"""Perfilado de productos a partir del historico real de inventario.

Reemplaza a `main.py`. Conserva intactas las reglas de negocio originales
(cortes de clasificacion, derivacion de consumos y reposiciones) y corrige:

  - `except:` desnudo -> excepciones concretas;
  - `if dias_hasta_agotarse` -> `is not None` (antes un 0.0 se volvia None);
  - muestreo con semilla fija (antes cambiaba en cada corrida);
  - rutas por argumento en vez de relativas al directorio de trabajo.

Entrada:  CSV consolidado con columnas de fecha, codigo y unidades.
Salida:   data/interim/productos_perfilados.json  (todos)
          data/interim/productos_muestra.json     (N por clase)

Uso:
    python -m inventory_ml.ingestion.perfilado --csv data/raw/inventario_consolidado.csv
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from inventory_ml import config

logger = logging.getLogger(__name__)

SEMILLA_MUESTRA = 42
N_POR_CLASE = 100

# Cortes de clasificacion por frecuencia de movimiento (reglas originales)
CLASE_MUERTO = 0.0
CLASE_BAJA = 0.05
CLASE_MEDIA = 0.20


class FormatoEntradaError(ValueError):
    """El CSV no tiene las columnas esperadas."""


def parse_fecha(valor: object) -> pd.Timestamp:
    """Formato original del export: dia_mes_anio."""
    try:
        d, m, y = str(valor).split("_")
        return pd.Timestamp(year=int(y), month=int(m), day=int(d))
    except (ValueError, TypeError):
        return pd.NaT


def detectar_columnas(df: pd.DataFrame) -> tuple[str, str, str]:
    """Heuristica original de deteccion de columnas."""
    fecha = next((c for c in df.columns if "fecha" in c.lower()), None)
    codigo = next(
        (c for c in df.columns if "codigo" in c.lower() or "código" in c.lower()), None
    )
    stock = next(
        (c for c in df.columns if "t.unid" in c.lower() or "unid" in c.lower()), None
    )
    if not all([fecha, codigo, stock]):
        raise FormatoEntradaError(
            f"No se detectaron columnas fecha/codigo/stock. Columnas: {list(df.columns)}"
        )
    return fecha, codigo, stock


def clasificar(frecuencia: float) -> str:
    if frecuencia == CLASE_MUERTO:
        return "Muerto"
    if frecuencia < CLASE_BAJA:
        return "Baja"
    if frecuencia < CLASE_MEDIA:
        return "Media"
    return "Alta"


def perfilar(
    df: pd.DataFrame,
    lead_time_dias: int = config.LEAD_TIME_DIAS,
    columnas: tuple[str, str, str] | None = None,
) -> list[dict]:
    """Un registro por producto con sus estadisticas de movimiento."""
    col_fecha, col_codigo, col_stock = columnas or detectar_columnas(df)

    df = df.copy()
    df["_fecha"] = df[col_fecha].apply(parse_fecha)
    sin_fecha = int(df["_fecha"].isna().sum())
    if sin_fecha:
        logger.warning("%s filas con fecha ilegible; se descartan", sin_fecha)
        df = df.dropna(subset=["_fecha"])

    df[col_stock] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0)
    df = df.sort_values([col_codigo, "_fecha"])

    productos: list[dict] = []
    for codigo, g in df.groupby(col_codigo):
        s = g[col_stock].astype(float).values
        if len(s) < 2:
            continue

        diffs = np.diff(s)
        cambios = int(np.sum(diffs != 0))
        frecuencia = cambios / max(len(s) - 1, 1)

        bajas = np.abs(diffs[diffs < 0])
        subidas = diffs[diffs > 0]

        consumo_promedio = float(bajas.mean()) if len(bajas) else 0.0
        stock_actual = float(s[-1])

        dias_hasta_agotarse = (
            stock_actual / consumo_promedio if consumo_promedio > 0 else None
        )

        productos.append(
            {
                "codigo": str(codigo),
                "clase": clasificar(frecuencia),
                "observaciones": len(s),
                "stock_actual": round(stock_actual, 2),
                "stock_inicial": round(float(s[0]), 2),
                "stock_promedio": round(float(np.mean(s)), 2),
                "consumo_promedio": round(consumo_promedio, 2),
                "consumo_maximo": round(float(bajas.max()) if len(bajas) else 0.0, 2),
                "consumo_minimo": round(float(bajas.min()) if len(bajas) else 0.0, 2),
                "reposicion_promedio": round(
                    float(subidas.mean()) if len(subidas) else 0.0, 2
                ),
                "reposicion_maxima": round(
                    float(subidas.max()) if len(subidas) else 0.0, 2
                ),
                "frecuencia_movimiento": round(frecuencia, 4),
                # Antes: `round(x,2) if dias_hasta_agotarse else None` convertia 0.0 en None
                "dias_hasta_agotarse": (
                    round(dias_hasta_agotarse, 2)
                    if dias_hasta_agotarse is not None
                    else None
                ),
                "punto_reorden": round(consumo_promedio * lead_time_dias, 2),
            }
        )

    return productos


def seleccionar_muestra(
    productos: list[dict],
    n_por_clase: int = N_POR_CLASE,
    semilla: int = SEMILLA_MUESTRA,
) -> list[dict]:
    """N productos por clase. Con semilla: la muestra es reproducible."""
    rng = np.random.default_rng(semilla)
    muestra: list[dict] = []
    for clase in ["Muerto", "Baja", "Media", "Alta"]:
        subset = [p for p in productos if p["clase"] == clase]
        n = min(n_por_clase, len(subset))
        if n < n_por_clase:
            logger.warning("Clase %s: solo %s productos disponibles", clase, len(subset))
        indices = rng.choice(len(subset), size=n, replace=False) if subset else []
        muestra.extend(subset[i] for i in indices)
    return muestra


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Perfila productos desde el historico")
    parser.add_argument(
        "--csv", type=Path, default=config.DATA_DIR / "raw/inventario_consolidado.csv"
    )
    parser.add_argument("--salida", type=Path, default=config.DATA_DIR / "interim")
    parser.add_argument("--n-por-clase", type=int, default=N_POR_CLASE)
    parser.add_argument("--semilla", type=int, default=SEMILLA_MUESTRA)
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"No se encontro {args.csv}")

    df = pd.read_csv(args.csv)
    productos = perfilar(df)
    muestra = seleccionar_muestra(productos, args.n_por_clase, args.semilla)

    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "productos_perfilados.json").write_text(
        json.dumps(productos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.salida / "productos_muestra.json").write_text(
        json.dumps(muestra, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    conteo = pd.Series([p["clase"] for p in muestra]).value_counts().to_dict()
    logger.info("Perfilados: %s | muestra: %s %s", len(productos), len(muestra), conteo)


if __name__ == "__main__":
    main()
