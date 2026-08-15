"""Capa HTTP sobre el modulo `inference`.

No entrena, no simula, no lee Excel, no hace feature engineering. Solo:
    validar JSON -> Predictor -> serializar.

Ejecutar:
    uvicorn inventory_ml.api.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from inventory_ml import config
from inventory_ml.api.dependencies import get_predictor, get_predictor_opcional
from inventory_ml.api.inventario import router as inventario_router
from inventory_ml.api.schemas import (
    BatchRequest,
    BatchResponse,
    ErrorResponse,
    HealthResponse,
    ModelInfoResponse,
    PrediccionResponse,
    ProductoRequest,
)
from inventory_ml.features import ContratoFeaturesError
from inventory_ml.inference import ModeloNoDisponibleError, Predictor

logger = logging.getLogger(__name__)

# Ruta base versionada: el consumidor es Spring Boot y un cambio de contrato
# futuro debe poder convivir con el actual. /health queda fuera porque es una
# sonda de infraestructura, no parte del contrato de negocio.
API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Carga el modelo UNA vez al arrancar. Nunca por request."""
    try:
        app.state.predictor = Predictor.cargar()
        info = app.state.predictor.get_model_info()
        logger.info(
            "API lista | modelo %s | origen=%s | validacion=%s",
            info["version_modelo"],
            info["origen_datos"],
            info["estado_validacion"],
        )
    except ModeloNoDisponibleError as exc:
        # No se aborta el arranque: la app queda degradada y lo dice en /health.
        app.state.predictor = None
        logger.error("Modelo no disponible al arrancar: %s", exc)
    yield
    app.state.predictor = None
    logger.info("API detenida")


app = FastAPI(
    title="API de prediccion de agotamiento de inventario",
    version="1.0.0",
    description=(
        "Predice la probabilidad de que un producto se agote dentro del horizonte "
        "del modelo.\n\n"
        "**El modelo activo esta entrenado con datos SIMULADOS y no ha sido validado "
        "con historia real.** Cada respuesta incluye `origen_modelo` y "
        "`estado_validacion`; no interprete estas predicciones como productivas."
    ),
    lifespan=lifespan,
)

# Sin CORS a proposito: Spring Boot consume esta API servidor-a-servidor, donde
# CORS no aplica. Habilitarlo solo si algun dia la llama un navegador.

router = APIRouter(prefix=API_PREFIX, tags=["prediccion"])


# ---------------------------------------------------------------
# Manejo de errores: nunca stack traces al cliente
# ---------------------------------------------------------------
@app.exception_handler(ContratoFeaturesError)
async def _contrato_invalido(request: Request, exc: ContratoFeaturesError):
    logger.warning("Entrada incompatible con el contrato: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "La entrada no cumple el contrato de features del modelo."},
    )


@app.exception_handler(ModeloNoDisponibleError)
async def _modelo_no_disponible(request: Request, exc: ModeloNoDisponibleError):
    logger.error("Modelo no disponible: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Modelo no disponible."},
    )


@app.exception_handler(Exception)
async def _error_inesperado(request: Request, exc: Exception):
    # El detalle tecnico va al log, no a la respuesta.
    logger.exception("Error inesperado en %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno al procesar la solicitud."},
    )


# ---------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["operacion"],
    summary="Sonda de disponibilidad",
    description=(
        "Liviano: no ejecuta predicciones. Devuelve 200 si el modelo esta cargado "
        "y 503 si no, para que un balanceador o un readiness probe lo detecte sin "
        "leer el cuerpo."
    ),
)
def health(
    response: Response,
    predictor: Predictor | None = Depends(get_predictor_opcional),
) -> HealthResponse:
    cargado = predictor is not None
    if not cargado:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if cargado else "degraded", model_loaded=cargado)


@router.get(
    "/model/info",
    response_model=ModelInfoResponse,
    tags=["operacion"],
    summary="Metadata del modelo cargado",
    responses={503: {"model": ErrorResponse, "description": "Modelo no disponible"}},
)
def model_info(predictor: Predictor = Depends(get_predictor)) -> ModelInfoResponse:
    return ModelInfoResponse(**predictor.get_model_info())


@router.post(
    "/predict",
    response_model=PrediccionResponse,
    summary="Predice el agotamiento de un producto",
    responses={
        422: {"model": ErrorResponse, "description": "Entrada invalida"},
        503: {"model": ErrorResponse, "description": "Modelo no disponible"},
    },
)
def predict(
    item: ProductoRequest,
    predictor: Predictor = Depends(get_predictor),
) -> PrediccionResponse:
    resultado = predictor.predict(item.model_dump())
    return PrediccionResponse(**resultado)


@router.post(
    "/predict/batch",
    response_model=BatchResponse,
    summary="Predice varios productos en una sola llamada",
    description=(
        f"Maximo {config.MAX_BATCH_SIZE} productos por peticion. Se resuelve con una "
        "unica pasada vectorizada sobre el Pipeline, no con llamadas repetidas."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "Entrada invalida o batch excedido"},
        503: {"model": ErrorResponse, "description": "Modelo no disponible"},
    },
)
def predict_batch(
    payload: BatchRequest,
    predictor: Predictor = Depends(get_predictor),
) -> BatchResponse:
    logger.info("Batch recibido: %s items", len(payload.items))
    resultados = predictor.predict_batch([i.model_dump() for i in payload.items])
    return BatchResponse(
        total=len(resultados),
        resultados=[PrediccionResponse(**r) for r in resultados],
    )


app.include_router(router)
app.include_router(inventario_router)
