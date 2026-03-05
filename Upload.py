from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from data_loader import load_single_excel
from predict import make_forecast_dataframe, plot_forecasts
from preprocessing import aggregate_if_needed, build_stock_dataset, clean_inventory_data
from train import train_group_models


st.set_page_config(
    page_title="Inventory Forecasting",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)
st.title("Inventory Forecasting - LSTM (TensorFlow/Keras)")
st.caption("Upload multiple daily Excel files and run stock forecasting from the browser.")


def load_uploaded_inventory(uploaded_files) -> pd.DataFrame:
    # Convertir cada Excel subido al esquema esperado por el pipeline.
    frames = []
    for uploaded in uploaded_files:
        day_df = load_single_excel(uploaded)
        frames.append(day_df[["date", "location", "total_stock", "net_movement"]])

    if not frames:
        return pd.DataFrame(columns=["date", "location", "total_stock", "net_movement"])
    return pd.concat(frames, ignore_index=True)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    # Serializar dataframe para descarga en Streamlit.
    return df.to_csv(index=False).encode("utf-8")


with st.sidebar:
    st.header("Configuration")
    window_size = st.number_input("Window Size (days)", min_value=5, max_value=120, value=30, step=1)
    forecast_days = st.number_input("Forecast Days", min_value=1, max_value=180, value=30, step=1)
    epochs = st.number_input("Epochs", min_value=1, max_value=500, value=30, step=1)
    batch_size = st.number_input("Batch Size", min_value=1, max_value=256, value=32, step=1)
    use_scaler = st.checkbox("Use MinMaxScaler", value=True)
    aggregate_locations = st.checkbox("Aggregate All Locations", value=False)
    save_outputs = st.checkbox("Save outputs to local /outputs folder", value=True)


uploaded_files = st.file_uploader(
    "Upload daily inventory Excel files",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)


if uploaded_files:
    try:
        # Cargar y limpiar datos diarios para entrenamiento.
        raw_df = load_uploaded_inventory(uploaded_files)
        clean_df = clean_inventory_data(raw_df)
    except Exception as exc:
        st.error(f"Error loading files: {exc}")
        st.stop()

    st.success(f"Loaded {len(uploaded_files)} file(s).")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows (clean)", f"{len(clean_df):,}")
    c2.metric("Locations", int(clean_df["location"].nunique()))
    c3.metric("Days", int(clean_df["date"].nunique()))

    st.subheader("Clean Dataset Preview")
    st.dataframe(clean_df.head(200), use_container_width=True)

    all_locations = sorted(clean_df["location"].unique().tolist())
    selected_locations = st.multiselect(
        "Filter Locations (optional)",
        options=all_locations,
        default=[],
        help="If empty, all locations are used.",
    )

    if st.button("Run Forecast", type="primary"):
        with st.spinner("Training models and generating forecast..."):
            work_df = clean_df.copy()
            if selected_locations:
                work_df = work_df[work_df["location"].isin(selected_locations)].copy()

            # Construir dataset temporal final y entrenar modelos por serie.
            work_df = aggregate_if_needed(work_df, per_location=not aggregate_locations)
            stock_df = build_stock_dataset(work_df)

            artifacts, metrics_df = train_group_models(
                stock_df=stock_df,
                window_size=int(window_size),
                epochs=int(epochs),
                batch_size=int(batch_size),
                use_scaler=bool(use_scaler),
            )

            if not artifacts:
                st.error(
                    "No models were trained. Each series needs enough days "
                    f"(minimum > window_size + 5, current window_size={window_size})."
                )
                st.stop()

            # Generar pronostico y conservar resultados en sesion.
            forecast_df = make_forecast_dataframe(artifacts, forecast_days=int(forecast_days))
            st.session_state["stock_df"] = stock_df
            st.session_state["metrics_df"] = metrics_df
            st.session_state["forecast_df"] = forecast_df
            st.session_state["artifacts"] = artifacts

            if save_outputs:
                # Exportar CSV y graficas al directorio local de salida.
                output_dir = Path("outputs")
                output_dir.mkdir(parents=True, exist_ok=True)
                stock_df.to_csv(output_dir / "historical_stock.csv", index=False)
                metrics_df.to_csv(output_dir / "metrics.csv", index=False)
                forecast_df.to_csv(output_dir / "forecast.csv", index=False)
                plot_forecasts(artifacts, forecast_df, output_dir=str(output_dir))

        st.success("Forecast completed.")


if "forecast_df" in st.session_state:
    stock_df = st.session_state["stock_df"]
    metrics_df = st.session_state["metrics_df"]
    forecast_df = st.session_state["forecast_df"]

    st.subheader("Model Metrics")
    st.dataframe(metrics_df, use_container_width=True)

    st.subheader("Forecast Data")
    st.dataframe(forecast_df, use_container_width=True)

    st.download_button(
        label="Download forecast.csv",
        data=to_csv_bytes(forecast_df),
        file_name="forecast.csv",
        mime="text/csv",
    )
    st.download_button(
        label="Download historical_stock.csv",
        data=to_csv_bytes(stock_df),
        file_name="historical_stock.csv",
        mime="text/csv",
    )
    st.download_button(
        label="Download metrics.csv",
        data=to_csv_bytes(metrics_df),
        file_name="metrics.csv",
        mime="text/csv",
    )

    st.subheader("Historical vs Predicted")
    labels = sorted(forecast_df["location"].drop_duplicates().tolist())
    if not labels:
        st.warning("No forecast series available to plot.")
    else:
        selected_label = st.selectbox("Series", options=labels)
        hist_sub = stock_df[stock_df["location"] == selected_label].sort_values("date")
        pred_sub = forecast_df[forecast_df["location"] == selected_label].sort_values("date")

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(hist_sub["date"], hist_sub["total_stock"], label="Historical stock")
        ax.plot(pred_sub["date"], pred_sub["predicted_stock"], label="Predicted stock")
        ax.set_title(selected_label)
        ax.set_xlabel("Date")
        ax.set_ylabel("Stock")
        ax.legend()
        st.pyplot(fig)
else:
    st.info("Upload files and click 'Run Forecast' to train and predict.")
