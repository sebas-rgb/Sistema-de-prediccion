from typing import Tuple

import numpy as np
import pandas as pd


def clean_inventory_data(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize inventory rows and drop invalid records."""
    output = df.copy()
    output["date"] = pd.to_datetime(output["date"], errors="coerce")
    output["location"] = output["location"].astype(str).str.strip()
    output["total_stock"] = pd.to_numeric(output["total_stock"], errors="coerce")
    output["net_movement"] = pd.to_numeric(output["net_movement"], errors="coerce")

    output = output.dropna(subset=["date", "location", "total_stock", "net_movement"])
    output = output[output["location"] != ""].copy()

    if output.empty:
        raise ValueError("No quedaron registros validos despues de limpiar los datos.")

    return output[["date", "location", "total_stock", "net_movement"]]


def aggregate_if_needed(df: pd.DataFrame, per_location: bool = True) -> pd.DataFrame:
    """Keep series by location or aggregate them into one global series."""
    if per_location:
        return df.copy()

    grouped = (
        df.groupby(["date"], as_index=False)[["total_stock", "net_movement"]]
        .sum()
        .assign(location="ALL")
    )
    return grouped[["date", "location", "total_stock", "net_movement"]]


def build_stock_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Regularize each location series to a daily frequency."""
    if df.empty:
        raise ValueError("No hay datos para construir el dataset consolidado.")

    grouped = df.sort_values(["location", "date"]).copy()
    all_parts = []

    for location, group in grouped.groupby("location"):
        group = group.sort_values("date").copy()
        full_dates = pd.date_range(group["date"].min(), group["date"].max(), freq="D")
        daily = group.set_index("date").reindex(full_dates)

        daily["total_stock"] = daily["total_stock"].ffill().bfill()
        daily["net_movement"] = daily["net_movement"].fillna(0.0)
        daily["location"] = str(location)
        daily = daily.rename_axis("date").reset_index()

        all_parts.append(daily[["date", "location", "total_stock", "net_movement"]])

    output = pd.concat(all_parts, ignore_index=True)
    output = output.sort_values(["location", "date"]).reset_index(drop=True)
    return output


def create_sliding_windows(
    features: np.ndarray,
    target: np.ndarray,
    window_size: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Create sequential windows for one-step forecasting."""
    if len(features) <= window_size:
        return (
            np.empty((0, window_size, features.shape[1]), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
        )

    x_list, y_list = [], []
    for idx in range(window_size, len(features)):
        x_list.append(features[idx - window_size : idx, :])
        y_list.append(target[idx])

    return (
        np.asarray(x_list, dtype=np.float32),
        np.asarray(y_list, dtype=np.float32),
    )
