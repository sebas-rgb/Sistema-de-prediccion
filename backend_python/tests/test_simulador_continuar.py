import sqlite3
from datetime import datetime

from inventory_ml.simulation.simulador import continuar, simular

PRODUCTOS = [
    {"codigo": str(i), "clase": "Alta", "stock_actual": 5, "stock_promedio": 5,
     "consumo_promedio": 2, "consumo_minimo": 1, "consumo_maximo": 3,
     "reposicion_promedio": 6, "frecuencia_movimiento": 0.9}
    for i in range(3)
]


def test_continuar_sigue_desde_el_ultimo_dia(tmp_path):
    db = tmp_path / "inv.db"
    simular(PRODUCTOS, db, dias=10, lead_time_dias=3, fecha_inicio=datetime(2026, 1, 1))

    assert continuar(db, dias=5, lead_time_dias=3) == ("2026-01-11", "2026-01-15")

    conn = sqlite3.connect(db)
    fechas = [f for (f,) in conn.execute("SELECT DISTINCT fecha FROM inventario ORDER BY fecha")]
    assert len(fechas) == 15 and fechas[-1] == "2026-01-15"
    # cada dia tiene un snapshot por producto, tambien los nuevos
    assert conn.execute("SELECT COUNT(*) FROM inventario").fetchone()[0] == 15 * len(PRODUCTOS)
    # ninguna orden queda RECIBIDA antes de llegar
    assert conn.execute(
        "SELECT COUNT(*) FROM ordenes_restock WHERE estado='PENDIENTE' AND fecha_llegada <= '2026-01-15'"
    ).fetchone()[0] == 0
