from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import torch
except ImportError as exc:
    raise RuntimeError(
        "PyTorch no esta disponible en el interprete actual. "
        "Usa un entorno compatible, preferiblemente Python 3.12, "
        "para ejecutar las predicciones."
    ) from exc

from train import SeriesArtifact, inverse_target


def recursive_forecast(artifact: SeriesArtifact, steps: int) -> np.ndarray:
    """Forecast future stock recursively from the last known window."""
    if steps <= 0:
        return np.asarray([], dtype=float)

    current_window = artifact.last_window_raw.copy()
    predictions: List[float] = []

    for _ in range(steps):
        if artifact.scaler_x is not None:
            model_window = artifact.scaler_x.transform(current_window).astype(np.float32)
        else:
            model_window = current_window.astype(np.float32)

        model_input = torch.tensor(model_window, dtype=torch.float32).unsqueeze(0).to(artifact.device)
        with torch.no_grad():
            next_scaled = artifact.model(model_input).detach().cpu().numpy().reshape(-1)[0]

        next_stock = float(inverse_target(np.asarray([next_scaled]), artifact.scaler_y)[0])
        predictions.append(next_stock)

        next_row = np.asarray(
            [next_stock, artifact.future_movement_assumption],
            dtype=float,
        )
        current_window = np.vstack([current_window[1:, :], next_row])

    return np.asarray(predictions, dtype=float)


def make_forecast_dataframe(
    artifacts: List[SeriesArtifact],
    forecast_days: int,
) -> pd.DataFrame:
    """Build the final forecast dataframe."""
    rows = []
    for artifact in artifacts:
        predictions = recursive_forecast(artifact, steps=forecast_days)
        start_date = pd.to_datetime(artifact.history_dates.iloc[-1]) + pd.Timedelta(days=1)
        future_dates = pd.date_range(start=start_date, periods=forecast_days, freq="D")

        for forecast_date, predicted_stock in zip(future_dates, predictions):
            rows.append(
                {
                    "date": forecast_date,
                    "location": artifact.location,
                    "predicted_stock": float(predicted_stock),
                }
            )

    forecast_df = pd.DataFrame(rows)
    if forecast_df.empty:
        return pd.DataFrame(columns=["date", "location", "predicted_stock"])
    return forecast_df.sort_values(["location", "date"]).reset_index(drop=True)


def plot_forecasts(
    artifacts: List[SeriesArtifact],
    forecast_df: pd.DataFrame,
    output_dir: str,
) -> None:
    """Create one plot per location with historical and predicted stock."""
    plots_dir = Path(output_dir) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for artifact in artifacts:
        subset = forecast_df[forecast_df["location"] == artifact.location].sort_values("date")

        plt.figure(figsize=(10, 5))
        plt.plot(artifact.history_dates, artifact.history_total_stock, label="Historical stock")
        plt.plot(subset["date"], subset["predicted_stock"], label="Predicted stock")
        plt.title(f"Stock Forecast - {artifact.location}")
        plt.xlabel("Date")
        plt.ylabel("Stock")
        plt.legend()
        plt.tight_layout()

        safe_name = artifact.location.replace(" ", "_").replace("/", "-")
        plt.savefig(plots_dir / f"forecast_{safe_name}.png", dpi=150)
        plt.close()
