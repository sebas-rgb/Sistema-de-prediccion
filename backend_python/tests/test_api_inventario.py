"""Tests del endpoint de inventario: usa una DB minima, no la simulacion real."""

import json
import sqlite3

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from inventory_ml import config
from inventory_ml.api.main import app
from inventory_ml.inference import Predictor
from inventory_ml.training.train import construir_pipeline

METADATA = {
    "version_modelo": "1.0.0",
    "algoritmo": "RandomForestClassifier",
    "horizonte_dias": 30,
    "origen_datos": "SIMULADO",
    "estado_validacion": "NO_VALIDADO_CON_DATOS_REALES",
    "fecha_entrenamiento": "2026-01-01T00:00:00+00:00",
}


@pytest.fixture
def db(tmp_path):
    ruta = tmp_path / "inv.db"
    conn = sqlite3.connect(ruta)
    conn.executescript(
        """
        CREATE TABLE productos (codigo TEXT PRIMARY KEY, clase TEXT, stock_inicial INTEGER,
          stock_promedio REAL, consumo_promedio REAL, consumo_minimo REAL,
          consumo_maximo REAL, reposicion_promedio REAL, frecuencia_movimiento REAL);
        CREATE TABLE inventario (fecha DATE, codigo TEXT, stock INTEGER);
        """
    )
    for i, clase in enumerate(["Alta", "Baja", "Media"]):
        conn.execute(
            "INSERT INTO productos VALUES (?,?,?,?,?,?,?,?,?)",
            (f"P{i}", clase, 100, 100, 5.0, 1, 20, 80, 0.4),
        )
        for dia, fecha in enumerate(["2026-01-01", "2026-01-02"]):
            conn.execute("INSERT INTO inventario VALUES (?,?,?)", (fecha, f"P{i}", 50 - dia * 10))
    conn.commit()
    conn.close()
    return ruta


@pytest.fixture
def client(db, tmp_path, monkeypatch):
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
    modelo, meta = tmp_path / "m.joblib", tmp_path / "m.json"
    joblib.dump(construir_pipeline().fit(df, [1, 1, 0, 0, 1, 0]), modelo)
    meta.write_text(json.dumps(METADATA), encoding="utf-8")
    predictor = Predictor.cargar(modelo, meta)
    monkeypatch.setattr(Predictor, "cargar", classmethod(lambda cls, *a, **k: predictor))
    monkeypatch.setattr(config, "DB_PATH", db)
    # el router lee config.DB_PATH en tiempo de request
    import inventory_ml.api.inventario as mod

    monkeypatch.setattr(mod.config, "DB_PATH", db)
    with TestClient(app) as c:
        yield c


def test_rango_de_fechas(client):
    r = client.get("/api/v1/inventario/fechas")
    assert r.status_code == 200
    assert r.json() == {
        "primera_fecha": "2026-01-01",
        "ultima_fecha": "2026-01-02",
        "dias_disponibles": 2,
    }


def test_por_defecto_usa_la_ultima_fecha(client):
    body = client.get("/api/v1/inventario").json()
    assert body["fecha"] == "2026-01-02"
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_fecha_explicita(client):
    body = client.get("/api/v1/inventario?fecha=2026-01-01").json()
    assert body["fecha"] == "2026-01-01"
    assert all(i["stock_actual"] == 50 for i in body["items"])


def test_items_traen_prediccion_coherente(client):
    body = client.get("/api/v1/inventario").json()
    for item in body["items"]:
        assert 0.0 <= item["probabilidad_agotamiento"] <= 1.0
        assert item["nivel_riesgo"] == config.nivel_riesgo(item["probabilidad_agotamiento"])
    # el origen del modelo viaja con los datos
    assert body["origen_modelo"] == "SIMULADO"
    assert body["estado_validacion"] == "NO_VALIDADO_CON_DATOS_REALES"


def test_no_expone_la_etiqueta_real(client):
    """agotado_30d no puede aparecer: solo se conoce 30 dias despues."""
    body = client.get("/api/v1/inventario").json()
    assert "agotado_30d" not in json.dumps(body)


def test_paginacion(client):
    p1 = client.get("/api/v1/inventario?pagina=1&tamano_pagina=2").json()
    p2 = client.get("/api/v1/inventario?pagina=2&tamano_pagina=2").json()
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    assert p1["total"] == p2["total"] == 3
    assert {i["codigo"] for i in p1["items"]}.isdisjoint({i["codigo"] for i in p2["items"]})


def test_filtro_por_codigo(client):
    body = client.get("/api/v1/inventario?codigo=P1").json()
    assert body["total"] == 1
    assert body["items"][0]["codigo"] == "P1"


def test_fecha_sin_datos_devuelve_vacio(client):
    body = client.get("/api/v1/inventario?fecha=2030-01-01").json()
    assert body["total"] == 0 and body["items"] == []


def test_parametros_invalidos(client):
    assert client.get("/api/v1/inventario?pagina=0").status_code == 422
    assert client.get("/api/v1/inventario?tamano_pagina=999").status_code == 422
    assert client.get("/api/v1/inventario?fecha=ayer").status_code == 422
