"""Integracion con el artefacto real. Se omite si el modelo no esta entrenado."""

import pytest
from fastapi.testclient import TestClient

from inventory_ml import config
from inventory_ml.api.main import app

pytestmark = pytest.mark.skipif(
    not config.MODEL_PATH.exists(),
    reason="Requiere el artefacto real: python -m inventory_ml.training.train",
)

PRODUCTO = {
    "codigo": "188486",
    "stock_actual": 3,
    "consumo_promedio": 7.5,
    "consumo_minimo": 1,
    "consumo_maximo": 22,
    "reposicion_promedio": 100,
    "frecuencia_movimiento": 0.5,
    "clase": "Alta",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_cadena_completa(client):
    """Pipeline real -> inference -> FastAPI -> JSON valido."""
    assert client.get("/health").json()["model_loaded"] is True

    info = client.get("/api/v1/model/info").json()
    assert info["origen_datos"] == "SIMULADO"
    assert info["estado_validacion"] == "NO_VALIDADO_CON_DATOS_REALES"

    body = client.post("/api/v1/predict", json=PRODUCTO).json()
    p = body["probabilidad_agotamiento"]
    assert 0.0 <= p <= 1.0
    assert body["nivel_riesgo"] == config.nivel_riesgo(p)
    # la metadata expuesta corresponde al modelo que predijo
    assert body["version_modelo"] == info["version_modelo"]
    assert body["horizonte_dias"] == info["horizonte_dias"]


def test_batch_real_es_consistente(client):
    variantes = [
        {**PRODUCTO, "codigo": "A", "stock_actual": 3},
        {**PRODUCTO, "codigo": "B", "stock_actual": 400},
    ]
    r = client.post("/api/v1/predict/batch", json={"items": variantes}).json()
    assert r["total"] == 2
    for item in r["resultados"]:
        assert 0.0 <= item["probabilidad_agotamiento"] <= 1.0
        assert item["nivel_riesgo"] == config.nivel_riesgo(item["probabilidad_agotamiento"])
    # con stock escaso el riesgo debe ser mayor que con stock holgado
    assert (
        r["resultados"][0]["probabilidad_agotamiento"]
        > r["resultados"][1]["probabilidad_agotamiento"]
    )


def test_stock_cero_es_el_maximo_riesgo(client):
    """Un producto ya agotado no puede tener menos riesgo que uno con 3 unidades.

    Antes fallaba: el target era `stock[t+30] <= 0`, contaminado por la
    reposicion del simulador. Con el minimo de la ventana, estar en cero
    implica agotamiento por definicion.
    """
    items = [
        {**PRODUCTO, "codigo": "CERO", "stock_actual": 0},
        {**PRODUCTO, "codigo": "TRES", "stock_actual": 3},
    ]
    r = client.post("/api/v1/predict/batch", json={"items": items}).json()
    cero, tres = (x["probabilidad_agotamiento"] for x in r["resultados"])
    assert cero >= tres


def test_riesgo_decrece_con_el_stock(client):
    """A mas stock, menos riesgo, con el resto de features constante."""
    niveles = [0, 10, 100, 1000]
    items = [{**PRODUCTO, "codigo": str(s), "stock_actual": s} for s in niveles]
    r = client.post("/api/v1/predict/batch", json={"items": items}).json()
    probas = [x["probabilidad_agotamiento"] for x in r["resultados"]]
    assert probas == sorted(probas, reverse=True), probas
