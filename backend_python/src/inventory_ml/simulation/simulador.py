"""Simulacion de movimientos diarios de inventario.

Reemplaza a `simulador.py` y absorbe `crear_sqlite_db.py` (habia dos DDL
distintos para las mismas tablas; este es el unico). Reglas de negocio
identicas al original. Correcciones:

  - la semilla es un PARAMETRO, no una constante del config. Con semilla fija
    cada corrida producia datos identicos, asi que la "validacion externa"
    evaluaba sobre los mismos datos de entrenamiento. Usa --semilla distinta
    para generar un set de validacion de verdad.
  - `stock_promedio` se guarda en la tabla productos (el original lo leia del
    JSON para calcular la reposicion pero nunca lo persistia).

Uso:
    python -m inventory_ml.simulation.simulador --dias 365
    python -m inventory_ml.simulation.simulador --semilla 99 --db data/validacion.db
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from inventory_ml import config

logger = logging.getLogger(__name__)

DIAS_SIMULACION = 365
SEMILLA = 42
FECHA_INICIO = datetime(2026, 1, 1)

DDL = """
DROP TABLE IF EXISTS movimientos;
DROP TABLE IF EXISTS ordenes_restock;
DROP TABLE IF EXISTS inventario;
DROP TABLE IF EXISTS productos;

CREATE TABLE productos (
    codigo TEXT PRIMARY KEY,
    clase TEXT NOT NULL,
    stock_inicial INTEGER,
    stock_promedio REAL,
    consumo_promedio REAL,
    consumo_minimo REAL,
    consumo_maximo REAL,
    reposicion_promedio REAL,
    frecuencia_movimiento REAL
);

CREATE TABLE inventario (
    fecha DATE NOT NULL,
    codigo TEXT NOT NULL,
    stock INTEGER NOT NULL,
    PRIMARY KEY (codigo, fecha),
    FOREIGN KEY (codigo) REFERENCES productos(codigo)
);

CREATE TABLE ordenes_restock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL,
    fecha_pedido DATE,
    fecha_llegada DATE,
    cantidad INTEGER,
    estado TEXT,
    FOREIGN KEY (codigo) REFERENCES productos(codigo)
);

CREATE TABLE movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    codigo TEXT NOT NULL,
    tipo TEXT NOT NULL,
    cantidad INTEGER,
    stock_resultante INTEGER,
    FOREIGN KEY (codigo) REFERENCES productos(codigo)
);

CREATE INDEX idx_inventario_codigo_fecha ON inventario(codigo, fecha);
"""


def _insertar_productos(cur: sqlite3.Cursor, productos: list[dict]) -> dict[str, int]:
    stock_actual: dict[str, int] = {}
    for p in productos:
        codigo = str(p["codigo"])
        inicial = int(round(p["stock_actual"]))
        stock_actual[codigo] = inicial
        cur.execute(
            "INSERT INTO productos VALUES (?,?,?,?,?,?,?,?,?)",
            (
                codigo,
                p["clase"],
                inicial,
                p.get("stock_promedio", inicial),
                p["consumo_promedio"],
                p["consumo_minimo"],
                p["consumo_maximo"],
                p["reposicion_promedio"],
                p["frecuencia_movimiento"],
            ),
        )
    return stock_actual


def simular(
    productos: list[dict],
    db_path: Path,
    dias: int = DIAS_SIMULACION,
    lead_time_dias: int = config.LEAD_TIME_DIAS,
    semilla: int = SEMILLA,
    fecha_inicio: datetime = FECHA_INICIO,
) -> Path:
    rng = random.Random(semilla)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(DDL)

    stock_actual = _insertar_productos(cur, productos)
    pendientes: list[dict] = []

    for dia in range(dias):
        fecha = fecha_inicio + timedelta(days=dia)
        fecha_str = fecha.strftime("%Y-%m-%d")

        # --- llegadas de restock ---
        for orden in pendientes[:]:
            if orden["fecha_llegada"] <= fecha:
                codigo = orden["codigo"]
                stock_actual[codigo] += int(orden["cantidad"])
                cur.execute(
                    "INSERT INTO movimientos (fecha, codigo, tipo, cantidad, stock_resultante)"
                    " VALUES (?,?,?,?,?)",
                    (fecha_str, codigo, "RESTOCK", int(orden["cantidad"]), stock_actual[codigo]),
                )
                cur.execute(
                    "UPDATE ordenes_restock SET estado='RECIBIDO' WHERE id=?", (orden["id"],)
                )
                pendientes.remove(orden)

        # --- consumo, pedidos y snapshot ---
        for p in productos:
            codigo = str(p["codigo"])
            stock = stock_actual[codigo]

            if rng.random() < p["frecuencia_movimiento"] and stock > 0:
                minimo = max(1, int(round(p["consumo_minimo"])))
                maximo = max(int(round(p["consumo_maximo"])), minimo)
                consumo = rng.randint(minimo, maximo)
                stock = max(0, stock - consumo)
                stock_actual[codigo] = stock
                cur.execute(
                    "INSERT INTO movimientos (fecha, codigo, tipo, cantidad, stock_resultante)"
                    " VALUES (?,?,?,?,?)",
                    (fecha_str, codigo, "CONSUMO", consumo, stock),
                )

            if stock_actual[codigo] <= 0 and not any(
                o["codigo"] == codigo for o in pendientes
            ):
                cantidad = max(
                    1,
                    int(round(max(p["reposicion_promedio"], p.get("stock_promedio", 0)))),
                )
                fecha_llegada = fecha + timedelta(days=lead_time_dias)
                cur.execute(
                    "INSERT INTO ordenes_restock (codigo, fecha_pedido, fecha_llegada,"
                    " cantidad, estado) VALUES (?,?,?,?,?)",
                    (codigo, fecha_str, fecha_llegada.strftime("%Y-%m-%d"), cantidad, "PENDIENTE"),
                )
                pendientes.append(
                    {
                        "id": cur.lastrowid,
                        "codigo": codigo,
                        "cantidad": cantidad,
                        "fecha_llegada": fecha_llegada,
                    }
                )

            cur.execute(
                "INSERT INTO inventario VALUES (?,?,?)",
                (fecha_str, codigo, int(stock_actual[codigo])),
            )

        if dia % 60 == 0:
            logger.info("Dia %s | ordenes pendientes: %s", dia, len(pendientes))

    conn.commit()
    conn.close()
    logger.info("Simulacion completada: %s productos x %s dias -> %s", len(productos), dias, db_path)
    return db_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Simula movimientos de inventario")
    parser.add_argument(
        "--productos", type=Path, default=config.DATA_DIR / "interim/productos_muestra.json"
    )
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--dias", type=int, default=DIAS_SIMULACION)
    parser.add_argument("--lead-time", type=int, default=config.LEAD_TIME_DIAS)
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    args = parser.parse_args()

    if not args.productos.exists():
        raise SystemExit(
            f"No se encontro {args.productos}. Ejecuta primero: "
            "python -m inventory_ml.ingestion.perfilado"
        )

    productos = json.loads(args.productos.read_text(encoding="utf-8"))
    simular(productos, args.db, args.dias, args.lead_time, args.semilla)


if __name__ == "__main__":
    main()
