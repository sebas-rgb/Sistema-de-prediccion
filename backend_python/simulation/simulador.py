import json
import sqlite3
import random
import os

from datetime import datetime, timedelta

# Directorio base del script y rutas organizadas
BASE_DIR = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)

# Archivos de configuración y datos (rutas absolutas dentro de la carpeta simulation)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PRODUCTOS_SAMPLE_PATH = os.path.join(BASE_DIR, "productos_simulacion_sample.json")
DB_PATH = os.path.join(DB_DIR, "inventario.db")

# =====================================
# CONFIG
# =====================================

with open(CONFIG_PATH, "r", encoding="utf8") as f:
    config = json.load(f)

with open(
    PRODUCTOS_SAMPLE_PATH,
    "r",
    encoding="utf8"
) as f:
    productos = json.load(f)

random.seed(
    config["semilla_random"]
)

# =====================================
# REINICIAR DB
# =====================================

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)

cur = conn.cursor()

# =====================================
# TABLAS
# =====================================

cur.executescript("""
CREATE TABLE productos (
    codigo TEXT PRIMARY KEY,
    clase TEXT,
    stock_inicial INTEGER,
    consumo_promedio REAL,
    consumo_minimo INTEGER,
    consumo_maximo INTEGER,
    reposicion_promedio INTEGER,
    frecuencia_movimiento REAL
);

CREATE TABLE inventario (
    fecha DATE,
    codigo TEXT,
    stock INTEGER,
    FOREIGN KEY(codigo)
        REFERENCES productos(codigo)
);

CREATE TABLE ordenes_restock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT,
    fecha_pedido DATE,
    fecha_llegada DATE,
    cantidad INTEGER,
    estado TEXT,
    FOREIGN KEY(codigo)
        REFERENCES productos(codigo)
);

CREATE TABLE movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE,
    codigo TEXT,
    tipo TEXT,
    cantidad INTEGER,
    stock_resultante INTEGER,
    FOREIGN KEY(codigo)
        REFERENCES productos(codigo)
);
""")

# =====================================
# DATOS INICIALES
# =====================================

stock_actual = {}
ordenes_pendientes = []

for p in productos:

    codigo = str(p["codigo"])

    stock_inicial = int(
        round(
            p["stock_actual"]
        )
    )

    stock_actual[codigo] = stock_inicial

    cur.execute(
        """
        INSERT INTO productos
        VALUES
        (?,?,?,?,?,?,?,?)
        """,
        (
            codigo,
            p["clase"],
            stock_inicial,
            p["consumo_promedio"],
            int(round(
                p["consumo_minimo"]
            )),
            int(round(
                p["consumo_maximo"]
            )),
            int(round(
                p["reposicion_promedio"]
            )),
            p["frecuencia_movimiento"]
        )
    )

# =====================================
# SIMULACIÓN
# =====================================

fecha_inicio = datetime(
    2026,
    1,
    1
)

for dia in range(
    config["dias_simulacion"]
):

    fecha_actual = (
        fecha_inicio +
        timedelta(days=dia)
    )

    # ==========================
    # LLEGADAS RESTOCK
    # ==========================

    for orden in ordenes_pendientes[:]:

        if (
            orden["fecha_llegada"]
            <= fecha_actual
        ):

            codigo = orden["codigo"]

            stock_actual[codigo] += int(
                orden["cantidad"]
            )

            cur.execute(
                """
                INSERT INTO movimientos
                (
                    fecha,
                    codigo,
                    tipo,
                    cantidad,
                    stock_resultante
                )
                VALUES
                (?,?,?,?,?)
                """,
                (
                    fecha_actual.strftime(
                        "%Y-%m-%d"
                    ),
                    codigo,
                    "RESTOCK",
                    int(
                        orden["cantidad"]
                    ),
                    stock_actual[codigo]
                )
            )

            cur.execute(
                """
                UPDATE ordenes_restock
                SET estado='RECIBIDO'
                WHERE id=?
                """,
                (
                    orden["id"],
                )
            )

            ordenes_pendientes.remove(
                orden
            )

    # ==========================
    # CONSUMOS
    # ==========================

    for p in productos:

        codigo = str(
            p["codigo"]
        )

        stock = stock_actual[codigo]

        if (
            random.random()
            < p["frecuencia_movimiento"]
        ):

            consumo_min = int(
                round(
                    p["consumo_minimo"]
                )
            )

            consumo_max = int(
                round(
                    p["consumo_maximo"]
                )
            )

            if consumo_max <= 0:

                consumo = 0

            else:

                consumo = random.randint(
                    max(
                        1,
                        consumo_min
                    ),
                    max(
                        consumo_max,
                        max(
                            1,
                            consumo_min
                        )
                    )
                )

            if stock > 0:

                stock -= consumo

                if stock < 0:
                    stock = 0

                stock = int(stock)

                stock_actual[
                    codigo
                ] = stock

                if consumo > 0:

                    cur.execute(
                        """
                        INSERT INTO movimientos
                        (
                            fecha,
                            codigo,
                            tipo,
                            cantidad,
                            stock_resultante
                        )
                        VALUES
                        (?,?,?,?,?)
                        """,
                        (
                            fecha_actual.strftime(
                                "%Y-%m-%d"
                            ),
                            codigo,
                            "CONSUMO",
                            consumo,
                            stock
                        )
                    )

        # ======================
        # GENERAR PEDIDO
        # ======================

        if stock_actual[codigo] <= 0:

            ya_pedido = any(
                o["codigo"] == codigo
                for o in ordenes_pendientes
            )

            if not ya_pedido:

                cantidad = int(
                    round(
                        max(
                            p["reposicion_promedio"],
                            p["stock_promedio"]
                        )
                    )
                )

                if cantidad <= 0:
                    cantidad = 1

                fecha_llegada = (
                    fecha_actual +
                    timedelta(
                        days=config[
                            "lead_time_dias"
                        ]
                    )
                )

                cur.execute(
                    """
                    INSERT INTO
                    ordenes_restock
                    (
                        codigo,
                        fecha_pedido,
                        fecha_llegada,
                        cantidad,
                        estado
                    )
                    VALUES
                    (?,?,?,?,?)
                    """,
                    (
                        codigo,
                        fecha_actual.strftime(
                            "%Y-%m-%d"
                        ),
                        fecha_llegada.strftime(
                            "%Y-%m-%d"
                        ),
                        cantidad,
                        "PENDIENTE"
                    )
                )

                orden_id = (
                    cur.lastrowid
                )

                ordenes_pendientes.append(
                    {
                        "id": orden_id,
                        "codigo": codigo,
                        "cantidad": cantidad,
                        "fecha_llegada":
                            fecha_llegada
                    }
                )

        # ======================
        # SNAPSHOT INVENTARIO
        # ======================

        cur.execute(
            """
            INSERT INTO inventario
            VALUES (?,?,?)
            """,
            (
                fecha_actual.strftime(
                    "%Y-%m-%d"
                ),
                codigo,
                int(
                    stock_actual[codigo]
                )
            )
        )

    if dia % 30 == 0:

        print(
            f"Día {dia} | "
            f"Órdenes pendientes: "
            f"{len(ordenes_pendientes)}"
        )

# =====================================
# FIN
# =====================================

conn.commit()
conn.close()

print(
    "\nSimulación completada."
)