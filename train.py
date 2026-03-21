from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except ImportError as exc:
    raise RuntimeError(
        "PyTorch no esta disponible en el interprete actual. "
        "Usa un entorno compatible, preferiblemente Python 3.12, "
        "e instala las dependencias antes de ejecutar el entrenamiento."
    ) from exc

from model import InventoryForecastGRU
from preprocessing import create_sliding_windows


@dataclass
class AutoTrainingConfig:
    num_files: int
    detected_days: int
    valid_records: int
    num_locations: int
    median_days_per_series: int
    min_days_per_series: int
    total_sequences_estimate: int
    window_size: int
    forecast_days: int
    epochs: int
    batch_size: int
    use_scaler: bool
    train_split_ratio: float
    validation_ratio: float
    explanation: Dict[str, str]


@dataclass
class SeriesArtifact:
    location: str
    model: InventoryForecastGRU
    device: str
    scaler_x: MinMaxScaler | None
    scaler_y: MinMaxScaler | None
    history_dates: pd.Series
    history_total_stock: np.ndarray
    history_net_movement: np.ndarray
    last_window_raw: np.ndarray
    future_movement_assumption: float
    test_dates: np.ndarray
    y_test_true: np.ndarray
    y_test_pred: np.ndarray
    train_samples: int
    validation_samples: int
    test_samples: int


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def auto_configure_training_params(
    stock_df: pd.DataFrame,
    num_files: int,
) -> AutoTrainingConfig:
    """Infer training parameters from the available historical data."""
    if stock_df.empty:
        raise ValueError("No hay datos disponibles para configurar el entrenamiento.")

    series_lengths = stock_df.groupby("location")["date"].nunique().sort_values()
    if series_lengths.empty:
        raise ValueError("No se pudieron detectar series temporales por ubicacion.")

    detected_days = int(stock_df["date"].nunique())
    valid_records = int(len(stock_df))
    num_locations = int(stock_df["location"].nunique())
    median_days = int(series_lengths.median())
    min_days = int(series_lengths.min())

    if min_days < 8:
        raise ValueError(
            "No hay suficientes datos para entrenar. "
            f"La serie mas corta solo tiene {min_days} dias y se requieren al menos 8."
        )

    max_window_allowed = max(5, min_days - 3)
    base_window = max(5, median_days // 3)
    window_size = _clamp(base_window, 5, min(45, max_window_allowed))

    usable_sequences = [max(0, int(length) - window_size) for length in series_lengths.tolist()]
    total_sequences_estimate = int(sum(usable_sequences))
    if total_sequences_estimate < 4:
        raise ValueError(
            "No hay suficientes secuencias para entrenar despues de crear ventanas "
            f"temporales con window_size={window_size}."
        )

    horizon_cap = min(30, max(1, min_days // 3))
    data_limited_horizon = max(1, min(median_days // 4, horizon_cap))
    forecast_days = _clamp(data_limited_horizon, 1, horizon_cap)

    if total_sequences_estimate < 32:
        epochs = 120
        batch_size = 4
    elif total_sequences_estimate < 96:
        epochs = 90
        batch_size = 8
    elif total_sequences_estimate < 256:
        epochs = 60
        batch_size = 16
    else:
        epochs = 40
        batch_size = 32

    batch_size = min(batch_size, max(4, total_sequences_estimate))
    use_scaler = True

    explanation = {
        "window_size": (
            "Se calcula con base en la mediana de dias historicos por serie y se limita "
            "para no consumir demasiada historia en datasets pequenos."
        ),
        "forecast_days": (
            "Se limita por la serie mas corta y por un maximo de 30 dias para evitar "
            "proyecciones excesivas cuando hay poco historial."
        ),
        "epochs": (
            "A menos secuencias disponibles, mas epocas para permitir convergencia; "
            "a mas datos, menos epocas para evitar sobreentrenamiento."
        ),
        "batch_size": (
            "Se ajusta al numero estimado de secuencias y se mantiene pequeno en "
            "datasets cortos para no perder estabilidad."
        ),
        "scaling": (
            "Se usa MinMaxScaler automaticamente para estabilizar el entrenamiento y "
            "luego se aplica inverse_transform en las predicciones."
        ),
    }

    return AutoTrainingConfig(
        num_files=int(num_files),
        detected_days=detected_days,
        valid_records=valid_records,
        num_locations=num_locations,
        median_days_per_series=median_days,
        min_days_per_series=min_days,
        total_sequences_estimate=total_sequences_estimate,
        window_size=window_size,
        forecast_days=forecast_days,
        epochs=epochs,
        batch_size=batch_size,
        use_scaler=use_scaler,
        train_split_ratio=0.8,
        validation_ratio=0.15,
        explanation=explanation,
    )


def _fit_feature_scaler(train_features: np.ndarray, use_scaler: bool) -> MinMaxScaler | None:
    if not use_scaler:
        return None
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaler.fit(train_features)
    return scaler


def _fit_target_scaler(train_target: np.ndarray, use_scaler: bool) -> MinMaxScaler | None:
    if not use_scaler:
        return None
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaler.fit(train_target.reshape(-1, 1))
    return scaler


def _transform_features(features: np.ndarray, scaler: MinMaxScaler | None) -> np.ndarray:
    if scaler is None:
        return features.astype(np.float32)
    return scaler.transform(features).astype(np.float32)


def _transform_target(target: np.ndarray, scaler: MinMaxScaler | None) -> np.ndarray:
    if scaler is None:
        return target.astype(np.float32)
    return scaler.transform(target.reshape(-1, 1)).reshape(-1).astype(np.float32)


def inverse_target(values: np.ndarray, scaler: MinMaxScaler | None) -> np.ndarray:
    """Return target values in the original stock scale."""
    if scaler is None:
        return values
    return scaler.inverse_transform(values.reshape(-1, 1)).reshape(-1)


def _build_loaders(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    batch_size: int,
) -> Tuple[DataLoader, DataLoader | None]:
    train_dataset = TensorDataset(
        torch.tensor(x_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.float32),
    )
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)

    if len(x_val) == 0:
        return train_loader, None

    val_dataset = TensorDataset(
        torch.tensor(x_val, dtype=torch.float32),
        torch.tensor(y_val, dtype=torch.float32),
    )
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    return train_loader, val_loader


def _evaluate_loss(model: nn.Module, loader: DataLoader, criterion: nn.Module, device: str) -> float:
    model.eval()
    losses: List[float] = []
    with torch.no_grad():
        for features, target in loader:
            features = features.to(device)
            target = target.to(device)
            prediction = model(features)
            losses.append(float(criterion(prediction, target).item()))
    return float(np.mean(losses)) if losses else float("inf")


def _train_torch_model(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    config: AutoTrainingConfig,
    input_size: int,
) -> Tuple[InventoryForecastGRU, str]:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = InventoryForecastGRU(input_size=input_size)
    model.to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    train_loader, val_loader = _build_loaders(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        batch_size=config.batch_size,
    )

    best_state = deepcopy(model.state_dict())
    best_loss = float("inf")
    patience = max(6, config.epochs // 6)
    epochs_without_improvement = 0

    for _ in range(config.epochs):
        model.train()
        for features, target in train_loader:
            features = features.to(device)
            target = target.to(device)

            optimizer.zero_grad()
            prediction = model(features)
            loss = criterion(prediction, target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        current_loss = (
            _evaluate_loss(model, val_loader, criterion, device)
            if val_loader is not None
            else _evaluate_loss(model, train_loader, criterion, device)
        )

        if current_loss + 1e-6 < best_loss:
            best_loss = current_loss
            best_state = deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        if epochs_without_improvement >= patience:
            break

    model.load_state_dict(best_state)
    model.eval()
    return model, device


def _predict_scaled(model: InventoryForecastGRU, x_data: np.ndarray, device: str) -> np.ndarray:
    if len(x_data) == 0:
        return np.asarray([], dtype=np.float32)

    tensor_x = torch.tensor(x_data, dtype=torch.float32).to(device)
    with torch.no_grad():
        prediction = model(tensor_x).detach().cpu().numpy()
    return prediction.reshape(-1)


def train_group_models(
    stock_df: pd.DataFrame,
    config: AutoTrainingConfig,
) -> Tuple[List[SeriesArtifact], pd.DataFrame]:
    """Train one PyTorch forecasting model per location."""
    artifacts: List[SeriesArtifact] = []
    metrics_rows: List[Dict[str, float | int | str]] = []

    for location, group in stock_df.groupby("location"):
        group = group.sort_values("date").reset_index(drop=True)
        features_raw = group[["total_stock", "net_movement"]].astype(float).values
        target_raw = group["total_stock"].astype(float).values
        dates = group["date"].values

        if len(target_raw) <= config.window_size + 3:
            continue

        split_idx = max(config.window_size + 1, int(len(target_raw) * config.train_split_ratio))
        if split_idx >= len(target_raw):
            split_idx = len(target_raw) - 1
        if split_idx <= config.window_size:
            continue

        train_features_raw = features_raw[:split_idx]
        train_target_raw = target_raw[:split_idx]
        scaler_x = _fit_feature_scaler(train_features_raw, config.use_scaler)
        scaler_y = _fit_target_scaler(train_target_raw, config.use_scaler)

        scaled_features = _transform_features(features_raw, scaler_x)
        scaled_target = _transform_target(target_raw, scaler_y)

        x_all, y_all = create_sliding_windows(
            features=scaled_features,
            target=scaled_target,
            window_size=config.window_size,
        )
        target_positions = np.arange(config.window_size, len(target_raw))

        train_mask = target_positions < split_idx
        test_mask = target_positions >= split_idx
        x_train_full, y_train_full = x_all[train_mask], y_all[train_mask]
        x_test, y_test = x_all[test_mask], y_all[test_mask]

        if len(x_train_full) < 2 or len(x_test) == 0:
            continue

        val_size = int(len(x_train_full) * config.validation_ratio)
        if val_size >= len(x_train_full):
            val_size = max(0, len(x_train_full) - 1)

        if val_size > 0:
            x_train = x_train_full[:-val_size]
            y_train = y_train_full[:-val_size]
            x_val = x_train_full[-val_size:]
            y_val = y_train_full[-val_size:]
        else:
            x_train, y_train = x_train_full, y_train_full
            x_val = np.empty((0, config.window_size, x_train_full.shape[2]), dtype=np.float32)
            y_val = np.empty((0,), dtype=np.float32)

        model, device = _train_torch_model(
            x_train=x_train,
            y_train=y_train,
            x_val=x_val,
            y_val=y_val,
            config=config,
            input_size=features_raw.shape[1],
        )

        y_pred_scaled = _predict_scaled(model, x_test, device)
        y_test_true = inverse_target(y_test, scaler_y)
        y_test_pred = inverse_target(y_pred_scaled, scaler_y)

        rmse = float(np.sqrt(mean_squared_error(y_test_true, y_test_pred)))
        mae = float(mean_absolute_error(y_test_true, y_test_pred))
        test_dates = dates[target_positions[test_mask]]

        recent_movements = group["net_movement"].astype(float).tail(min(7, len(group)))
        movement_assumption = float(recent_movements.mean()) if not recent_movements.empty else 0.0

        artifacts.append(
            SeriesArtifact(
                location=str(location),
                model=model,
                device=device,
                scaler_x=scaler_x,
                scaler_y=scaler_y,
                history_dates=group["date"],
                history_total_stock=target_raw,
                history_net_movement=group["net_movement"].astype(float).values,
                last_window_raw=features_raw[-config.window_size :, :].copy(),
                future_movement_assumption=movement_assumption,
                test_dates=test_dates,
                y_test_true=y_test_true,
                y_test_pred=y_test_pred,
                train_samples=int(len(x_train)),
                validation_samples=int(len(x_val)),
                test_samples=int(len(x_test)),
            )
        )

        metrics_rows.append(
            {
                "location": str(location),
                "rmse": rmse,
                "mae": mae,
                "train_samples": int(len(x_train)),
                "validation_samples": int(len(x_val)),
                "test_samples": int(len(x_test)),
            }
        )

    metrics_df = pd.DataFrame(metrics_rows)
    if not metrics_df.empty:
        metrics_df = metrics_df.sort_values("location").reset_index(drop=True)
    return artifacts, metrics_df
