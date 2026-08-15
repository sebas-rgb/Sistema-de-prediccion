"""Acceso al Predictor sin estado global.

El Predictor vive en `app.state`, poblado una sola vez durante el lifespan.
Los endpoints lo reciben por inyeccion de dependencias.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from inventory_ml.inference import Predictor


def get_predictor_opcional(request: Request) -> Predictor | None:
    """Devuelve el Predictor o None si el modelo no pudo cargarse.

    Para /health, que debe poder responder aunque el modelo falte.
    """
    return getattr(request.app.state, "predictor", None)


def get_predictor(
    predictor: Predictor | None = Depends(get_predictor_opcional),
) -> Predictor:
    """Exige un modelo disponible. 503 si no lo hay.

    No se intenta cargar el artefacto aqui: eso ocurre una unica vez al arrancar.
    """
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Modelo no disponible. Revise el estado del servicio en /health.",
        )
    return predictor
