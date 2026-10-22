"""Acceso de solo lectura al inventario simulado.

Separado de `inference` a proposito: esto es acceso a datos, no inferencia.
La API lo combina con el Predictor para servir estado + prediccion juntos.

Cuando el proyecto migre a PostgreSQL, se reemplaza este modulo y el contrato
HTTP no cambia.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from inventory_ml.features import COLUMNAS_NUMERICAS, COLUMNA_CATEGORICA


class InventarioNoDisponibleError(RuntimeError):
    """La base de datos del inventario no existe o no se puede leer."""


class SedeDesconocidaError(LookupError):
    """La sede pedida no tiene perfiles."""


COLUMNAS_PRODUCTO = [c for c in COLUMNAS_NUMERICAS if c != "stock_actual"]


def _conectar(db_path: Path) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise InventarioNoDisponibleError("Inventario no disponible.")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rango_fechas(db_path: Path) -> dict:
    """Primera y ultima fecha con snapshots, y cuantos dias hay."""
    with _conectar(db_path) as conn:
        fila = conn.execute(
            "SELECT MIN(fecha) AS primera, MAX(fecha) AS ultima,"
            " COUNT(DISTINCT fecha) AS dias FROM inventario"
        ).fetchone()
    if fila is None or fila["primera"] is None:
        raise InventarioNoDisponibleError("El inventario esta vacio.")
    return {
        "primera_fecha": date.fromisoformat(fila["primera"]),
        "ultima_fecha": date.fromisoformat(fila["ultima"]),
        "dias_disponibles": fila["dias"],
    }


def estado_en_fecha(
    db_path: Path,
    fecha: date | None = None,
    codigo: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[date, int, list[dict]]:
    """Snapshot del inventario en una fecha, listo para pasar al Predictor.

    Devuelve (fecha_efectiva, total_de_productos, pagina_de_registros).
    Si no se indica fecha, usa la ultima disponible.
    """
    columnas = ", ".join(f"p.{c}" for c in COLUMNAS_PRODUCTO)

    with _conectar(db_path) as conn:
        if fecha is None:
            fila = conn.execute("SELECT MAX(fecha) AS f FROM inventario").fetchone()
            if fila is None or fila["f"] is None:
                raise InventarioNoDisponibleError("El inventario esta vacio.")
            fecha = date.fromisoformat(fila["f"])

        filtro = "WHERE i.fecha = ?"
        params: list = [fecha.isoformat()]
        if codigo:
            filtro += " AND i.codigo LIKE ?"
            params.append(f"%{codigo}%")

        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM inventario i {filtro}", params
        ).fetchone()["n"]

        filas = conn.execute(
            f"""
            SELECT i.codigo, i.fecha, i.stock AS stock_actual,
                   p.{COLUMNA_CATEGORICA}, {columnas}
            FROM inventario i
            JOIN productos p ON p.codigo = i.codigo
            {filtro}
            ORDER BY i.codigo
            LIMIT ? OFFSET ?
            """,
            [*params, limite, desplazamiento],
        ).fetchall()

    return fecha, total, [dict(f) for f in filas]


# ---------------------------------------------------------------
# Por sede: perfiles reales (ingestion/sedes.py), no la simulacion
# ---------------------------------------------------------------


def listar_sedes(db_path: Path) -> tuple[date, list[str]]:
    """Fecha del ultimo snapshot real y sedes con productos perfilados."""
    with _conectar(db_path) as conn:
        filas = conn.execute(
            "SELECT sede, MAX(fecha) AS f FROM perfil_sede GROUP BY sede ORDER BY sede"
        ).fetchall()
    if not filas:
        raise InventarioNoDisponibleError("No hay perfiles por sede.")
    return date.fromisoformat(filas[0]["f"]), [f["sede"] for f in filas]


def estado_sede(
    db_path: Path,
    sede: str,
    codigo: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[date, int, list[dict]]:
    """Ultimo stock real de cada producto en una sede, con su perfil EN esa sede.

    Misma forma que `estado_en_fecha`: el Predictor y la interfaz no distinguen
    si el registro viene de la simulacion o de una sede.
    """
    columnas = ", ".join(COLUMNAS_PRODUCTO)
    filtro = "WHERE sede = ?"
    params: list = [sede]
    if codigo:
        filtro += " AND codigo LIKE ?"
        params.append(f"%{codigo}%")

    with _conectar(db_path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM perfil_sede {filtro}", params
        ).fetchone()["n"]
        filas = conn.execute(
            f"""
            SELECT codigo, fecha, stock_actual, {COLUMNA_CATEGORICA}, {columnas}
            FROM perfil_sede
            {filtro}
            ORDER BY codigo
            LIMIT ? OFFSET ?
            """,
            [*params, limite, desplazamiento],
        ).fetchall()
        if not total:
            existe = conn.execute(
                "SELECT 1 FROM perfil_sede WHERE sede = ? LIMIT 1", [sede]
            ).fetchone()
            if existe is None:
                raise SedeDesconocidaError(sede)
        fecha = conn.execute(
            "SELECT MAX(fecha) AS f FROM perfil_sede WHERE sede = ?", [sede]
        ).fetchone()["f"]

    return date.fromisoformat(fecha), total, [dict(f) for f in filas]
