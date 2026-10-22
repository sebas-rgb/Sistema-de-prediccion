"""Agente conversacional sobre el inventario.

    pregunta
      -> resumen del inventario inyectado como contexto base
      -> BUCLE: el modelo pide herramientas, se ejecutan, ve el resultado
      -> respuesta

Decisiones:
  - La llamada al LLM vive en Python, no en Spring: el contexto que el modelo
    necesita ya esta aqui, y asi se evita un salto de red extra.
  - La API key se lee de entorno y NUNCA sale hacia el navegador ni a los logs.
  - Se inyecta un resumen curado ADEMAS de dar herramientas. Las preguntas
    frecuentes ("¿que priorizo?") se responden en una sola vuelta sin gastar
    iteraciones; las herramientas cubren lo que el resumen no puede anticipar.
  - El system prompt deja explicito que el modelo predictivo es SIMULADO y que
    la decision de compra es de la persona, no del agente.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from inventory_ml import config, herramientas
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

# Los umbrales se interpolan desde config: si cambian alli, el agente se entera.
SYSTEM_PROMPT = """Eres un asistente de analisis de inventario para un laboratorio optico.

Recibes un resumen del inventario con probabilidades de agotamiento calculadas
por un modelo predictivo, y tienes herramientas para consultar datos que el
resumen no incluye.

REGLAS IMPORTANTES:

1. El modelo predictivo fue entrenado con datos SIMULADOS y no ha sido validado
   con historia real. Trata las probabilidades como orientativas, no como
   hechos. Si el usuario va a tomar una decision de compra importante,
   recuerdaselo.
2. NO decides tu. Presentas analisis, prioridades y advertencias; la persona
   decide. Nunca digas "compra X"; di "X aparece como prioridad porque...".
3. Responde SOLO con datos del resumen o de las herramientas. Si te preguntan
   algo que no puedes obtener por ninguna de las dos vias, dilo claramente en
   vez de inventar cifras.
4. Un producto sin consumo historico ("Muerto") en stock cero NO es una
   prioridad de compra aunque su probabilidad sea alta: nadie lo consume.
5. Usa las herramientas cuando la pregunta lo requiera: un codigo concreto que
   no esta en el resumen, un escenario hipotetico de stock, o las cifras de la
   comparacion de politicas. No las uses si el resumen ya basta.
6. Los niveles de riesgo salen de la probabilidad: ALTO por encima de {alto:.0%},
   MEDIO entre {medio:.0%} y {alto:.0%}, BAJO por debajo de {medio:.0%}. Para
   "cuanto stock hace falta" usa la herramienta stock_minimo y reporta su cifra.
7. Se breve y concreto. Usa listas cortas. Responde en espanol.""".format(
    alto=config.UMBRAL_RIESGO_ALTO, medio=config.UMBRAL_RIESGO_MEDIO
)


def _pedir(cliente: httpx.Client, mensajes: list[dict]) -> dict:
    """Una llamada al proveedor. Traduce cualquier fallo a un 503 sin detalles.

    `tools` viaja SIEMPRE, incluso en la vuelta final. Omitirlo equivale a
    tool_choice="none", y si el historial ya venia encadenando llamadas el
    modelo intenta otra igual y el proveedor responde 400 ("Tool choice is
    none, but model called a tool"). Para cerrar la conversacion se le instruye
    por mensaje, no quitandole las herramientas.
    """
    cuerpo: dict = {
        "max_tokens": config.LLM_MAX_TOKENS,
        "messages": mensajes,
        "tools": herramientas.DEFINICIONES,
        "tool_choice": "auto",
    }

    modelos = list(dict.fromkeys([config.LLM_MODEL, *config.LLM_MODELOS_RESPALDO]))
    # Los 503 de Gemini duran segundos: si toda la lista falla, una segunda
    # pasada tras una pausa corta suele entrar.
    intentos = modelos * 2
    try:
        for n, modelo in enumerate(intentos):
            if n == len(modelos):
                time.sleep(2)
            ultimo = n == len(intentos) - 1
            try:
                respuesta = cliente.post(
                    f"{config.LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                    json={**cuerpo, "model": modelo},
                )
            except httpx.TimeoutException:
                if ultimo:
                    raise
                logger.warning("LLM %s no respondio a tiempo; pruebo el siguiente", modelo)
                continue
            # 503 = saturado; 429 = cuota agotada (el free tier de Gemini Flash
            # da 20 peticiones al dia y cada pregunta gasta varias vueltas).
            if respuesta.status_code in (429, 503) and not ultimo:
                logger.warning("LLM %s no disponible (%s); pruebo el siguiente", modelo, respuesta.status_code)
                continue
            respuesta.raise_for_status()
            return respuesta.json()
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


def _mensaje_de(datos: dict) -> dict:
    try:
        return datos["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Respuesta inesperada del LLM: %s", str(datos)[:300])
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El asistente devolvio una respuesta que no se pudo interpretar.",
        ) from exc


@router.post(
    "",
    response_model=AsistenteResponse,
    summary="Pregunta al agente sobre el inventario",
    description=(
        "Envia la pregunta junto a un resumen del inventario a un modelo de "
        "lenguaje que puede invocar herramientas para consultar productos "
        "concretos, simular escenarios de stock o leer la comparacion de "
        "politicas. Requiere la variable de entorno LLM_API_KEY; sin ella "
        "devuelve 503.\n\n"
        "`herramientas_usadas` deja trazabilidad de que consulto el agente para "
        "construir la respuesta."
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
        "Agente | fecha=%s | pregunta de %s caracteres",
        resumen["fecha"],
        len(peticion.pregunta),
    )

    mensajes: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Resumen del inventario:\n\n{contexto}\n\nPregunta: {peticion.pregunta}",
        },
    ]

    usadas: list[str] = []
    tokens_entrada = tokens_salida = 0
    texto = ""
    modelo_llm = config.LLM_MODEL

    with httpx.Client(timeout=config.LLM_TIMEOUT) as cliente:
        for vuelta in range(herramientas.MAX_ITERACIONES):
            datos = _pedir(cliente, mensajes)
            modelo_llm = datos.get("model", config.LLM_MODEL)

            uso = datos.get("usage") or {}
            tokens_entrada += uso.get("prompt_tokens") or 0
            tokens_salida += uso.get("completion_tokens") or 0

            mensaje = _mensaje_de(datos)
            llamadas = mensaje.get("tool_calls") or []

            if not llamadas:
                texto = (mensaje.get("content") or "").strip()
                break

            # El mensaje del asistente se reenvia VERBATIM: el proveedor exige
            # que cada resultado referencie un tool_call_id que ya vio.
            mensajes.append(mensaje)

            for llamada in llamadas:
                funcion = llamada.get("function") or {}
                nombre = funcion.get("name", "")
                resultado = herramientas.ejecutar(
                    nombre,
                    funcion.get("arguments") or "{}",
                    predictor,
                    peticion.fecha,
                )
                usadas.append(nombre)
                logger.info(
                    "Agente | vuelta %s | herramienta %s -> %s",
                    vuelta + 1,
                    nombre,
                    "error" if "error" in resultado else "ok",
                )
                mensajes.append(
                    {
                        "role": "tool",
                        "tool_call_id": llamada.get("id"),
                        "content": json.dumps(resultado, ensure_ascii=False),
                    }
                )
        else:
            # Se agotaron las iteraciones sin respuesta final: se fuerza una
            # ultima vuelta SIN herramientas para que concluya con lo que tiene.
            logger.warning("Agente | tope de %s vueltas alcanzado", herramientas.MAX_ITERACIONES)
            mensajes.append(
                {
                    "role": "user",
                    "content": (
                        "Ya no puedes usar mas herramientas. Responde ahora con la "
                        "informacion que ya tienes, y di explicitamente que te falto "
                        "si la respuesta queda incompleta."
                    ),
                }
            )
            datos = _pedir(cliente, mensajes)
            uso = datos.get("usage") or {}
            tokens_entrada += uso.get("prompt_tokens") or 0
            tokens_salida += uso.get("completion_tokens") or 0
            texto = (_mensaje_de(datos).get("content") or "").strip()

    if not texto:
        logger.error("El agente termino sin texto tras %s herramientas", len(usadas))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El asistente no pudo completar una respuesta.",
        )

    return AsistenteResponse(
        respuesta=texto,
        fecha_contexto=resumen["fecha"],
        modelo_llm=modelo_llm,
        version_modelo_prediccion=resumen["modelo"]["version"],
        origen_modelo=resumen["modelo"]["origen_datos"],
        estado_validacion=resumen["modelo"]["estado_validacion"],
        herramientas_usadas=usadas,
        tokens_entrada=tokens_entrada or None,
        tokens_salida=tokens_salida or None,
    )


# ---------------------------------------------------------------
# Preguntas en segundo plano
# ---------------------------------------------------------------
# Una pregunta tarda de segundos a mas de un minuto (varias vueltas al LLM).
# Con una sola peticion abierta, cambiar de pagina la cancelaba y el chat
# guardaba "Failed to fetch". Asi el navegador solo pregunta "¿ya?" cada pocos
# segundos y puede retomar la espera desde otra pagina con el id.
# ponytail: en memoria del proceso; se pierden al reiniciar y no escala a
# varios workers. Pasar a una tabla si algun dia hay mas de un proceso.
_ejecutor = ThreadPoolExecutor(max_workers=4)
_tareas: dict[str, Future] = {}
MAX_TAREAS = 200


@router.post(
    "/tareas",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Encola una pregunta y devuelve su id",
    description="Igual que POST /asistente, pero sin esperar: consulta el resultado en GET /tareas/{id}.",
)
def encolar(
    peticion: AsistenteRequest,
    predictor: Predictor = Depends(get_predictor),
) -> dict:
    # Se descartan las terminadas mas viejas: el dict conserva el orden de llegada
    for viejo in [k for k, f in _tareas.items() if f.done()][: max(0, len(_tareas) - MAX_TAREAS + 1)]:
        del _tareas[viejo]
    id_tarea = uuid.uuid4().hex
    _tareas[id_tarea] = _ejecutor.submit(preguntar, peticion, predictor)
    return {"id": id_tarea}


@router.get(
    "/tareas/{id_tarea}",
    summary="Estado de una pregunta encolada",
    responses={404: {"model": ErrorResponse, "description": "Id desconocido o API reiniciada"}},
)
def consultar(id_tarea: str) -> dict:
    futuro = _tareas.get(id_tarea)
    if futuro is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta desconocida.")
    if not futuro.done():
        return {"estado": "EN_CURSO"}
    error = futuro.exception()
    if error is None:
        return {"estado": "OK", "resultado": futuro.result().model_dump(mode="json")}
    detalle = error.detail if isinstance(error, HTTPException) else "Error interno del asistente."
    if not isinstance(error, HTTPException):
        logger.error("Fallo una pregunta encolada", exc_info=error)
    return {"estado": "ERROR", "detalle": detalle}
