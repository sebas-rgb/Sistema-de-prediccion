import argparse
from pathlib import Path

import pandas as pd

from data_loader import list_excel_files, load_inventory_files
from predict import make_forecast_dataframe, plot_forecasts
from preprocessing import aggregate_if_needed, build_stock_dataset, clean_inventory_data
from train import auto_configure_training_params, train_group_models


def parse_args():
    parser = argparse.ArgumentParser(description="Inventory forecasting with PyTorch")
    parser.add_argument("--data-dir", type=str, default="data", help="Folder with daily Excel files")
    parser.add_argument("--output-dir", type=str, default="outputs", help="Folder to save CSV and plots")
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

    excel_files = list_excel_files(args.data_dir)
    raw_df = load_inventory_files(args.data_dir)
    clean_df = clean_inventory_data(raw_df)

    selected_locations = args.locations if args.locations else args.products
    if selected_locations:
        clean_df = clean_df[clean_df["location"].isin(selected_locations)].copy()
        if clean_df.empty:
            raise ValueError("Los filtros de ubicacion dejaron el dataset vacio.")

    clean_df = aggregate_if_needed(clean_df, per_location=not args.aggregate_locations)
    stock_df = build_stock_dataset(clean_df)
    config = auto_configure_training_params(stock_df=stock_df, num_files=len(excel_files))

    artifacts, metrics_df = train_group_models(stock_df=stock_df, config=config)
    if not artifacts:
        raise RuntimeError(
            "No se pudo entrenar ningun modelo. Verifica que cada serie tenga "
            "suficientes dias para construir ventanas temporales."
        )

    forecast_df = make_forecast_dataframe(
        artifacts=artifacts,
        forecast_days=config.forecast_days,
    )

    stock_csv = output_dir / "historical_stock.csv"
    metrics_csv = output_dir / "metrics.csv"
    forecast_csv = output_dir / "forecast.csv"

    stock_df.to_csv(stock_csv, index=False)
    metrics_df.to_csv(metrics_csv, index=False)
    forecast_df.to_csv(forecast_csv, index=False)
    plot_forecasts(artifacts, forecast_df, output_dir=str(output_dir))

    return {
        "stock_df": stock_df,
        "metrics_df": metrics_df,
        "forecast_df": forecast_df,
        "config": config,
        "stock_csv": stock_csv,
        "metrics_csv": metrics_csv,
        "forecast_csv": forecast_csv,
    }


def main():
    results = run_pipeline(parse_args())

    print("Pipeline completed successfully.")
    print(f"Historical stock rows: {len(results['stock_df'])}")
    print(f"Forecast rows: {len(results['forecast_df'])}")
    print(f"Saved: {results['stock_csv']}")
    print(f"Saved: {results['metrics_csv']}")
    print(f"Saved: {results['forecast_csv']}")
    print("\nAuto configuration:")
    print(
        f"files={results['config'].num_files}, "
        f"days={results['config'].detected_days}, "
        f"window_size={results['config'].window_size}, "
        f"forecast_days={results['config'].forecast_days}, "
        f"epochs={results['config'].epochs}, "
        f"batch_size={results['config'].batch_size}"
    )
    print("\nMetrics preview:")
    with pd.option_context("display.max_rows", 10, "display.max_columns", None):
        print(results["metrics_df"].head(10))


if __name__ == "__main__":
    main()
