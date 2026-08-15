"""Endpoint de comparacion de politicas de reposicion.

Sirve un resultado PRECALCULADO por
`python -m inventory_ml.simulation.experimento`. La simulacion completa tarda
~11 s: demasiado para una peticion HTTP, y ademas no cambia entre visitas.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, status

from inventory_ml import config
from inventory_ml.api.schemas import ErrorResponse, ExperimentoResponse
from inventory_ml.simulation.experimento import NOMBRE_JSON

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/experimento", tags=["experimento"])


@router.get(
    "",
    response_model=ExperimentoResponse,
    summary="Comparacion entre reposicion reactiva y predictiva",
    description=(
        "Resultado del experimento contrafactual: la misma demanda simulada bajo "
        "dos politicas de compra. Incluye la serie diaria de productos agotados "
        "para graficar.\n\n"
        "Se genera con `python -m inventory_ml.simulation.experimento`; si nunca "
        "se ejecuto, devuelve 503."
    ),
    responses={503: {"model": ErrorResponse, "description": "Experimento no generado"}},
)
def experimento() -> ExperimentoResponse:
    ruta = config.ARTIFACTS_DIR / "reports" / NOMBRE_JSON
    if not ruta.exists():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Comparacion no disponible. Ejecute el experimento primero.",
        )
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("El JSON del experimento esta corrupto: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Comparacion no disponible."
        ) from exc
    return ExperimentoResponse(**datos)
