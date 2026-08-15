"""Tests minimos del contrato entre features, Pipeline e inference."""

import json

import joblib
import pandas as pd
import pytest

from inventory_ml import config
from inventory_ml.features import FEATURES, ContratoFeaturesError, construir_dataset
from inventory_ml.inference import ModeloNoDisponibleError, Predictor
from inventory_ml.training.train import construir_pipeline


@pytest.fixture
def pipeline_pequeno():
    """Modelo controlado y liviano; no depende del artefacto real."""
    df = pd.DataFrame(
        {
            "stock_actual": [0, 5, 200, 300, 1, 150],
            "consumo_promedio": [10, 8, 1, 0.5, 12, 2],
            "consumo_minimo": [1, 1, 0, 0, 2, 0],
            "consumo_maximo": [30, 20, 3, 2, 40, 5],
            "reposicion_promedio": [50, 40, 10, 5, 60, 20],
            "frecuencia_movimiento": [0.5, 0.4, 0.02, 0.0, 0.6, 0.1],
            "clase": ["Alta", "Alta", "Baja", "Muerto", "Alta", "Media"],
        }
    )
    y = [1, 1, 0, 0, 1, 0]
    return construir_pipeline().fit(df, y)


@pytest.fixture
def predictor(pipeline_pequeno, tmp_path, monkeypatch):
    model_path = tmp_path / "test.joblib"
    meta_path = tmp_path / "test.metadata.json"
    joblib.dump(pipeline_pequeno, model_path)
    meta_path.write_text(
        json.dumps(
            {
                "version_modelo": "0.0.1-test",
                "algoritmo": "RandomForestClassifier",
                "horizonte_dias": 30,
                "origen_datos": "SIMULADO",
                "estado_validacion": "NO_VALIDADO_CON_DATOS_REALES",
            }
        ),
        encoding="utf-8",
    )
    return Predictor.cargar(model_path, meta_path)


def test_clase_positiva_no_se_asume(pipeline_pequeno):
    """predict_proba[:, i] debe apuntar a la clase 1, verificado via classes_."""
    clases = list(pipeline_pequeno.classes_)
    assert 1 in clases
    assert Predictor._resolver_clase_positiva(pipeline_pequeno) == clases.index(1)


def test_modelo_inexistente_falla_explicito(tmp_path):
    with pytest.raises(ModeloNoDisponibleError):
        Predictor.cargar(tmp_path / "no_existe.joblib", tmp_path / "no.json")


def test_prediccion_en_rango_y_riesgo_consistente(predictor):
    r = predictor.predict(
        {
            "codigo": "12345",
            "stock_actual": 0,
            "consumo_promedio": 10,
            "consumo_minimo": 1,
            "consumo_maximo": 30,
            "reposicion_promedio": 50,
            "frecuencia_movimiento": 0.5,
            "clase": "Alta",
        }
    )
    p = r["probabilidad_agotamiento"]
    assert 0.0 <= p <= 1.0
    assert r["nivel_riesgo"] == config.nivel_riesgo(p)
    assert r["origen_modelo"] == "SIMULADO"
    assert r["estado_validacion"] == "NO_VALIDADO_CON_DATOS_REALES"


def test_batch_equivale_a_individual(predictor):
    registro = {
        "codigo": "999",
        "stock_actual": 300,
        "consumo_promedio": 0.5,
        "consumo_minimo": 0,
        "consumo_maximo": 2,
        "reposicion_promedio": 5,
        "frecuencia_movimiento": 0.0,
        "clase": "Muerto",
    }
    individual = predictor.predict(registro)
    batch = predictor.predict_batch([registro, registro])
    assert len(batch) == 2
    assert batch[0]["probabilidad_agotamiento"] == individual["probabilidad_agotamiento"]


def test_batch_vacio(predictor):
    assert predictor.predict_batch([]) == []


def test_falta_columna_requerida(predictor):
    with pytest.raises(ContratoFeaturesError):
        predictor.predict({"codigo": "1", "stock_actual": 0})


def test_encoding_clase_no_depende_del_lote(pipeline_pequeno):
    """El bug viejo: cat.codes cambiaba segun que clases traia el lote."""
    base = {
        "stock_actual": 10,
        "consumo_promedio": 5,
        "consumo_minimo": 1,
        "consumo_maximo": 10,
        "reposicion_promedio": 20,
        "frecuencia_movimiento": 0.3,
        "clase": "Media",
    }
    solo = pd.DataFrame([base])[FEATURES]
    acompanado = pd.DataFrame([base, {**base, "clase": "Alta"}])[FEATURES]
    assert (
        pipeline_pequeno.predict_proba(solo)[0, 1]
        == pipeline_pequeno.predict_proba(acompanado)[0, 1]
    )


def test_construir_dataset_target_a_horizonte():
    inventario = pd.DataFrame(
        {
            "fecha": pd.date_range("2026-01-01", periods=10).astype(str),
            "codigo": ["A"] * 10,
            "stock": [100, 90, 80, 70, 60, 50, 40, 30, 0, 0],
        }
    )
    productos = pd.DataFrame(
        [
            {
                "codigo": "A",
                "clase": "Alta",
                "consumo_promedio": 10,
                "consumo_minimo": 5,
                "consumo_maximo": 15,
                "reposicion_promedio": 100,
                "frecuencia_movimiento": 0.9,
            }
        ]
    )
    ds = construir_dataset(inventario, productos, horizonte_dias=8)
    assert len(ds) == 2
    assert ds["agotado_30d"].tolist() == [1, 1]
