"""Capa de inferencia.

Es el unico punto de entrada para obtener predicciones. La futura API de
FastAPI debe limitarse a: validar JSON -> llamar Predictor -> serializar.
Nada de feature engineering ni joblib.load fuera de aqui.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd

from inventory_ml import config
from inventory_ml.features import FEATURES, preparar_features

logger = logging.getLogger(__name__)


class ModeloNoDisponibleError(RuntimeError):
    """El artefacto no existe, esta corrupto o su metadata es invalida."""


class Predictor:
    """Envuelve el Pipeline entrenado y su metadata."""

    def __init__(self, pipeline: Any, metadata: dict) -> None:
        self._pipeline = pipeline
        self._metadata = metadata
        self._indice_positiva = self._resolver_clase_positiva(pipeline)

    # -------------------------------------------------------
    # Construccion
    # -------------------------------------------------------
    @classmethod
    def cargar(
        cls,
        model_path: Path | None = None,
        metadata_path: Path | None = None,
    ) -> "Predictor":
        model_path = Path(model_path or config.MODEL_PATH)
        metadata_path = Path(metadata_path or config.MODEL_METADATA_PATH)

        if not model_path.exists():
            raise ModeloNoDisponibleError(f"No existe el artefacto: {model_path.name}")
        try:
            pipeline = joblib.load(model_path)
        except Exception as exc:  # artefacto corrupto / incompatible
            raise ModeloNoDisponibleError(
                f"No se pudo cargar el artefacto: {type(exc).__name__}"
            ) from exc

        if not hasattr(pipeline, "predict_proba"):
            raise ModeloNoDisponibleError("El artefacto no soporta predict_proba()")

        metadata: dict = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ModeloNoDisponibleError("Metadata invalida (JSON malformado)") from exc
        else:
            logger.warning("Sin metadata en %s; se reportaran campos nulos", metadata_path.name)

        logger.info(
            "Modelo cargado: %s (version=%s origen=%s)",
            model_path.name,
            metadata.get("version_modelo"),
            metadata.get("origen_datos"),
        )
        return cls(pipeline, metadata)

    @staticmethod
    def _resolver_clase_positiva(pipeline: Any) -> int:
        """Nunca asumir predict_proba(X)[:, 1]."""
        clases = list(getattr(pipeline, "classes_", []))
        if not clases:
            raise ModeloNoDisponibleError("El artefacto no expone classes_")
        if 1 in clases:
            return clases.index(1)
        if True in clases:
            return clases.index(True)
        raise ModeloNoDisponibleError(f"No hay clase positiva en classes_={clases}")

    # -------------------------------------------------------
    # Inferencia
    # -------------------------------------------------------
    def predict_batch(self, registros: Iterable[dict]) -> list[dict]:
        """Inferencia vectorizada: N registros -> 1 sola llamada al Pipeline."""
        filas = list(registros)
        if not filas:
            return []

        df = pd.DataFrame(filas)
        codigos = (
            df["codigo"].astype(str).tolist()
            if "codigo" in df.columns
            else [None] * len(df)
        )

        X = preparar_features(df)
        probas = self._pipeline.predict_proba(X)[:, self._indice_positiva]

        hoy = date.today().isoformat()
        return [
            {
                "codigo": codigo,
                "probabilidad_agotamiento": round(float(p), 4),
                "nivel_riesgo": config.nivel_riesgo(float(p)),
                "horizonte_dias": self._metadata.get(
                    "horizonte_dias", config.HORIZONTE_DIAS
                ),
                "version_modelo": self._metadata.get("version_modelo"),
                "fecha_prediccion": hoy,
                "origen_modelo": self._metadata.get("origen_datos"),
                "estado_validacion": self._metadata.get("estado_validacion"),
            }
            for codigo, p in zip(codigos, probas)
        ]

    def predict(self, registro: dict) -> dict:
        """Un solo producto. Reutiliza exactamente la misma logica que el batch."""
        return self.predict_batch([registro])[0]

    # -------------------------------------------------------
    # Metadata
    # -------------------------------------------------------
    def get_model_info(self) -> dict:
        """Solo campos publicables: nada de rutas ni configuracion interna."""
        return {
            "version_modelo": self._metadata.get("version_modelo"),
            "algoritmo": self._metadata.get("algoritmo"),
            "horizonte_dias": self._metadata.get("horizonte_dias"),
            "origen_datos": self._metadata.get("origen_datos"),
            "estado_validacion": self._metadata.get("estado_validacion"),
            "fecha_entrenamiento": self._metadata.get("fecha_entrenamiento"),
            "features_requeridas": FEATURES,
        }
