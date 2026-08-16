"""Tests del asistente. No se llama al proveedor real: se simula la respuesta."""

import json

import httpx
import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from inventory_ml import config
from inventory_ml.api.main import app
from inventory_ml.inference import Predictor
from inventory_ml.training.train import construir_pipeline

METADATA = {
    "version_modelo": "2.0.0",
    "algoritmo": "RandomForestClassifier",
    "horizonte_dias": 30,
    "origen_datos": "SIMULADO",
    "estado_validacion": "NO_VALIDADO_CON_DATOS_REALES",
}

RESPUESTA_LLM = {
    "model": "modelo-de-prueba",
    "choices": [{"message": {"content": "Prioriza los tres de clase Alta en cero."}}],
    "usage": {"prompt_tokens": 300, "completion_tokens": 40},
}


@pytest.fixture
def db(tmp_path):
    import sqlite3

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
    for i, (clase, consumo) in enumerate([("Alta", 8.0), ("Muerto", 0.0), ("Media", 3.0)]):
        conn.execute(
            "INSERT INTO productos VALUES (?,?,?,?,?,?,?,?,?)",
            (f"P{i}", clase, 100, 100, consumo, 1, 20, 80, 0.4),
        )
        conn.execute("INSERT INTO inventario VALUES (?,?,?)", ("2026-01-01", f"P{i}", 0))
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
    import inventory_ml.resumen as mod_resumen

    monkeypatch.setattr(mod_resumen.config, "DB_PATH", db)
    with TestClient(app) as c:
        yield c


def _simular_llm(monkeypatch, respuesta=None, status_code=200):
    """Sustituye la llamada saliente SOLO dentro del modulo del asistente.

    No se puede parchear httpx.Client globalmente: el TestClient de FastAPI
    tambien esta construido sobre httpx, asi que un parche global intercepta
    las peticiones del propio test y nunca llegan a la aplicacion.
    """
    capturado: dict = {}
    payload = respuesta if respuesta is not None else RESPUESTA_LLM

    class RespuestaFalsa:
        def __init__(self):
            self.status_code = status_code
            self.text = json.dumps(payload)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error", request=httpx.Request("POST", capturado["url"]), response=self
                )

        def json(self):
            return payload

    class ClienteFalso:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            capturado["url"] = url
            capturado["headers"] = headers or {}
            capturado["json"] = json or {}
            return RespuestaFalsa()

    class HttpxFalso:
        Client = ClienteFalso
        HTTPStatusError = httpx.HTTPStatusError
        HTTPError = httpx.HTTPError
        Request = httpx.Request

    monkeypatch.setattr("inventory_ml.api.asistente.httpx", HttpxFalso)
    return capturado


def test_sin_api_key_devuelve_503(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    r = client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"})
    assert r.status_code == 503
    assert "LLM_API_KEY" in r.json()["detail"]


def test_respuesta_correcta(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-de-prueba")
    _simular_llm(monkeypatch)
    r = client.post("/api/v1/asistente", json={"pregunta": "¿Que productos priorizo?"})
    assert r.status_code == 200
    body = r.json()
    assert body["respuesta"] == "Prioriza los tres de clase Alta en cero."
    assert body["origen_modelo"] == "SIMULADO"
    assert body["estado_validacion"] == "NO_VALIDADO_CON_DATOS_REALES"
    assert body["tokens_entrada"] == 300


def test_el_contexto_incluye_el_estado_del_modelo(client, monkeypatch):
    """El LLM debe saber que las probabilidades vienen de un modelo simulado."""
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-de-prueba")
    capturado = _simular_llm(monkeypatch)
    client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"})

    mensajes = capturado["json"]["messages"]
    system = mensajes[0]["content"]
    usuario = mensajes[1]["content"]
    assert "SIMULADOS" in system
    assert "NO decides" in system or "no decides" in system.lower()
    assert "SIMULADO" in usuario
    assert "NO_VALIDADO_CON_DATOS_REALES" in usuario


def test_la_clave_va_en_la_cabecera_y_no_en_el_cuerpo(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-secreta-123")
    capturado = _simular_llm(monkeypatch)
    client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"})
    assert capturado["headers"]["Authorization"] == "Bearer clave-secreta-123"
    assert "clave-secreta-123" not in json.dumps(capturado["json"])


def test_la_clave_nunca_llega_al_cliente(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-secreta-123")
    _simular_llm(monkeypatch)
    r = client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"})
    assert "clave-secreta-123" not in r.text


def test_error_del_proveedor_no_filtra_detalles(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-de-prueba")
    _simular_llm(monkeypatch, respuesta={"error": "cuenta sin saldo, org-12345"}, status_code=429)
    r = client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"})
    assert r.status_code == 503
    assert "org-12345" not in r.text


def test_respuesta_malformada_del_llm(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-de-prueba")
    _simular_llm(monkeypatch, respuesta={"sin": "choices"})
    assert client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"}).status_code == 503


@pytest.mark.parametrize("pregunta", ["", "ab", "x" * 1001])
def test_pregunta_invalida(client, monkeypatch, pregunta):
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-de-prueba")
    assert client.post("/api/v1/asistente", json={"pregunta": pregunta}).status_code == 422


def test_resumen_excluye_productos_sin_demanda_de_los_criticos(client, monkeypatch):
    """Un producto Muerto en cero no debe encabezar la lista de prioridades."""
    monkeypatch.setattr(config, "LLM_API_KEY", "clave-de-prueba")
    capturado = _simular_llm(monkeypatch)
    client.post("/api/v1/asistente", json={"pregunta": "¿Que compro?"})
    contexto = capturado["json"]["messages"][1]["content"]
    seccion_criticos = contexto.split("Top ")[1]
    assert "Muerto" not in seccion_criticos
