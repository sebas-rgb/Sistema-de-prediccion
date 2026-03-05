from typing import Tuple

import numpy as np
import pandas as pd


def clean_inventory_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean raw inventory rows in date/location format."""
    # Normalizar tipos y limpiar campos para dejar el dataset listo para modelado.
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["location"] = out["location"].astype(str).str.strip()
    out["total_stock"] = pd.to_numeric(out["total_stock"], errors="coerce")
    out["net_movement"] = pd.to_numeric(out["net_movement"], errors="coerce")

    out = out.dropna(subset=["date", "location", "total_stock", "net_movement"])
    out = out[out["location"] != ""].copy()
    return out[["date", "location", "total_stock", "net_movement"]]


def aggregate_if_needed(df: pd.DataFrame, per_location: bool = True) -> pd.DataFrame:
    """Optionally aggregate series across locations."""
    # Mantener series por ubicacion o consolidar todo en una sola serie "ALL".
    if per_location:
        return df

    grouped = (
        df.groupby(["date"], as_index=False)[["total_stock", "net_movement"]]
        .sum()
        .assign(location="ALL")
    )
    return grouped[["date", "location", "total_stock", "net_movement"]]


def build_stock_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Regularize the dataset to daily frequency per location."""
    # Construir el dataset final con columnas: date, location, total_stock, net_movement.

    grouped = df.sort_values(["location", "date"]).copy()

    all_parts = []
    for location_key, group in grouped.groupby(["location"]):
        # groupby(["location"]) devuelve la llave como tupla: ('Centro',)
        # Normalizamos para quedarnos con el string de la sede.
        if isinstance(location_key, tuple):
            location = location_key[0]
        elif isinstance(location_key, (list, pd.Index)):
            location = location_key[0] if len(location_key) else "ALL"
        else:
            location = location_key

        group = group.sort_values("date").copy()
        full_dates = pd.date_range(group["date"].min(), group["date"].max(), freq="D")

        # Completar días faltantes para que cada serie tenga frecuencia diaria continua.
        daily = group.set_index("date").reindex(full_dates)

        # Rellenar stock total: si falta un día, asumimos que se mantiene el último valor conocido.
        daily["total_stock"] = daily["total_stock"].ffill().bfill()

        # Movimiento neto: si falta un día, asumimos 0 movimiento.
        daily["net_movement"] = daily["net_movement"].fillna(0.0)

        # Asignar la sede como escalar (string) a todas las filas del DataFrame diario.
        daily["location"] = str(location)

        # Volver a columnas normales
        daily = daily.rename_axis("date").reset_index()

        all_parts.append(daily[["date", "location", "total_stock", "net_movement"]])

    out = pd.concat(all_parts, ignore_index=True)
    out = out.sort_values(["location", "date"]).reset_index(drop=True)
    return out

def create_sliding_windows(
    features: np.ndarray,
    target: np.ndarray,
    window_size: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Create (X, y) arrays from multivariate features and a univariate target."""
    # Crear ventanas temporales para entrenar con 2 features y predecir el stock total futuro.
    if len(features) <= window_size:
        return np.empty((0, window_size, features.shape[1])), np.empty((0,))

    x_list, y_list = [], []
    for idx in range(window_size, len(features)):
        x_list.append(features[idx - window_size : idx, :])
        y_list.append(target[idx])

    x_arr = np.array(x_list).reshape(-1, window_size, features.shape[1])
    y_arr = np.array(y_list).reshape(-1)
    return x_arr, y_arr
