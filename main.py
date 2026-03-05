import argparse
from pathlib import Path

import pandas as pd

from data_loader import load_inventory_files
from predict import make_forecast_dataframe, plot_forecasts
from preprocessing import aggregate_if_needed, build_stock_dataset, clean_inventory_data
from train import train_group_models


def parse_args():
    parser = argparse.ArgumentParser(description="Inventory forecasting with LSTM")
    parser.add_argument("--data-dir", type=str, default="data", help="Folder with daily Excel files")
    parser.add_argument("--output-dir", type=str, default="outputs", help="Folder to save CSV and plots")
    parser.add_argument("--window-size", type=int, default=30, help="Sliding window size (days)")
    parser.add_argument("--forecast-days", type=int, default=30, help="Number of future days to predict")
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Training batch size")
    parser.add_argument(
        "--no-scaling",
        action="store_true",
        help="Disable MinMaxScaler (enabled by default)",
    )
    parser.add_argument(
        "--aggregate-locations",
        action="store_true",
        help="Train a single series by summing all locations",
    )
    parser.add_argument(
        "--locations",
        nargs="*",
        default=None,
        help="Optional list of location names to train",
    )
    parser.add_argument(
        "--products",
        nargs="*",
        default=None,
        help="Deprecated alias of --locations (kept for compatibility).",
    )
    return parser.parse_args()


def run_pipeline(args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_df = load_inventory_files(args.data_dir)
    clean_df = clean_inventory_data(raw_df)

    # Compatibilidad: si llega --products, usarlo como alias de --locations.
    selected_locations = args.locations if args.locations else args.products
    if selected_locations:
        clean_df = clean_df[clean_df["location"].isin(selected_locations)].copy()

    clean_df = aggregate_if_needed(clean_df, per_location=not args.aggregate_locations)
    stock_df = build_stock_dataset(clean_df)

    artifacts, metrics_df = train_group_models(
        stock_df=stock_df,
        window_size=args.window_size,
        epochs=args.epochs,
        batch_size=args.batch_size,
        use_scaler=not args.no_scaling,
    )

    if not artifacts:
        raise RuntimeError(
            "No models were trained. Check if each series has enough days "
            f"(minimum > window_size + 5, current window_size={args.window_size})."
        )

    forecast_df = make_forecast_dataframe(artifacts, forecast_days=args.forecast_days)

    stock_csv = output_dir / "historical_stock.csv"
    metrics_csv = output_dir / "metrics.csv"
    forecast_csv = output_dir / "forecast.csv"

    stock_df.to_csv(stock_csv, index=False)
    metrics_df.to_csv(metrics_csv, index=False)
    forecast_df.to_csv(forecast_csv, index=False)

    plot_forecasts(artifacts, forecast_df, output_dir=str(output_dir))

    return stock_df, metrics_df, forecast_df, stock_csv, metrics_csv, forecast_csv


def main():
    args = parse_args()
    stock_df, metrics_df, forecast_df, stock_csv, metrics_csv, forecast_csv = run_pipeline(args)

    print("Pipeline completed successfully.")
    print(f"Historical stock rows: {len(stock_df)}")
    print(f"Forecast rows: {len(forecast_df)}")
    print(f"Saved: {stock_csv}")
    print(f"Saved: {metrics_csv}")
    print(f"Saved: {forecast_csv}")
    print("\nModel metrics preview:")
    with pd.option_context("display.max_rows", 10, "display.max_columns", None):
        print(metrics_df.head(10))


if __name__ == "__main__":
    main()
