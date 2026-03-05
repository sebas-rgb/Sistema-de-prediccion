from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler

from model import build_lstm_model
from preprocessing import create_sliding_windows


@dataclass
class SeriesArtifact:
    product: str
    location: str
    model: object
    scaler: MinMaxScaler | None
    history_dates: pd.Series
    history_stock: np.ndarray
    last_window_scaled: np.ndarray
    test_dates: np.ndarray
    y_test_true: np.ndarray
    y_test_pred: np.ndarray


def _scale_series(series: np.ndarray, use_scaler: bool):
    if not use_scaler:
        return series.copy(), None

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(series.reshape(-1, 1)).reshape(-1)
    return scaled, scaler


def _inverse(values: np.ndarray, scaler: MinMaxScaler | None) -> np.ndarray:
    if scaler is None:
        return values
    return scaler.inverse_transform(values.reshape(-1, 1)).reshape(-1)


def train_group_models(
    stock_df: pd.DataFrame,
    window_size: int = 30,
    epochs: int = 30,
    batch_size: int = 32,
    use_scaler: bool = True,
) -> Tuple[List[SeriesArtifact], pd.DataFrame]:
    """Train one LSTM model per product/location series."""
    artifacts: List[SeriesArtifact] = []
    metrics_rows: List[Dict] = []

    for (product, location), group in stock_df.groupby(["product", "location"]):
        group = group.sort_values("date").reset_index(drop=True)
        series = group["stock"].astype(float).values
        dates = group["date"].values

        if len(series) <= window_size + 5:
            continue

        split_idx = int(len(series) * 0.8)
        if split_idx <= window_size:
            continue

        scaled_series, scaler = _scale_series(series, use_scaler=use_scaler)

        x_all, y_all = create_sliding_windows(scaled_series, window_size)
        target_positions = np.arange(window_size, len(scaled_series))

        train_mask = target_positions < split_idx
        test_mask = target_positions >= split_idx

        x_train, y_train = x_all[train_mask], y_all[train_mask]
        x_test, y_test = x_all[test_mask], y_all[test_mask]

        if len(x_train) == 0 or len(x_test) == 0:
            continue

        model = build_lstm_model(timesteps=window_size, features=1)
        model.fit(
            x_train,
            y_train,
            epochs=epochs,
            batch_size=batch_size,
            verbose=0,
            validation_split=0.1,
            shuffle=False,
        )

        y_pred_scaled = model.predict(x_test, verbose=0).reshape(-1)

        y_test_true = _inverse(y_test, scaler)
        y_test_pred = _inverse(y_pred_scaled, scaler)

        mse = mean_squared_error(y_test_true, y_test_pred)
        mae = mean_absolute_error(y_test_true, y_test_pred)

        test_dates = dates[target_positions[test_mask]]
        last_window_scaled = scaled_series[-window_size:].copy()

        artifacts.append(
            SeriesArtifact(
                product=product,
                location=location,
                model=model,
                scaler=scaler,
                history_dates=group["date"],
                history_stock=series,
                last_window_scaled=last_window_scaled,
                test_dates=test_dates,
                y_test_true=y_test_true,
                y_test_pred=y_test_pred,
            )
        )

        metrics_rows.append(
            {
                "product": product,
                "location": location,
                "mse": mse,
                "mae": mae,
                "train_samples": int(len(x_train)),
                "test_samples": int(len(x_test)),
            }
        )

    metrics_df = pd.DataFrame(metrics_rows).sort_values(["product", "location"])
    return artifacts, metrics_df
