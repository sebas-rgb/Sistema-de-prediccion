"""Endpoints de estado del inventario + prediccion.

Router separado de /predict: aquel recibe el estado del cliente, este lo lee de
la simulacion. Comparten el mismo Predictor y el mismo contrato de salida.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from inventory_ml import config
from inventory_ml.api.dependencies import get_predictor
from inventory_ml.api.schemas import (
    ErrorResponse,
    InventarioItem,
    InventarioResponse,
    RangoFechasResponse,
)
from inventory_ml.inference import Predictor
from inventory_ml.repository import InventarioNoDisponibleError, estado_en_fecha, rango_fechas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/inventario", tags=["inventario"])

TAMANO_PAGINA_MAX = 200


@router.get(
    "/fechas",
    response_model=RangoFechasResponse,
    summary="Ventana temporal disponible",
    description="Permite a la interfaz saber que fechas puede consultar.",
    responses={503: {"model": ErrorResponse, "description": "Inventario no disponible"}},
)
def fechas() -> RangoFechasResponse:
    try:
        return RangoFechasResponse(**rango_fechas(config.DB_PATH))
    except InventarioNoDisponibleError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get(
    "",
    response_model=InventarioResponse,
    summary="Estado del inventario en una fecha, con prediccion",
    description=(
        "Devuelve una pagina de productos con su stock en la fecha indicada y la "
        "probabilidad de agotamiento calculada con el modelo activo. Si no se "
        "indica fecha, usa la ultima disponible.\n\n"
        "Las predicciones se calculan en una unica pasada vectorizada por pagina."
    ),
    responses={503: {"model": ErrorResponse, "description": "Inventario o modelo no disponible"}},
)
def inventario(
    fecha: date | None = Query(None, description="YYYY-MM-DD; por defecto la ultima"),
    codigo: str | None = Query(None, max_length=64, description="Filtro parcial por codigo"),
    pagina: int = Query(1, ge=1),
    tamano_pagina: int = Query(50, ge=1, le=TAMANO_PAGINA_MAX),
    predictor: Predictor = Depends(get_predictor),
) -> InventarioResponse:
    try:
        fecha_efectiva, total, registros = estado_en_fecha(
            config.DB_PATH,
            fecha=fecha,
            codigo=codigo,
            limite=tamano_pagina,
            desplazamiento=(pagina - 1) * tamano_pagina,
        )
    except InventarioNoDisponibleError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    predicciones = predictor.predict_batch(registros) if registros else []
    info = predictor.get_model_info()

    items = [
        InventarioItem(
            codigo=reg["codigo"],
            fecha=fecha_efectiva,
            stock_actual=reg["stock_actual"],
            clase=reg["clase"],
            consumo_promedio=reg["consumo_promedio"],
            probabilidad_agotamiento=pred["probabilidad_agotamiento"],
            nivel_riesgo=pred["nivel_riesgo"],
        )
        for reg, pred in zip(registros, predicciones)
    ]

    logger.info("Inventario %s | pagina %s | %s items", fecha_efectiva, pagina, len(items))

    return InventarioResponse(
        fecha=fecha_efectiva,
        total=total,
        pagina=pagina,
        tamano_pagina=tamano_pagina,
        version_modelo=info["version_modelo"],
        origen_modelo=info["origen_datos"],
        estado_validacion=info["estado_validacion"],
        items=items,
    )
