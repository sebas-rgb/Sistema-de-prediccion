Proyecto de forecasting de inventario migrado a PyTorch.

Cambios principales:
- La fecha de cada dia se sigue extrayendo exclusivamente desde el nombre del archivo Excel.
- Se conserva la lectura de multiples archivos `.xlsx` y `.xls`.
- Se mantiene la logica basada en la fila `Totales:` para separar `total_stock` y `net_movement`.
- El entrenamiento y la prediccion ahora se ejecutan con PyTorch.
- `window_size`, `forecast_days`, `epochs` y `batch_size` ya no se piden manualmente: se calculan con `auto_configure_training_params(...)`.

Ejecucion CLI:
```bash
python main.py --data-dir data --output-dir outputs
```

Interfaz Streamlit:
```bash
streamlit run Upload.py
```

Salidas:
- `outputs/historical_stock.csv`
- `outputs/metrics.csv`
- `outputs/forecast.csv`
- `outputs/plots/*.png`
