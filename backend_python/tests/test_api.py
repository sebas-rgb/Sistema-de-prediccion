"""Tests de la capa HTTP. No dependen del artefacto real: usan un modelo minimo."""

import json

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from inventory_ml import config
from inventory_ml.api.main import app
from inventory_ml.inference import Predictor
from inventory_ml.training.train import construir_pipeline

PRODUCTO = {
    "codigo": "12345",
    "stock_actual": 2,
    "consumo_promedio": 9.0,
    "consumo_minimo": 1,
    "consumo_maximo": 25,
    "reposicion_promedio": 80,
    "frecuencia_movimiento": 0.55,
    "clase": "Alta",
}

METADATA = {
    "version_modelo": "1.0.0",
    "algoritmo": "RandomForestClassifier",
    "horizonte_dias": 30,
    "origen_datos": "SIMULADO",
    "estado_validacion": "NO_VALIDADO_CON_DATOS_REALES",
    "fecha_entrenamiento": "2026-01-01T00:00:00+00:00",
}


@pytest.fixture
def predictor(tmp_path):
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
    modelo = tmp_path / "m.joblib"
    meta = tmp_path / "m.metadata.json"
    joblib.dump(construir_pipeline().fit(df, [1, 1, 0, 0, 1, 0]), modelo)
    meta.write_text(json.dumps(METADATA), encoding="utf-8")
    return Predictor.cargar(modelo, meta)


@pytest.fixture
def client(predictor, monkeypatch):
    """Cliente con modelo cargado."""
    monkeypatch.setattr(Predictor, "cargar", classmethod(lambda cls, *a, **k: predictor))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_sin_modelo(monkeypatch, tmp_path):
    """Cliente cuyo artefacto no existe: la app arranca degradada."""
    monkeypatch.setattr(config, "MODEL_PATH", tmp_path / "no_existe.joblib")
    monkeypatch.setattr(config, "MODEL_METADATA_PATH", tmp_path / "no.json")
    with TestClient(app) as c:
        yield c


# --- health -------------------------------------------------------------
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_loaded": True}


def test_health_degradado_sin_modelo(client_sin_modelo):
    r = client_sin_modelo.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "model_loaded": False}


# --- model/info ---------------------------------------------------------
def test_model_info_expone_origen_simulado(client):
    r = client.get("/api/v1/model/info")
    assert r.status_code == 200
    body = r.json()
    assert body["origen_datos"] == "SIMULADO"
    assert body["estado_validacion"] == "NO_VALIDADO_CON_DATOS_REALES"
    assert body["algoritmo"] == "RandomForestClassifier"
    # no debe filtrar rutas ni configuracion interna
    assert not any("path" in k.lower() or "dir" in k.lower() for k in body)


def test_model_info_503_sin_modelo(client_sin_modelo):
    assert client_sin_modelo.get("/api/v1/model/info").status_code == 503


# --- predict ------------------------------------------------------------
def test_predict_ok(client):
    r = client.post("/api/v1/predict", json=PRODUCTO)
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["probabilidad_agotamiento"] <= 1.0
    assert body["nivel_riesgo"] == config.nivel_riesgo(body["probabilidad_agotamiento"])
    assert body["codigo"] == "12345"
    assert body["origen_modelo"] == "SIMULADO"
    assert body["estado_validacion"] == "NO_VALIDADO_CON_DATOS_REALES"
    assert body["horizonte_dias"] == 30


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("clase", "Inexistente"),
        ("frecuencia_movimiento", 1.5),
        ("stock_actual", -1),
        ("codigo", ""),
        ("consumo_promedio", "texto"),
    ],
)
def test_predict_rechaza_entrada_invalida(client, campo, valor):
    assert client.post("/api/v1/predict", json={**PRODUCTO, campo: valor}).status_code == 422


def test_predict_campo_faltante(client):
    payload = {k: v for k, v in PRODUCTO.items() if k != "clase"}
    assert client.post("/api/v1/predict", json=payload).status_code == 422


def test_predict_503_sin_modelo(client_sin_modelo):
    assert client_sin_modelo.post("/api/v1/predict", json=PRODUCTO).status_code == 503


# --- batch --------------------------------------------------------------
def test_batch_ok(client):
    r = client.post("/api/v1/predict/batch", json={"items": [PRODUCTO, PRODUCTO]})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["resultados"]) == 2


def test_batch_coincide_con_individual(client):
    ind = client.post("/api/v1/predict", json=PRODUCTO).json()
    lote = client.post("/api/v1/predict/batch", json={"items": [PRODUCTO]}).json()
    assert (
        lote["resultados"][0]["probabilidad_agotamiento"]
        == ind["probabilidad_agotamiento"]
    )


def test_batch_vacio_rechazado(client):
    assert client.post("/api/v1/predict/batch", json={"items": []}).status_code == 422


def test_batch_excede_maximo(client):
    items = [PRODUCTO] * (config.MAX_BATCH_SIZE + 1)
    assert client.post("/api/v1/predict/batch", json={"items": items}).status_code == 422


def test_batch_en_el_maximo_funciona(client):
    items = [PRODUCTO] * config.MAX_BATCH_SIZE
    r = client.post("/api/v1/predict/batch", json={"items": items})
    assert r.status_code == 200
    assert r.json()["total"] == config.MAX_BATCH_SIZE


# --- errores ------------------------------------------------------------
def test_error_de_inferencia_no_filtra_stacktrace(predictor, monkeypatch):
    """Un fallo inesperado debe dar 500 limpio, sin rutas ni traceback."""

    def explota(*a, **k):
        raise RuntimeError("ruta secreta /home/maple/.env")

    monkeypatch.setattr(Predictor, "cargar", classmethod(lambda cls, *a, **k: predictor))
    monkeypatch.setattr(Predictor, "predict_batch", explota)
    # raise_server_exceptions=False: queremos ver la respuesta HTTP real que
    # recibiria Spring Boot, no que el cliente de tests relance la excepcion.
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/api/v1/predict", json=PRODUCTO)
    assert r.status_code == 500
    assert r.json() == {"detail": "Error interno al procesar la solicitud."}
    assert "secreta" not in r.text and "Traceback" not in r.text


def test_swagger_disponible(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
