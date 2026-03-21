from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from data_loader import load_single_excel
from predict import make_forecast_dataframe, plot_forecasts
from preprocessing import aggregate_if_needed, build_stock_dataset, clean_inventory_data
from train import auto_configure_training_params, train_group_models


st.set_page_config(
    page_title="Inventory Forecasting",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)
st.title("Inventory Forecasting")
st.caption(
    "Carga archivos diarios de inventario y genera pronosticos con un modelo PyTorch "
    "configurado automaticamente."
)


def load_uploaded_inventory(uploaded_files) -> pd.DataFrame:
    """Convert uploaded Excel files to the consolidated schema."""
    frames = []
    for uploaded in uploaded_files:
        frames.append(load_single_excel(uploaded))

    if not frames:
        return pd.DataFrame(columns=["date", "location", "total_stock", "net_movement"])
    return pd.concat(frames, ignore_index=True)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def render_auto_config(config) -> None:
    st.subheader("Configuracion automatica")
    c1, c2, c3 = st.columns(3)
    c1.metric("Archivos cargados", config.num_files)
    c2.metric("Dias detectados", config.detected_days)
    c3.metric("Registros validos", config.valid_records)

    c4, c5, c6 = st.columns(3)
    c4.metric("Window size auto", config.window_size)
    c5.metric("Forecast horizon auto", config.forecast_days)
    c6.metric("Series", config.num_locations)

    c7, c8, c9 = st.columns(3)
    c7.metric("Epochs auto", config.epochs)
    c8.metric("Batch size auto", config.batch_size)
    c9.metric("Secuencias estimadas", config.total_sequences_estimate)

    explanation_df = pd.DataFrame(
        [{"parametro": key, "detalle": value} for key, value in config.explanation.items()]
    )
    st.dataframe(explanation_df, use_container_width=True, hide_index=True)


with st.sidebar:
    st.header("Ejecucion")
    aggregate_locations = st.checkbox("Agregar todas las ubicaciones", value=False)
    save_outputs = st.checkbox("Guardar resultados en /outputs", value=True)


uploaded_files = st.file_uploader(
    "Carga archivos diarios de inventario",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)


if uploaded_files:
    try:
        raw_df = load_uploaded_inventory(uploaded_files)
        clean_df = clean_inventory_data(raw_df)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    st.success(f"Se cargaron {len(uploaded_files)} archivo(s).")
    c1, c2, c3 = st.columns(3)
    c1.metric("Filas limpias", f"{len(clean_df):,}")
    c2.metric("Ubicaciones", int(clean_df["location"].nunique()))
    c3.metric("Dias", int(clean_df["date"].nunique()))

    st.subheader("Vista previa del dataset limpio")
    st.dataframe(clean_df.head(200), use_container_width=True)

    all_locations = sorted(clean_df["location"].unique().tolist())
    selected_locations = st.multiselect(
        "Filtrar ubicaciones",
        options=all_locations,
        default=[],
        help="Si no eliges ninguna, se usan todas.",
    )

    work_df = clean_df.copy()
    if selected_locations:
        work_df = work_df[work_df["location"].isin(selected_locations)].copy()

    if work_df.empty:
        st.error("No quedaron datos despues de aplicar el filtro de ubicaciones.")
        st.stop()

    work_df = aggregate_if_needed(work_df, per_location=not aggregate_locations)
    stock_df = build_stock_dataset(work_df)

    try:
        auto_config = auto_configure_training_params(
            stock_df=stock_df,
            num_files=len(uploaded_files),
        )
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    render_auto_config(auto_config)

    if st.button("Ejecutar forecast", type="primary"):
        with st.spinner("Entrenando modelos PyTorch y generando forecast..."):
            artifacts, metrics_df = train_group_models(stock_df=stock_df, config=auto_config)

            if not artifacts:
                st.error(
                    "No se entrenaron modelos. Verifica que las series tengan "
                    "suficientes dias historicos."
                )
                st.stop()

            forecast_df = make_forecast_dataframe(
                artifacts=artifacts,
                forecast_days=auto_config.forecast_days,
            )

            st.session_state["stock_df"] = stock_df
            st.session_state["metrics_df"] = metrics_df
            st.session_state["forecast_df"] = forecast_df
            st.session_state["auto_config"] = auto_config

            if save_outputs:
                output_dir = Path("outputs")
                output_dir.mkdir(parents=True, exist_ok=True)
                stock_df.to_csv(output_dir / "historical_stock.csv", index=False)
                metrics_df.to_csv(output_dir / "metrics.csv", index=False)
                forecast_df.to_csv(output_dir / "forecast.csv", index=False)
                plot_forecasts(artifacts, forecast_df, output_dir=str(output_dir))

        st.success("Forecast completado.")


if "forecast_df" in st.session_state:
    stock_df = st.session_state["stock_df"]
    metrics_df = st.session_state["metrics_df"]
    forecast_df = st.session_state["forecast_df"]
    auto_config = st.session_state["auto_config"]

    render_auto_config(auto_config)

    st.subheader("Metricas del modelo")
    st.dataframe(metrics_df, use_container_width=True)

    st.subheader("Pronostico")
    st.dataframe(forecast_df, use_container_width=True)

    st.download_button(
        label="Descargar forecast.csv",
        data=to_csv_bytes(forecast_df),
        file_name="forecast.csv",
        mime="text/csv",
    )
    st.download_button(
        label="Descargar historical_stock.csv",
        data=to_csv_bytes(stock_df),
        file_name="historical_stock.csv",
        mime="text/csv",
    )
    st.download_button(
        label="Descargar metrics.csv",
        data=to_csv_bytes(metrics_df),
        file_name="metrics.csv",
        mime="text/csv",
    )

    st.subheader("Historico vs pronostico")
    series_options = sorted(forecast_df["location"].drop_duplicates().tolist())
    selected_series = st.selectbox("Serie", options=series_options)
    historical = stock_df[stock_df["location"] == selected_series].sort_values("date")
    predicted = forecast_df[forecast_df["location"] == selected_series].sort_values("date")

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(historical["date"], historical["total_stock"], label="Historico")
    ax.plot(predicted["date"], predicted["predicted_stock"], label="Pronosticado")
    ax.set_title(selected_series)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Stock")
    ax.legend()
    st.pyplot(fig)
else:
    st.info("Carga archivos y ejecuta el forecast para ver resultados.")
