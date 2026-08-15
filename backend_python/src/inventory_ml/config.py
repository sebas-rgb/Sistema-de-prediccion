"""Configuracion central del proyecto.

UNICA fuente de verdad para rutas, horizonte y umbrales de riesgo.
Ningun otro modulo debe hardcodear estos valores.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------
# Raiz del proyecto
# ---------------------------------------------------------------
# config.py vive en src/inventory_ml/, la raiz esta dos niveles arriba de src/
PROJECT_ROOT = Path(
    os.environ.get("INVENTORY_ML_ROOT", Path(__file__).resolve().parents[2])
)

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "inventario.db"))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", PROJECT_ROOT / "artifacts"))
MODELS_DIR = ARTIFACTS_DIR / "models"

MODEL_NAME = os.environ.get("MODEL_NAME", "stockout_simulated_v1")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", MODELS_DIR / f"{MODEL_NAME}.joblib"))
MODEL_METADATA_PATH = Path(
    os.environ.get("MODEL_METADATA_PATH", MODELS_DIR / f"{MODEL_NAME}.metadata.json")
)

# ---------------------------------------------------------------
# Dominio
# ---------------------------------------------------------------
HORIZONTE_DIAS = int(os.environ.get("HORIZONTE_DIAS", 30))
LEAD_TIME_DIAS = int(os.environ.get("LEAD_TIME_DIAS", 30))

# ---------------------------------------------------------------
# Niveles de riesgo (unica definicion del proyecto)
# ---------------------------------------------------------------
UMBRAL_RIESGO_ALTO = float(os.environ.get("UMBRAL_RIESGO_ALTO", 0.70))
UMBRAL_RIESGO_MEDIO = float(os.environ.get("UMBRAL_RIESGO_MEDIO", 0.40))


def nivel_riesgo(probabilidad: float) -> str:
    """Convierte una probabilidad [0,1] en ALTO / MEDIO / BAJO.

    Unica funcion del proyecto autorizada a aplicar los umbrales.
    """
    if not 0.0 <= probabilidad <= 1.0:
        raise ValueError(f"Probabilidad fuera de rango: {probabilidad}")
    if probabilidad > UMBRAL_RIESGO_ALTO:
        return "ALTO"
    if probabilidad >= UMBRAL_RIESGO_MEDIO:
        return "MEDIO"
    return "BAJO"


# ---------------------------------------------------------------
# Para la fase siguiente (API)
# ---------------------------------------------------------------
MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", 500))
