from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from train import SeriesArtifact


def _inverse(values: np.ndarray, scaler):
    # Revertir escala de salida para devolver predicciones en unidades reales de stock.
    if scaler is None:
        return values
    return scaler.inverse_transform(values.reshape(-1, 1)).reshape(-1)


def recursive_forecast(artifact: SeriesArtifact, steps: int = 30) -> np.ndarray:
    """Forecast future stock recursively using the last known 2-feature window."""
    # Usar la ultima ventana [total_stock, net_movement] para predecir dias futuros.
    current_window = artifact.last_window_features_scaled.copy()
    preds_scaled = []

    for _ in range(steps):
        model_input = current_window.reshape(1, current_window.shape[0], current_window.shape[1])
        next_scaled = artifact.model.predict(model_input, verbose=0).reshape(-1)[0]
        preds_scaled.append(next_scaled)

        # Mantener un supuesto simple para movimiento neto futuro: ultimo valor observado.
        next_row = np.array([next_scaled, artifact.last_net_movement_scaled], dtype=float)
        current_window = np.vstack([current_window[1:, :], next_row])

    preds_scaled = np.array(preds_scaled)
    return _inverse(preds_scaled, artifact.scaler_y)


def make_forecast_dataframe(artifacts: List[SeriesArtifact], forecast_days: int = 30) -> pd.DataFrame:
    # Construir salida final requerida: date, location, predicted_stock.
    rows = []
    for artifact in artifacts:
        preds = recursive_forecast(artifact, steps=forecast_days)
        start = pd.to_datetime(artifact.history_dates.iloc[-1]) + pd.Timedelta(days=1)
        future_dates = pd.date_range(start=start, periods=forecast_days, freq="D")

        for date, pred in zip(future_dates, preds):
            rows.append(
                {
                    "date": date,
                    "location": artifact.location,
                    "predicted_stock": float(pred),
                }
            )

    return pd.DataFrame(rows).sort_values(["location", "date"])


def plot_forecasts(artifacts: List[SeriesArtifact], forecast_df: pd.DataFrame, output_dir: str):
    """Create one plot per location with historical and forecasted stock."""
    # Generar graficas comparando historial y prediccion para cada ubicacion.
    plots_dir = Path(output_dir) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for artifact in artifacts:
        sub = forecast_df[forecast_df["location"] == artifact.location].sort_values("date")

        plt.figure(figsize=(10, 5))
        plt.plot(artifact.history_dates, artifact.history_total_stock, label="Historical stock")
        plt.plot(sub["date"], sub["predicted_stock"], label="Predicted stock")
        plt.title(f"Stock Forecast - {artifact.location}")
        plt.xlabel("Date")
        plt.ylabel("Stock")
        plt.legend()
        plt.tight_layout()

        safe_name = f"{artifact.location}".replace(" ", "_").replace("/", "-")
        plt.savefig(plots_dir / f"forecast_{safe_name}.png", dpi=150)
        plt.close()
