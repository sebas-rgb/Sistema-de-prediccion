"""Entrenamiento del modelo de agotamiento a N dias.

Reemplaza al script perdido que genero `modelo_agotamiento.pkl`.
Diferencias intencionales respecto a aquel:

  1. Produce un Pipeline completo (encoding + modelo), no un estimador crudo.
  2. El encoding de `clase` es fijo y explicito (ver features/dataset.py).
  3. Hace split TEMPORAL, no aleatorio: entrenar con el futuro y evaluar con
     el pasado infla las metricas de forma irreal en series temporales.
  4. Escribe metadata junto al artefacto.

Uso:
    python -m inventory_ml.training.train
    python -m inventory_ml.training.train --db data/inventario.db --test-size 0.2
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

from inventory_ml import config
from inventory_ml.features import (
    CLASES,
    COLUMNAS_NUMERICAS,
    COLUMNA_CATEGORICA,
    FEATURES,
    TARGET,
    construir_dataset,
    preparar_features,
)

logger = logging.getLogger(__name__)

VERSION_MODELO = "2.0.0"
SEMILLA = 42

# Mientras el modelo se entrene sobre la simulacion, estos valores NO cambian.
ORIGEN_DATOS = "SIMULADO"
ESTADO_VALIDACION = "NO_VALIDADO_CON_DATOS_REALES"

# "rf" es el modelo de produccion y conserva las rutas de config. "logistica"
# se guarda aparte: sirve de linea base interpretable en el experimento y no
# debe pisar el artefacto que sirve la API.
ALGORITMOS = ("rf", "logistica")


def rutas_artefacto(algoritmo: str) -> tuple[Path, Path]:
    if algoritmo == "rf":
        return config.MODEL_PATH, config.MODEL_METADATA_PATH
    nombre = f"stockout_{algoritmo}_v1"
    return (
        config.MODELS_DIR / f"{nombre}.joblib",
        config.MODELS_DIR / f"{nombre}.metadata.json",
    )


def cargar_desde_sqlite(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base de datos: {db_path}")
    with sqlite3.connect(db_path) as conn:
        inventario = pd.read_sql("SELECT fecha, codigo, stock FROM inventario", conn)
        productos = pd.read_sql("SELECT * FROM productos", conn)
    return inventario, productos


def split_temporal(
    dataset: pd.DataFrame, test_size: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Corta por fecha: pasado para entrenar, futuro para evaluar."""
    fechas = dataset["fecha"].sort_values().unique()
    corte = pd.Timestamp(fechas[int(len(fechas) * (1 - test_size))])
    train = dataset[dataset["fecha"] < corte]
    test = dataset[dataset["fecha"] >= corte]
    return train, test, corte


def construir_pipeline(balancear: bool = False, algoritmo: str = "rf") -> Pipeline:
    """Encoding + modelo en un solo artefacto.

    Hiperparametros del bosque identicos a los de `riesgo_agotamiento.py` (el
    script original): no se cambia el algoritmo de produccion.

    handle_unknown='use_encoded_value' evita que una clase nueva reviente la
    inferencia en produccion; queda marcada como -1.
    """
    preprocesador = ColumnTransformer(
        transformers=[
            (
                "clase",
                OrdinalEncoder(
                    categories=[CLASES],
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
                [COLUMNA_CATEGORICA],
            ),
        ],
        remainder="passthrough",
        verbose_feature_names_out=False,
    )
    if algoritmo == "logistica":
        # Escalar es obligatorio aqui y no en el bosque: stock_actual llega a
        # miles y frecuencia_movimiento vive en [0,1]. Sin StandardScaler el
        # descenso no converge y los coeficientes no son comparables.
        return Pipeline(
            [
                ("preproceso", preprocesador),
                ("escalado", StandardScaler()),
                (
                    "modelo",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced" if balancear else None,
                        random_state=SEMILLA,
                    ),
                ),
            ]
        )

    modelo = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        class_weight="balanced" if balancear else None,
        n_jobs=-1,
        random_state=SEMILLA,
    )
    return Pipeline([("preproceso", preprocesador), ("modelo", modelo)])


def entrenar(
    db_path: Path,
    test_size: float = 0.2,
    balancear: bool = False,
    algoritmo: str = "rf",
) -> dict:
    inventario, productos = cargar_desde_sqlite(db_path)
    dataset = construir_dataset(inventario, productos, config.HORIZONTE_DIAS)
    logger.info("Dataset construido: %s filas", len(dataset))

    train, test, corte = split_temporal(dataset, test_size)
    if train.empty or test.empty:
        raise ValueError("El split temporal dejo un lado vacio; revisa el historico")
    logger.info("Split temporal en %s | train=%s test=%s", corte.date(), len(train), len(test))

    X_train = preparar_features(train)
    y_train = train[TARGET]
    X_test = preparar_features(test)
    y_test = test[TARGET]

    pipeline = construir_pipeline(balancear=balancear, algoritmo=algoritmo)
    pipeline.fit(X_train, y_train)

    # Verificacion explicita de la clase positiva (no asumir [:, 1])
    clases = list(pipeline.classes_)
    if 1 not in clases:
        raise ValueError(f"El modelo no aprendio la clase positiva. classes_={clases}")
    indice_positiva = clases.index(1)

    proba = pipeline.predict_proba(X_test)[:, indice_positiva]
    pred = pipeline.predict(X_test)

    metricas = {
        "accuracy": float(accuracy_score(y_test, pred)),
        "roc_auc": (
            float(roc_auc_score(y_test, proba)) if y_test.nunique() > 1 else None
        ),
        "positivos_test": int(y_test.sum()),
        "n_test": int(len(y_test)),
    }
    logger.info("Metricas holdout temporal: %s", metricas)
    print(classification_report(y_test, pred, zero_division=0))
    print(confusion_matrix(y_test, pred))

    model_path, metadata_path = rutas_artefacto(algoritmo)
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)

    metadata = {
        "version_modelo": VERSION_MODELO,
        "algoritmo": type(pipeline.named_steps["modelo"]).__name__,
        "horizonte_dias": config.HORIZONTE_DIAS,
        "definicion_target": (
            f"stock llega a 0 en algun momento dentro de "
            f"{config.HORIZONTE_DIAS} dias (minimo de la ventana)"
        ),
        "origen_datos": ORIGEN_DATOS,
        "estado_validacion": ESTADO_VALIDACION,
        "fecha_entrenamiento": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": FEATURES,
        "features_numericas": COLUMNAS_NUMERICAS,
        "clases_categoricas": CLASES,
        "clases_target": [int(c) for c in clases],
        "indice_clase_positiva": indice_positiva,
        "corte_temporal": corte.date().isoformat(),
        "n_train": int(len(train)),
        "semilla": SEMILLA,
        "class_weight_balanced": balancear,
        "metricas_holdout_temporal": metricas,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info("Artefacto guardado en %s", model_path)
    return metadata


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Entrena el modelo de agotamiento")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument(
        "--balancear",
        action="store_true",
        help="class_weight=balanced (NO estaba en el script original)",
    )
    parser.add_argument(
        "--algoritmo",
        choices=ALGORITMOS,
        default="rf",
        help="rf sobrescribe el modelo de produccion; logistica se guarda aparte",
    )
    args = parser.parse_args()
    entrenar(args.db, args.test_size, args.balancear, args.algoritmo)


if __name__ == "__main__":
    main()
