from typing import Tuple

import numpy as np
import pandas as pd


TOTAL_WORDS = ("total", "subtotal", "resumen", "sum", "grand total", "totales")


def clean_inventory_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean raw long-format inventory rows."""
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["product"] = out["product"].astype(str).str.strip()
    out["location"] = out["location"].astype(str).str.strip()

    out["movement"] = pd.to_numeric(out["movement"], errors="coerce")

    out = out.dropna(subset=["date", "product", "location", "movement"])
    out = out[(out["product"] != "") & (out["location"] != "")]

    lower_product = out["product"].str.lower()
    totals_mask = lower_product.apply(lambda x: any(w in x for w in TOTAL_WORDS))
    out = out[~totals_mask].copy()

    return out


def aggregate_if_needed(df: pd.DataFrame, per_location: bool = True) -> pd.DataFrame:
    """Optionally aggregate movements across locations."""
    if per_location:
        return df

    grouped = (
        df.groupby(["date", "product"], as_index=False)["movement"]
        .sum()
        .assign(location="ALL")
    )
    return grouped[["date", "product", "location", "movement"]]


def build_stock_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Build cumulative stock and regularize to daily frequency."""
    grouped = (
        df.groupby(["date", "product", "location"], as_index=False)["movement"]
        .sum()
        .sort_values(["product", "location", "date"])
    )

    all_parts = []
    for (product, location), group in grouped.groupby(["product", "location"]):
        group = group.sort_values("date").copy()
        full_dates = pd.date_range(group["date"].min(), group["date"].max(), freq="D")

        daily = group.set_index("date").reindex(full_dates)
        daily["movement"] = daily["movement"].fillna(0.0)
        daily["product"] = product
        daily["location"] = location
        daily = daily.rename_axis("date").reset_index()
        daily["stock"] = daily["movement"].cumsum()

        all_parts.append(daily[["date", "product", "location", "movement", "stock"]])

    out = pd.concat(all_parts, ignore_index=True)
    out = out.sort_values(["product", "location", "date"]).reset_index(drop=True)
    return out


def create_sliding_windows(series: np.ndarray, window_size: int) -> Tuple[np.ndarray, np.ndarray]:
    """Create (X, y) arrays using a rolling window over a 1D series."""
    if len(series) <= window_size:
        return np.empty((0, window_size, 1)), np.empty((0,))

    x_list, y_list = [], []
    for idx in range(window_size, len(series)):
        x_list.append(series[idx - window_size : idx])
        y_list.append(series[idx])

    x_arr = np.array(x_list).reshape(-1, window_size, 1)
    y_arr = np.array(y_list).reshape(-1)
    return x_arr, y_arr
