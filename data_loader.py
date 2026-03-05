import re
from pathlib import Path
from typing import List
from datetime import datetime

import pandas as pd

TOTALS_PATTERN = re.compile(r"totales?\s*:", flags=re.IGNORECASE)
NON_LOCATION_COLUMNS = {"codigo", "descripcion", "t.unid", "t.costo"}


def extract_date_from_filename(filename: str) -> pd.Timestamp:
    # Extraer la fecha del nombre de archivo con formato d_m_yyyy o d-m-yyyy.
    filename = Path(filename).name

    match = re.search(r'(\d{1,2})[_-](\d{1,2})[_-](\d{4})', filename)

    if not match:
        raise ValueError(f"No se encontró fecha en el nombre: {filename}")

    day, month, year = match.groups()

    return datetime(int(year), int(month), int(day))

def list_excel_files(data_dir: str) -> List[Path]:
    """Return all Excel files in a directory, sorted by name."""
    base = Path(data_dir)
    files = sorted([*base.glob("*.xlsx"), *base.glob("*.xls")])
    if not files:
        raise FileNotFoundError(f"No Excel files found in: {base.resolve()}")
    return files


def _is_totals_row(row: pd.Series) -> bool:
    # Detectar la fila "Totales:" buscando la marca en cualquier celda de la fila.
    row_text = " | ".join(row.fillna("").astype(str).tolist())
    return bool(TOTALS_PATTERN.search(row_text))


def _location_columns(df: pd.DataFrame) -> List[str]:
    # Identificar columnas de ubicacion excluyendo metadatos conocidos.
    cols: List[str] = []
    for col in df.columns:
        name = str(col).strip()
        if not name:
            continue
        if name.lower() in NON_LOCATION_COLUMNS:
            continue
        cols.append(name)
    return cols


def load_single_excel(file_path: Path | str) -> pd.DataFrame:
    """Load one Excel file and return date/location totals and movements."""
    # Extraer la fecha del dia desde el nombre del archivo.
    source_name = getattr(file_path, "name", str(file_path))
    display_name = Path(str(source_name)).name
    date = extract_date_from_filename(str(source_name))
    raw_df = pd.read_excel(file_path)

    if raw_df.empty:
        raise ValueError(f"El archivo {display_name} no contiene datos.")

    # Buscar la fila que contiene "Totales:" para separar stock total y movimientos diarios.
    totals_mask = raw_df.apply(_is_totals_row, axis=1)
    if not totals_mask.any():
        raise ValueError(f"No se encontro la fila 'Totales:' en {display_name}.")

    totals_idx = totals_mask[totals_mask].index[0]
    location_cols = _location_columns(raw_df)
    if not location_cols:
        raise ValueError(f"No se encontraron columnas de ubicacion en {display_name}.")

    # Extraer el stock total del dia por ubicacion desde la fila "Totales:".
    totals_row = raw_df.loc[totals_idx, location_cols]
    total_stock = pd.to_numeric(totals_row, errors="coerce").fillna(0.0)

    # Calcular el movimiento neto diario sumando todos los productos debajo de "Totales:".
    movement_rows = raw_df.loc[totals_idx + 1 :, location_cols]
    movement_numeric = movement_rows.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    net_movement = movement_numeric.sum(axis=0)

    day_df = pd.DataFrame(
        {
            "date": date,
            "location": total_stock.index.astype(str).str.strip(),
            "total_stock": total_stock.values.astype(float),
            "net_movement": net_movement.values.astype(float),
        }
    )
    return day_df[["date", "location", "total_stock", "net_movement"]]


def load_inventory_files(data_dir: str) -> pd.DataFrame:
    """Load and stack all inventory files in date/location format."""
    # Cargar todos los archivos diarios y unirlos en un unico dataset.
    files = list_excel_files(data_dir)
    frames = [load_single_excel(file_path) for file_path in files]
    df = pd.concat(frames, ignore_index=True)

    df["location"] = df["location"].astype(str).str.strip()

    return df[["date", "location", "total_stock", "net_movement"]]
