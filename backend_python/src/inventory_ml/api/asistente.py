"""Asistente conversacional sobre el inventario.

    pregunta -> resumen del inventario -> LLM -> respuesta

Decisiones:
  - La llamada al LLM vive en Python, no en Spring: el contexto que el modelo
    necesita ya esta aqui, y asi se evita un salto de red extra.
  - La API key se lee de entorno y NUNCA sale hacia el navegador ni a los logs.
  - Se envia un resumen curado, no el CSV completo: mas barato y mejores
    respuestas.
  - El system prompt deja explicito que el modelo predictivo es SIMULADO y que
    la decision de compra es de la persona, no del asistente.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from inventory_ml import config
from inventory_ml.api.dependencies import get_predictor
from inventory_ml.api.schemas import (
    AsistenteRequest,
    AsistenteResponse,
    ErrorResponse,
)
from inventory_ml.inference import Predictor
from inventory_ml.repository import InventarioNoDisponibleError
from inventory_ml.resumen import construir_resumen, resumen_a_texto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/asistente", tags=["asistente"])

SYSTEM_PROMPT = """Eres un asistente de analisis de inventario para un laboratorio optico.

Recibes un resumen del inventario con probabilidades de agotamiento calculadas
por un modelo predictivo. Tu trabajo es ayudar a una persona a entender esos
datos y a priorizar compras.

REGLAS IMPORTANTES:

1. El modelo predictivo fue entrenado con datos SIMULADOS y no ha sido validado
   con historia real. Trata las probabilidades como orientativas, no como
   hechos. Si el usuario va a tomar una decision de compra importante,
   recuerdaselo.
2. NO decides tu. Presentas analisis, prioridades y advertencias; la persona
   decide. Nunca digas "compra X"; di "X aparece como prioridad porque...".
3. Responde SOLO con los datos del resumen. Si te preguntan algo que el resumen
   no contiene, dilo claramente en vez de inventar cifras.
4. Un producto sin consumo historico ("Muerto") en stock cero NO es una
   prioridad de compra aunque su probabilidad sea alta: nadie lo consume.
5. Se breve y concreto. Usa listas cortas. Responde en espanol."""


@router.post(
    "",
    response_model=AsistenteResponse,
    summary="Pregunta al asistente sobre el inventario",
    description=(
        "Envia la pregunta junto a un resumen del inventario a un modelo de "
        "lenguaje. Requiere la variable de entorno LLM_API_KEY; sin ella "
        "devuelve 503."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "Pregunta invalida"},
        503: {"model": ErrorResponse, "description": "Asistente o modelo no disponible"},
    },
)
def preguntar(
    peticion: AsistenteRequest,
    predictor: Predictor = Depends(get_predictor),
) -> AsistenteResponse:
    if not config.llm_configurado():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Asistente no configurado. Falta la variable de entorno LLM_API_KEY.",
        )

    try:
        resumen = construir_resumen(predictor, fecha=peticion.fecha)
    except InventarioNoDisponibleError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    contexto = resumen_a_texto(resumen)
    logger.info(
        "Asistente | fecha=%s | pregunta de %s caracteres",
        resumen["fecha"],
        len(peticion.pregunta),
    )

    cuerpo = {
        "model": config.LLM_MODEL,
        "max_tokens": config.LLM_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Resumen del inventario:\n\n{contexto}\n\nPregunta: {peticion.pregunta}",
            },
        ],
    }

    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT) as cliente:
            respuesta = cliente.post(
                f"{config.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                json=cuerpo,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
    except httpx.HTTPStatusError as exc:
        # El cuerpo del error puede traer detalles de la cuenta: solo al log.
        logger.error(
            "El proveedor del LLM devolvio %s: %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El asistente no esta disponible en este momento.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Fallo de red al contactar el LLM: %s", type(exc).__name__)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El asistente no esta disponible en este momento.",
        ) from exc

    try:
        texto = datos["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Respuesta inesperada del LLM: %s", str(datos)[:300])
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El asistente devolvio una respuesta que no se pudo interpretar.",
        ) from exc

    uso = datos.get("usage") or {}
    return AsistenteResponse(
        respuesta=texto.strip(),
        fecha_contexto=resumen["fecha"],
        modelo_llm=datos.get("model", config.LLM_MODEL),
        version_modelo_prediccion=resumen["modelo"]["version"],
        origen_modelo=resumen["modelo"]["origen_datos"],
        estado_validacion=resumen["modelo"]["estado_validacion"],
        tokens_entrada=uso.get("prompt_tokens"),
        tokens_salida=uso.get("completion_tokens"),
    )
