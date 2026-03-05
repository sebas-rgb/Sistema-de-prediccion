<<<<<<< HEAD
# Inventory Forecasting (TensorFlow + Keras)

This project trains LSTM neural networks to forecast inventory stock from daily Excel files.

## Expected data

Place your files in a folder (default: `data/`) with names like:

- `inventory_2024-01-01.xlsx`
- `inventory_2024-01-02.xlsx`

The date is extracted from the file name.

Inside each file:

- First column: product name
- Remaining columns: locations/warehouses
- Values: daily movement (`+` incoming, `-` sold)

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py --data-dir data --output-dir outputs
```

## Streamlit Interface

```bash
streamlit run Upload.py
```

The web app lets you upload multiple Excel files, configure training parameters, run forecasts, visualize historical vs predicted stock, and download CSV outputs.

Optional flags:

- `--window-size 30`
- `--forecast-days 30`
- `--epochs 30`
- `--batch-size 32`
- `--no-scaling`
- `--aggregate-locations`
- `--products Product_A Product_B`

## Outputs

Generated under `outputs/`:

- `historical_stock.csv` (clean stock history)
- `metrics.csv` (MSE/MAE by series)
- `forecast.csv` (future stock predictions)
- `plots/forecast_<product>_<location>.png`

## Project structure

- `data_loader.py`: loads Excel files and extracts date from filenames
- `preprocessing.py`: cleaning, aggregation, stock build, sliding windows
- `model.py`: LSTM model definition
- `train.py`: training/evaluation per product-location
- `predict.py`: recursive future forecasting and plots
- `main.py`: full pipeline entrypoint
=======
# Sistema-de-prediccion
Time-series inventory forecasting platform built with Python, TensorFlow/Keras and Streamlit. It processes Excel inventory movement matrices, reconstructs stock history and predicts future stock levels using LSTM models.
>>>>>>> 78078895267fb129c47fc541da7432ee6fa2114d
