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
    # Una lista simula un agente encadenando vueltas: cada post consume la
    # siguiente respuesta y la ultima se repite si el bucle pidiera mas.
    guion = respuesta if respuesta is not None else RESPUESTA_LLM
    pendientes = list(guion) if isinstance(guion, list) else [guion]
    capturado["cuerpos"] = []

    def siguiente():
        return pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]

    class RespuestaFalsa:
        def __init__(self, payload):
            self.status_code = status_code
            self.payload = payload
            self.text = json.dumps(payload)

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error", request=httpx.Request("POST", capturado["url"]), response=self
                )

        def json(self):
            return self.payload

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
            capturado["cuerpos"].append(json or {})
            return RespuestaFalsa(siguiente())

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


# ---------------------------------------------------------------
# Bucle de agente: el modelo pide herramientas y las usa
# ---------------------------------------------------------------


def _llamada(nombre, argumentos, id_="call_1"):
    return {
        "model": "modelo-de-prueba",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": id_,
                            "type": "function",
                            "function": {"name": nombre, "arguments": json.dumps(argumentos)},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 500, "completion_tokens": 20},
    }


def test_el_agente_ejecuta_la_herramienta_y_responde(client, monkeypatch):
    """Primera vuelta: pide la herramienta. Segunda: responde con el resultado."""
    capturado = _simular_llm(
        monkeypatch,
        [
            _llamada("consultar_producto", {"codigo": "P0"}),
            {
                "model": "modelo-de-prueba",
                "choices": [{"message": {"content": "P0 esta en cero y es clase Alta."}}],
                "usage": {"prompt_tokens": 700, "completion_tokens": 30},
            },
        ],
    )

    r = client.post("/api/v1/asistente", json={"pregunta": "¿Como esta el P0?"})
    assert r.status_code == 200
    cuerpo = r.json()

    assert cuerpo["herramientas_usadas"] == ["consultar_producto"]
    assert cuerpo["respuesta"] == "P0 esta en cero y es clase Alta."
    # Los tokens se acumulan a lo largo de todas las vueltas, no solo la ultima.
    assert cuerpo["tokens_entrada"] == 1200

    # La segunda peticion debe llevar el resultado de la herramienta como
    # mensaje 'tool'; sin eso el modelo responderia a ciegas.
    mensajes = capturado["cuerpos"][1]["messages"]
    tool = [m for m in mensajes if m.get("role") == "tool"]
    assert len(tool) == 1
    assert tool[0]["tool_call_id"] == "call_1"
    assert "P0" in tool[0]["content"]


def test_el_escenario_hipotetico_cambia_la_probabilidad(client, monkeypatch):
    """La herramienta contrafactual devuelve las dos probabilidades."""
    capturado = _simular_llm(
        monkeypatch,
        [
            _llamada("simular_escenario", {"codigo": "P0", "niveles_stock": [50, 500]}),
            {
                "model": "modelo-de-prueba",
                "choices": [{"message": {"content": "Con 500 unidades el riesgo baja."}}],
            },
        ],
    )

    r = client.post("/api/v1/asistente", json={"pregunta": "¿Y si compro 500 de P0?"})
    assert r.status_code == 200
    assert r.json()["herramientas_usadas"] == ["simular_escenario"]

    resultado = json.loads(
        [m for m in capturado["cuerpos"][1]["messages"] if m.get("role") == "tool"][0]["content"]
    )
    assert resultado["stock_real"] == 0
    assert [e["stock"] for e in resultado["escenarios"]] == [50, 500]
    # Mas stock nunca puede aumentar el riesgo de agotarse.
    probabilidades = [resultado["probabilidad_real"]] + [
        e["probabilidad"] for e in resultado["escenarios"]
    ]
    assert probabilidades == sorted(probabilidades, reverse=True)


def test_herramienta_inexistente_no_rompe_la_conversacion(client, monkeypatch):
    """Un nombre inventado vuelve como error en texto, no como excepcion."""
    capturado = _simular_llm(
        monkeypatch,
        [
            _llamada("borrar_inventario", {}),
            {
                "model": "modelo-de-prueba",
                "choices": [{"message": {"content": "No puedo hacer eso."}}],
            },
        ],
    )

    r = client.post("/api/v1/asistente", json={"pregunta": "Borra todo"})
    assert r.status_code == 200

    resultado = json.loads(
        [m for m in capturado["cuerpos"][1]["messages"] if m.get("role") == "tool"][0]["content"]
    )
    assert "no existe" in resultado["error"]


def test_sin_herramientas_responde_en_una_vuelta(client, monkeypatch):
    """El resumen inyectado basta para las preguntas comunes: no gasta vueltas."""
    capturado = _simular_llm(monkeypatch)
    r = client.post("/api/v1/asistente", json={"pregunta": "¿Que priorizo?"})
    assert r.status_code == 200
    assert r.json()["herramientas_usadas"] == []
    assert len(capturado["cuerpos"]) == 1


def test_el_bucle_termina_aunque_el_modelo_insista(client, monkeypatch):
    """Un modelo que solo pide herramientas no puede colgar la peticion."""
    from inventory_ml import herramientas

    capturado = _simular_llm(monkeypatch, [_llamada("comparar_politicas", {})])
    r = client.post("/api/v1/asistente", json={"pregunta": "¿Sirve el modelo?"})

    # Se agotan las vueltas y se fuerza una final instruida a concluir.
    assert len(capturado["cuerpos"]) == herramientas.MAX_ITERACIONES + 1
    # Las herramientas SIGUEN presentes: quitarlas provoca un 400 del proveedor
    # cuando el historial venia encadenando llamadas.
    assert "tools" in capturado["cuerpos"][-1]
    assert "no puedes usar mas herramientas" in capturado["cuerpos"][-1]["messages"][-1]["content"]
    # El guion nunca entrega texto, asi que el endpoint lo reporta como 503
    # en vez de devolver una respuesta vacia.
    assert r.status_code == 503
