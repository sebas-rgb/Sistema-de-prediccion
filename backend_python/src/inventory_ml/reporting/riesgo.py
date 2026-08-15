"""Scoring de riesgo actual y generacion de los CSV que hoy consume Spring Boot.

Reemplaza la segunda mitad de `riesgo_agotamiento.py`. Diferencias:

  - NO entrena. Carga el artefacto ya entrenado via Predictor.
  - NO codifica `clase` a mano: lo hace el Pipeline.
  - NO duplica los umbrales: usa config.nivel_riesgo().

Este modulo es temporal: existe para que el proyecto Java siga funcionando con
sus CSV estaticos hasta que consuma la API. Cuando eso ocurra, se puede borrar.

Uso:
    python -m inventory_ml.reporting.riesgo
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from inventory_ml import config
from inventory_ml.features import COLUMNAS_NUMERICAS, COLUMNA_CATEGORICA
from inventory_ml.inference import Predictor

logger = logging.getLogger(__name__)

SQL_ULTIMO_STOCK = """
SELECT i.codigo, i.stock
FROM inventario i
INNER JOIN (
    SELECT codigo, MAX(fecha) AS ultima_fecha
    FROM inventario
    GROUP BY codigo
) ult ON i.codigo = ult.codigo AND i.fecha = ult.ultima_fecha
"""


def cargar_estado_actual(db_path: Path) -> pd.DataFrame:
    """Productos + su ultimo stock conocido, listos para inferencia."""
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base de datos: {db_path}")
    with sqlite3.connect(db_path) as conn:
        productos = pd.read_sql("SELECT * FROM productos", conn)
        ultimo = pd.read_sql(SQL_ULTIMO_STOCK, conn)

    productos["codigo"] = productos["codigo"].astype(str)
    ultimo["codigo"] = ultimo["codigo"].astype(str)
    df = productos.merge(ultimo, on="codigo", how="left")

    sin_stock = df["stock"].isna().sum()
    if sin_stock:
        # El script original no cubria esto: un NaN hace fallar predict_proba.
        logger.warning("%s productos sin historial de inventario; se excluyen", sin_stock)
        df = df.dropna(subset=["stock"])

    return df.rename(columns={"stock": "stock_actual"})


def puntuar(df: pd.DataFrame, predictor: Predictor) -> pd.DataFrame:
    """Una sola llamada vectorizada al Pipeline para todos los productos."""
    columnas = ["codigo", *COLUMNAS_NUMERICAS, COLUMNA_CATEGORICA]
    resultados = predictor.predict_batch(df[columnas].to_dict("records"))
    puntuado = pd.DataFrame(resultados)
    return df.merge(
        puntuado[["codigo", "probabilidad_agotamiento", "nivel_riesgo"]],
        on="codigo",
        how="left",
    )


def generar_reportes(db_path: Path, salida: Path) -> dict[str, int]:
    predictor = Predictor.cargar()
    df = cargar_estado_actual(db_path)

    total = len(df)
    agotados = int((df["stock_actual"] <= 0).sum())
    logger.info("Productos: %s | agotados: %s | activos: %s", total, agotados, total - agotados)

    df = puntuar(df, predictor)

    # Igual que el script original: se puntua todo y luego se excluyen los ya
    # agotados, que no son "riesgo" sino un hecho consumado.
    activos = df[df["stock_actual"] > 0].sort_values(
        "probabilidad_agotamiento", ascending=False
    )

    salida.mkdir(parents=True, exist_ok=True)
    activos.to_csv(salida / "riesgo_productos.csv", index=False)
    activos.head(50).to_csv(salida / "top50_riesgo.csv", index=False)

    conteos: dict[str, int] = {}
    for nivel, archivo in [
        ("ALTO", "alto_riesgo.csv"),
        ("MEDIO", "riesgo_medio.csv"),
        ("BAJO", "riesgo_bajo.csv"),
    ]:
        subset = activos[activos["nivel_riesgo"] == nivel]
        subset.to_csv(salida / archivo, index=False)
        conteos[nivel] = len(subset)

    logger.info("Reportes en %s | %s", salida, conteos)
    return conteos


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Genera los CSV de riesgo actual")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--salida", type=Path, default=config.ARTIFACTS_DIR / "reports")
    args = parser.parse_args()
    generar_reportes(args.db, args.salida)


if __name__ == "__main__":
    main()
