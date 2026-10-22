"""Control del pipeline desde la interfaz: simular, extender, entrenar, comparar.

Cada tarea corre los MISMOS comandos de consola documentados en EJECUCION.md,
en un subproceso: si la interfaz y la terminal hacen lo mismo, no hay dos
caminos que mantener. Una sola tarea a la vez; el estado vive en memoria, asi
que se pierde al reiniciar la API (aceptable para una herramienta de
demostracion).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from inventory_ml import config
from inventory_ml.inference import Predictor
from inventory_ml.repository import InventarioNoDisponibleError, rango_fechas
from inventory_ml.simulation.experimento import NOMBRE_JSON

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

Tipo = Literal["simular_anio", "agregar_dias", "entrenar", "experimento"]


class TareaRequest(BaseModel):
    tipo: Tipo
    dias: int = Field(30, ge=1, le=730, description="simular_anio / agregar_dias")
    semilla: int = Field(42, ge=0)
    algoritmo: Literal["rf", "logistica", "xgb", "mlp"] = "rf"
    umbral: float = Field(0.8, gt=0, lt=1, description="experimento")


class _Tarea:
    def __init__(self, req: TareaRequest):
        self.tipo = req.tipo
        self.parametros = req.model_dump(exclude={"tipo"})
        self.estado = "EN_CURSO"
        self.inicio = datetime.now(timezone.utc)
        self.fin: datetime | None = None
        self.log: deque[str] = deque(maxlen=200)

    def json(self) -> dict:
        return {
            "tipo": self.tipo,
            "parametros": self.parametros,
            "estado": self.estado,
            "inicio": self.inicio.isoformat(),
            "fin": self.fin.isoformat() if self.fin else None,
            "log": list(self.log),
        }


_candado = threading.Lock()
_ultima: _Tarea | None = None


def _comandos(req: TareaRequest) -> list[list[str]]:
    py = [sys.executable, "-m"]
    if req.tipo == "simular_anio":
        # Se genera aparte y se reemplaza al final: la API sigue sirviendo la
        # simulacion anterior mientras la nueva se construye.
        tmp = str(config.DB_PATH.with_suffix(".nuevo.db"))
        return [py + ["inventory_ml.simulation.simulador", "--dias", str(req.dias),
                      "--semilla", str(req.semilla), "--db", tmp]]
    if req.tipo == "agregar_dias":
        return [py + ["inventory_ml.simulation.simulador", "--continuar",
                      "--dias", str(req.dias), "--semilla", str(req.semilla)]]
    if req.tipo == "entrenar":
        cmd = py + ["inventory_ml.training.train", "--algoritmo", req.algoritmo]
        return [cmd + ["--dispositivo", "cpu"] if req.algoritmo == "xgb" else cmd]
    return [py + ["inventory_ml.simulation.experimento", "--umbral", str(req.umbral)]]


def _ejecutar(tarea: _Tarea, req: TareaRequest, app: FastAPI) -> None:
    try:
        for cmd in _comandos(req):
            tarea.log.append("$ " + " ".join(cmd[1:]))
            proc = subprocess.Popen(
                cmd, cwd=config.PROJECT_ROOT, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            for linea in proc.stdout:
                tarea.log.append(linea.rstrip())
            if proc.wait() != 0:
                raise RuntimeError(f"El comando termino con codigo {proc.returncode}")

        if req.tipo == "simular_anio":
            os.replace(config.DB_PATH.with_suffix(".nuevo.db"), config.DB_PATH)
        if req.tipo == "entrenar" and req.algoritmo == "rf":
            # El rf es el modelo que sirve la API: se recarga sin reiniciar.
            app.state.predictor = Predictor.cargar()
            tarea.log.append("Modelo activo recargado.")
        tarea.estado = "OK"
    except Exception as exc:
        logger.exception("Fallo la tarea %s", tarea.tipo)
        tarea.log.append(f"ERROR: {exc}")
        tarea.estado = "ERROR"
    finally:
        tarea.fin = datetime.now(timezone.utc)
        _candado.release()


def _modelos() -> list[dict]:
    salida = []
    for meta in sorted(config.MODELS_DIR.glob("*.metadata.json")):
        try:
            d = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        salida.append({
            "nombre": meta.name.removesuffix(".metadata.json"),
            "activo": meta == config.MODEL_METADATA_PATH,
            "algoritmo": d.get("algoritmo"),
            "fecha_entrenamiento": d.get("fecha_entrenamiento"),
            "corte_temporal": d.get("corte_temporal"),
            "n_train": d.get("n_train"),
            "metricas": d.get("metricas_holdout_temporal"),
        })
    return salida


@router.get("", summary="Estado de la simulacion, los modelos y la ultima tarea")
def estado() -> dict:
    try:
        r = rango_fechas(config.DB_PATH)
        simulacion = {k: str(v) for k, v in r.items()}
    except InventarioNoDisponibleError:
        simulacion = None

    reporte = config.ARTIFACTS_DIR / "reports" / NOMBRE_JSON
    experimento = None
    if reporte.exists():
        try:
            experimento = {"generado": json.loads(reporte.read_text(encoding="utf-8")).get("generado")}
        except json.JSONDecodeError:
            pass

    return {
        "simulacion": simulacion,
        "modelos": _modelos(),
        "experimento": experimento,
        "tarea": _ultima.json() if _ultima else None,
    }


@router.post("/tareas", status_code=status.HTTP_202_ACCEPTED, summary="Lanza una tarea")
def lanzar(req: TareaRequest, request: Request) -> dict:
    global _ultima
    if not _candado.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una tarea en curso. Espera a que termine.")
    _ultima = _Tarea(req)
    threading.Thread(target=_ejecutar, args=(_ultima, req, request.app), daemon=True).start()
    return _ultima.json()
