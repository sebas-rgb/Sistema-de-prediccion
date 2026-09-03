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

# ---------------------------------------------------------------
# Carga del archivo .env
# ---------------------------------------------------------------
# Las variables ya definidas en el entorno GANAN sobre el archivo: asi se puede
# sobrescribir puntualmente sin editar el .env. Si python-dotenv no esta
# instalado, todo sigue funcionando leyendo solo el entorno.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass

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
# API
# ---------------------------------------------------------------
MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", 500))

# ---------------------------------------------------------------
# Asistente LLM
# ---------------------------------------------------------------
# La clave NUNCA se escribe en codigo ni se envia al navegador.
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
# Los nombres de modelo cambian seguido; se elige por entorno, no en codigo.
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", 30))
# 800 truncaba las respuestas: los modelos de razonamiento (gpt-oss, o-series)
# gastan tokens de razonamiento contra este mismo presupuesto. Subirlo mas
# tampoco es gratis: Groq cuenta prompt + max_tokens contra el limite por
# minuto, asi que un techo alto provoca 429 antes de generar nada.
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 1200))
# Cuantos productos de mayor riesgo se incluyen en el contexto. El resumen se
# reenvia COMPLETO en cada vuelta del agente, asi que cada fila se paga
# tantas veces como herramientas invoque.
LLM_TOP_RIESGO = int(os.environ.get("LLM_TOP_RIESGO", 10))


def llm_configurado() -> bool:
    return bool(LLM_API_KEY)
