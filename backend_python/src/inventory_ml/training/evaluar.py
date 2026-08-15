"""Evaluacion honesta del modelo.

Accuracy no sirve aqui: si el 90% de los casos son negativos, predecir siempre
"no se agota" da 90%. Lo que importa es:

  - precision/recall sobre la clase positiva;
  - PR-AUC (mejor que ROC-AUC con clases desbalanceadas);
  - calibracion: cuando dice 80%, ¿se agota el 80% de las veces?;
  - y sobre todo: ¿le gana a una regla trivial?

BASELINE: dias_cobertura = stock_actual / consumo_promedio. Si eso es menor al
horizonte, se agota. Es una division. Si el modelo no le gana, el modelo sobra.

Uso:
    python -m inventory_ml.training.evaluar
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_fscore_support,
    roc_auc_score,
)

from inventory_ml import config
from inventory_ml.features import TARGET, construir_dataset, preparar_features
from inventory_ml.inference import Predictor
from inventory_ml.training.train import split_temporal

logger = logging.getLogger(__name__)


def metricas_binarias(y: np.ndarray, proba: np.ndarray, umbral: float = 0.5) -> dict:
    pred = (proba >= umbral).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, pred, average="binary", zero_division=0
    )
    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "pr_auc": round(float(average_precision_score(y, proba)), 4),
        "roc_auc": round(float(roc_auc_score(y, proba)), 4),
        "brier": round(float(brier_score_loss(y, proba)), 4),
    }


def baseline_cobertura(df: pd.DataFrame, horizonte: int) -> np.ndarray:
    """Regla trivial: dias de cobertura < horizonte -> se agota.

    Se convierte a pseudo-probabilidad para poder comparar curvas.
    """
    consumo = df["consumo_promedio"].replace(0, np.nan)
    dias_cobertura = (df["stock_actual"] / consumo).fillna(np.inf)
    return np.clip(1 - dias_cobertura / (horizonte * 2), 0, 1).to_numpy()


def tabla_calibracion(y: np.ndarray, proba: np.ndarray, bins: int = 5) -> pd.DataFrame:
    """Por tramo de probabilidad: que tan seguido ocurrio de verdad."""
    df = pd.DataFrame({"y": y, "p": proba})
    df["tramo"] = pd.cut(df["p"], np.linspace(0, 1, bins + 1), include_lowest=True)
    salida = (
        df.groupby("tramo", observed=True)
        .agg(n=("y", "size"), predicho=("p", "mean"), real=("y", "mean"))
        .round(3)
    )
    return salida


def evaluar(db_path: Path, test_size: float = 0.2) -> dict:
    predictor = Predictor.cargar()
    horizonte = predictor.get_model_info()["horizonte_dias"] or config.HORIZONTE_DIAS

    with sqlite3.connect(db_path) as conn:
        inventario = pd.read_sql("SELECT fecha, codigo, stock FROM inventario", conn)
        productos = pd.read_sql("SELECT * FROM productos", conn)

    dataset = construir_dataset(inventario, productos, horizonte)
    _, test, corte = split_temporal(dataset, test_size)
    logger.info("Evaluando sobre %s filas posteriores a %s", len(test), corte.date())

    y = test[TARGET].to_numpy()
    X = preparar_features(test)
    proba = predictor._pipeline.predict_proba(X)[:, predictor._indice_positiva]
    proba_baseline = baseline_cobertura(test, horizonte)

    resultado = {
        "n_test": int(len(y)),
        "tasa_positivos": round(float(y.mean()), 4),
        "modelo": metricas_binarias(y, proba),
        "baseline_cobertura": metricas_binarias(y, proba_baseline),
    }

    print("\n=== Evaluacion sobre datos NO vistos (posteriores a", corte.date(), ")===")
    print(f"Filas: {len(y)} | se agotaron de verdad: {y.mean():.1%}")
    print("\n", pd.DataFrame([resultado["modelo"], resultado["baseline_cobertura"]],
                             index=["MODELO", "baseline (division)"]).to_string())
    print("\n=== Calibracion del modelo ===")
    print(tabla_calibracion(y, proba).to_string())

    mejora = resultado["modelo"]["pr_auc"] - resultado["baseline_cobertura"]["pr_auc"]
    print(f"\nPR-AUC: el modelo {'supera' if mejora > 0 else 'NO supera'} al baseline "
          f"por {mejora:+.4f}")
    if mejora <= 0.02:
        print("La ventaja es marginal: la regla trivial ya resuelve el problema.")

    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Evalua el modelo contra un baseline")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--test-size", type=float, default=0.2)
    args = parser.parse_args()
    evaluar(args.db, args.test_size)


if __name__ == "__main__":
    main()
