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
    location: str
    model: object
    scaler_x: MinMaxScaler | None
    scaler_y: MinMaxScaler | None
    history_dates: pd.Series
    history_total_stock: np.ndarray
    history_net_movement: np.ndarray
    last_window_features_scaled: np.ndarray
    last_net_movement_scaled: float
    test_dates: np.ndarray
    y_test_true: np.ndarray
    y_test_pred: np.ndarray


def _scale_features(features: np.ndarray, use_scaler: bool):
    # Escalar las 2 features de entrada: total_stock y net_movement.
    if not use_scaler:
        return features.copy(), None

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(features)
    return scaled, scaler


def _scale_target(target: np.ndarray, use_scaler: bool):
    # Escalar el objetivo (total_stock futuro) para estabilizar el entrenamiento.
    if not use_scaler:
        return target.copy(), None

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(target.reshape(-1, 1)).reshape(-1)
    return scaled, scaler


def _inverse(values: np.ndarray, scaler: MinMaxScaler | None) -> np.ndarray:
    # Revertir escala para reportar metricas y predicciones en unidades originales.
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
    """Train one LSTM model per location series."""
    artifacts: List[SeriesArtifact] = []
    metrics_rows: List[Dict] = []

    for location, group in stock_df.groupby(["location"]):
        group = group.sort_values("date").reset_index(drop=True)
        features = group[["total_stock", "net_movement"]].astype(float).values
        target = group["total_stock"].astype(float).values
        dates = group["date"].values

        if len(target) <= window_size + 5:
            continue

        split_idx = int(len(target) * 0.8)
        if split_idx <= window_size:
            continue

        # Escalar features y target por separado para poder invertir la prediccion correctamente.
        scaled_features, scaler_x = _scale_features(features, use_scaler=use_scaler)
        scaled_target, scaler_y = _scale_target(target, use_scaler=use_scaler)

        x_all, y_all = create_sliding_windows(scaled_features, scaled_target, window_size)
        target_positions = np.arange(window_size, len(target))

        train_mask = target_positions < split_idx
        test_mask = target_positions >= split_idx

        x_train, y_train = x_all[train_mask], y_all[train_mask]
        x_test, y_test = x_all[test_mask], y_all[test_mask]

        if len(x_train) == 0 or len(x_test) == 0:
            continue

        model = build_lstm_model(timesteps=window_size, features=2)
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

        y_test_true = _inverse(y_test, scaler_y)
        y_test_pred = _inverse(y_pred_scaled, scaler_y)

        mse = mean_squared_error(y_test_true, y_test_pred)
        mae = mean_absolute_error(y_test_true, y_test_pred)

        test_dates = dates[target_positions[test_mask]]
        last_window_features_scaled = scaled_features[-window_size:, :].copy()
        last_net_movement_scaled = float(scaled_features[-1, 1])

        artifacts.append(
            SeriesArtifact(
                location=location,
                model=model,
                scaler_x=scaler_x,
                scaler_y=scaler_y,
                history_dates=group["date"],
                history_total_stock=target,
                history_net_movement=group["net_movement"].astype(float).values,
                last_window_features_scaled=last_window_features_scaled,
                last_net_movement_scaled=last_net_movement_scaled,
                test_dates=test_dates,
                y_test_true=y_test_true,
                y_test_pred=y_test_pred,
            )
        )

        metrics_rows.append(
            {
                "location": location,
                "mse": mse,
                "mae": mae,
                "train_samples": int(len(x_train)),
                "test_samples": int(len(x_test)),
            }
        )

    metrics_df = pd.DataFrame(metrics_rows)
    if not metrics_df.empty:
        metrics_df = metrics_df.sort_values(["location"])
    return artifacts, metrics_df
