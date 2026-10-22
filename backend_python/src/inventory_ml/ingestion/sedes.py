"""Perfil por (sede, producto) a partir de los Excel diarios reales.

El perfilado general usa T.Unid (la suma de todas las sedes). Aqui se perfila
cada columna de sede por separado con la MISMA funcion `perfilar`, asi que el
modelo activo puntua una sede exactamente igual que puntua el total: no hace
falta reentrenar.

Va a una base aparte (sedes.db) y no a inventario.db: "simular un ano" desde
la interfaz reemplaza inventario.db entero y se llevaria esta tabla.

Entrada:  data/raw/inventarios/D_M_AAAA.xlsx  (una columna por sede)
Salida:   data/sedes.db, tabla perfil_sede

Uso:
    python -m inventory_ml.ingestion.sedes
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from inventory_ml import config
from inventory_ml.ingestion.perfilado import parse_fecha, perfilar

logger = logging.getLogger(__name__)

COLUMNAS_NO_SEDE = ["Descripción", "Costo", "T.Unid", "T.Costo"]


def _leer(ruta: Path) -> pd.DataFrame:
    df = pd.read_excel(ruta).drop(columns=COLUMNAS_NO_SEDE, errors="ignore")
    df["Fecha"] = ruta.stem  # el nombre del archivo ES la fecha: D_M_AAAA
    return df


def perfilar_sedes(carpeta: Path) -> tuple[pd.DataFrame, str]:
    """Devuelve (perfiles, fecha_del_ultimo_snapshot)."""
    archivos = sorted(carpeta.glob("*.xlsx"))
    if not archivos:
        raise SystemExit(f"No hay .xlsx en {carpeta}")
    # openpyxl tarda ~4 s por archivo; en paralelo se reparte entre nucleos.
    with ProcessPoolExecutor() as pool:
        df = pd.concat(pool.map(_leer, archivos), ignore_index=True)

    sedes = [c for c in df.columns if c not in ("Código", "Fecha")]
    df[sedes] = df[sedes].apply(pd.to_numeric, errors="coerce").fillna(0).astype("int32")
    fecha = max(parse_fecha(f) for f in df["Fecha"].unique()).date().isoformat()
    logger.info("%s snapshots, %s filas, sedes: %s", len(archivos), len(df), sedes)

    perfiles = []
    for sede in sedes:
        sub = df[["Fecha", "Código", sede]]
        # Un producto que nunca tuvo stock en la sede no es riesgo de nada ahi
        con_stock = sub.loc[sub[sede] != 0, "Código"].unique()
        sub = sub[sub["Código"].isin(con_stock)]
        p = pd.DataFrame(perfilar(sub, columnas=("Fecha", "Código", sede)))
        p.insert(0, "sede", sede)
        perfiles.append(p)
        logger.info("Sede %s: %s productos", sede, len(p))

    return pd.concat(perfiles, ignore_index=True), fecha


def guardar(perfiles: pd.DataFrame, fecha: str, db_path: Path) -> None:
    perfiles = perfiles.assign(fecha=fecha)
    with sqlite3.connect(db_path) as conn:
        perfiles.to_sql("perfil_sede", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX idx_perfil_sede ON perfil_sede(sede, codigo)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Perfila productos por sede")
    parser.add_argument("--carpeta", type=Path, default=config.DATA_DIR / "raw/inventarios")
    parser.add_argument("--db", type=Path, default=config.SEDES_DB_PATH)
    args = parser.parse_args()

    perfiles, fecha = perfilar_sedes(args.carpeta)
    guardar(perfiles, fecha, args.db)
    logger.info("Guardados %s perfiles (fecha %s) en %s", len(perfiles), fecha, args.db)


if __name__ == "__main__":
    main()
