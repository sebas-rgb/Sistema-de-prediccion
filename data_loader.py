import re
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

TOTALS_PATTERN = re.compile(r"totales?\s*:", flags=re.IGNORECASE)
NON_LOCATION_COLUMNS = {"codigo", "descripcion", "t.unid", "t.costo"}


def extract_date_from_filename(filename: str) -> pd.Timestamp:
    """Extract the report date from the Excel filename."""
    basename = Path(filename).name
    match = re.search(r"(\d{1,2})[_-](\d{1,2})[_-](\d{4})", basename)

    if not match:
        raise ValueError(
            "No se pudo extraer la fecha desde el nombre del archivo "
            f"'{basename}'. Se esperaba un formato tipo d_m_yyyy o d-m-yyyy."
        )

    day, month, year = match.groups()
    return pd.Timestamp(datetime(int(year), int(month), int(day)))


def list_excel_files(data_dir: str) -> List[Path]:
    """Return all Excel files in a directory, sorted by name."""
    base = Path(data_dir)
    files = sorted([*base.glob("*.xlsx"), *base.glob("*.xls")])
    if not files:
        raise FileNotFoundError(
            f"No se encontraron archivos Excel en: {base.resolve()}"
        )
    return files


def _is_totals_row(row: pd.Series) -> bool:
    """Detect whether a row contains the Totales marker."""
    row_text = " | ".join(row.fillna("").astype(str).tolist())
    return bool(TOTALS_PATTERN.search(row_text))


def _location_columns(df: pd.DataFrame) -> List[str]:
    """Detect location columns while skipping known metadata columns."""
    columns: List[str] = []
    for col in df.columns:
        name = str(col).strip()
        if not name:
            continue
        if name.lower() in NON_LOCATION_COLUMNS:
            continue
        columns.append(name)
    return columns


def load_single_excel(file_path: Path | str) -> pd.DataFrame:
    """Load one Excel file and return the daily stock summary by location."""
    source_name = getattr(file_path, "name", str(file_path))
    display_name = Path(str(source_name)).name
    report_date = extract_date_from_filename(str(source_name))
    raw_df = pd.read_excel(file_path)

    if raw_df.empty:
        raise ValueError(f"El archivo '{display_name}' no contiene datos.")

    totals_mask = raw_df.apply(_is_totals_row, axis=1)
    if not totals_mask.any():
        raise ValueError(
            f"No se encontro la fila 'Totales:' en el archivo '{display_name}'."
        )

    totals_idx = totals_mask[totals_mask].index[0]
    location_cols = _location_columns(raw_df)
    if not location_cols:
        raise ValueError(
            f"No se encontraron columnas de ubicacion en el archivo '{display_name}'."
        )

    totals_row = raw_df.loc[totals_idx, location_cols]
    total_stock = pd.to_numeric(totals_row, errors="coerce").fillna(0.0)

    movement_rows = raw_df.loc[totals_idx + 1 :, location_cols]
    movement_numeric = movement_rows.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    net_movement = movement_numeric.sum(axis=0)

    daily_frame = pd.DataFrame(
        {
            "date": report_date,
            "location": total_stock.index.astype(str).str.strip(),
            "total_stock": total_stock.values.astype(float),
            "net_movement": net_movement.values.astype(float),
        }
    )

    return daily_frame[["date", "location", "total_stock", "net_movement"]]


def load_inventory_files(data_dir: str) -> pd.DataFrame:
    """Load and consolidate all daily Excel files into one inventory dataset."""
    files = list_excel_files(data_dir)
    frames = [load_single_excel(file_path) for file_path in files]
    df = pd.concat(frames, ignore_index=True)
    df["location"] = df["location"].astype(str).str.strip()
    return df[["date", "location", "total_stock", "net_movement"]]
