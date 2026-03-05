import re
from pathlib import Path
from typing import List
from datetime import datetime

import pandas as pd

DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
TOTAL_PATTERNS = re.compile(
    r"total|subtotal|resumen|sum|grand\s*total|totales",
    flags=re.IGNORECASE,
)


def extract_date_from_filename(filename: str) -> pd.Timestamp:
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


def load_single_excel(file_path: Path) -> pd.DataFrame:
    """Load one Excel file and return long format rows with file date."""
    date = extract_date_from_filename(file_path)
    raw_df = pd.read_excel(file_path)

    if raw_df.shape[1] < 2:
        raise ValueError(f"Expected at least 2 columns in {file_path.name}")

    product_col = raw_df.columns[0]
    df = raw_df.rename(columns={product_col: "product"}).copy()

    long_df = df.melt(
        id_vars=["product"],
        var_name="location",
        value_name="movement",
    )
    long_df["date"] = date

    return long_df[["date", "product", "location", "movement"]]


def load_inventory_files(data_dir: str) -> pd.DataFrame:
    """Load and stack all inventory files in long format."""
    files = list_excel_files(data_dir)
    frames = [load_single_excel(file_path) for file_path in files]
    df = pd.concat(frames, ignore_index=True)

    df["product"] = df["product"].astype(str).str.strip()
    df["location"] = df["location"].astype(str).str.strip()

    total_mask = df["product"].str.contains(TOTAL_PATTERNS, na=False)
    df = df[~total_mask].copy()

    return df
