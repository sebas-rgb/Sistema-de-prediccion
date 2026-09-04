"""Experimento contrafactual: ¿comprar con el modelo evita quiebres?

Compara dos politicas de reposicion sobre EXACTAMENTE la misma demanda:

  REACTIVA   (la actual): pedir cuando el stock llega a 0.
  PREDICTIVA (el modelo): pedir cuando P(agotamiento) >= umbral,
                          manteniendo la reactiva como red de seguridad.

La demanda se genera UNA vez y se congela. Ambos brazos enfrentan el mismo
flujo dia a dia, asi que cualquier diferencia viene de la politica y no del
azar. Sin eso, la comparacion no significa nada.

El resultado se guarda en JSON para que la API lo sirva sin recalcular: la
simulacion completa tarda ~11 s, demasiado para una peticion HTTP.

Uso:
    python -m inventory_ml.simulation.experimento --umbral 0.8
    python -m inventory_ml.simulation.experimento --umbral 0.5 --umbral 0.9
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from inventory_ml import config
from inventory_ml.features import COLUMNAS_NUMERICAS, COLUMNA_CATEGORICA
from inventory_ml.inference import Predictor

logger = logging.getLogger(__name__)

NOMBRE_JSON = "comparacion_politicas.json"


def cargar_productos(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql("SELECT * FROM productos", conn).to_dict("records")


def fecha_inicio_simulacion(db_path: Path) -> date:
    with sqlite3.connect(db_path) as conn:
        fila = conn.execute("SELECT MIN(fecha) AS f FROM inventario").fetchone()
    return date.fromisoformat(fila[0]) if fila and fila[0] else date(2026, 1, 1)


def generar_demanda(productos: list[dict], dias: int, semilla: int) -> dict[str, list[int]]:
    """Demanda diaria por producto, independiente del stock disponible.

    Clave del experimento: se genera una sola vez. Ambas politicas ven la misma
    secuencia, incluyendo la demanda que la reactiva no puede atender.
    """
    rng = random.Random(semilla)
    demanda: dict[str, list[int]] = {}
    for p in productos:
        codigo = str(p["codigo"])
        minimo = max(1, int(round(p["consumo_minimo"])))
        maximo = max(int(round(p["consumo_maximo"])), minimo)
        demanda[codigo] = [
            rng.randint(minimo, maximo) if rng.random() < p["frecuencia_movimiento"] else 0
            for _ in range(dias)
        ]
    return demanda


def _cantidad_pedido(p: dict) -> int:
    return max(1, int(round(max(p["reposicion_promedio"], p.get("stock_promedio") or 0))))


def simular_politica(
    productos: list[dict],
    demanda: dict[str, list[int]],
    dias: int,
    lead_time: int,
    politica: str,
    predictor: Predictor | None = None,
    umbral: float = 0.8,
    red_seguridad: bool = True,
) -> dict:
    """Corre la simulacion bajo una politica y devuelve metricas y serie diaria."""
    stock = {str(p["codigo"]): int(round(p["stock_inicial"])) for p in productos}
    pendientes: dict[str, int] = {}
    por_codigo = {str(p["codigo"]): p for p in productos}
    con_demanda = {c for c, serie in demanda.items() if sum(serie) > 0}

    dias_agotado = 0
    dias_agotado_utiles = 0
    no_servidas = 0
    demanda_total = 0
    pedidos = 0
    stock_acumulado = 0
    serie_agotados: list[int] = []
    serie_stock: list[int] = []
    serie_vendido: list[int] = []

    for dia in range(dias):
        for codigo, dia_llegada in list(pendientes.items()):
            if dia_llegada <= dia:
                stock[codigo] += _cantidad_pedido(por_codigo[codigo])
                del pendientes[codigo]

        vendido_hoy = 0
        for codigo, serie in demanda.items():
            d = serie[dia]
            demanda_total += d
            atendido = min(d, stock[codigo])
            stock[codigo] -= atendido
            vendido_hoy += atendido
            no_servidas += d - atendido

        if politica == "reactiva":
            for codigo, s in stock.items():
                if s <= 0 and codigo not in pendientes:
                    pendientes[codigo] = dia + lead_time
                    pedidos += 1
        else:
            # Red de seguridad: si ya estas en cero, pides igual. Sin esto la
            # politica predictiva abandona los productos que el modelo no marca.
            if red_seguridad:
                for codigo, s in stock.items():
                    if s <= 0 and codigo not in pendientes:
                        pendientes[codigo] = dia + lead_time
                        pedidos += 1

            candidatos = [c for c in stock if c not in pendientes]
            if candidatos:
                filas = []
                for codigo in candidatos:
                    p = por_codigo[codigo]
                    fila = {"codigo": codigo, "stock_actual": stock[codigo]}
                    for col in COLUMNAS_NUMERICAS:
                        if col != "stock_actual":
                            fila[col] = p[col]
                    fila[COLUMNA_CATEGORICA] = p[COLUMNA_CATEGORICA]
                    filas.append(fila)
                # una sola llamada vectorizada por dia, no una por producto
                for r in predictor.predict_batch(filas):
                    if r["probabilidad_agotamiento"] >= umbral:
                        pendientes[r["codigo"]] = dia + lead_time
                        pedidos += 1

        agotados_hoy = sum(1 for c, s in stock.items() if s <= 0 and c in con_demanda)
        serie_agotados.append(agotados_hoy)
        serie_stock.append(sum(stock.values()))
        serie_vendido.append(vendido_hoy)
        dias_agotado += sum(1 for s in stock.values() if s <= 0)
        dias_agotado_utiles += agotados_hoy
        stock_acumulado += sum(stock.values())

    n = len(stock) * dias
    return {
        "politica": "reactiva" if politica == "reactiva" else f"predictiva@{umbral}",
        "etiqueta": "Sin anticipación" if politica == "reactiva" else f"Con modelo ({umbral:.0%})",
        "dias_agotado": dias_agotado,
        "dias_agotado_utiles": dias_agotado_utiles,
        "unidades_no_servidas": no_servidas,
        "fill_rate": round(1 - no_servidas / max(demanda_total, 1), 4),
        "pedidos": pedidos,
        "stock_promedio": round(stock_acumulado / n, 1),
        "serie_agotados": serie_agotados,
        "serie_stock": serie_stock,
        "serie_vendido": serie_vendido,
    }


def comparar(
    db_path: Path,
    dias: int,
    lead_time: int,
    semilla: int,
    umbrales: list[float],
    red_seguridad: bool = True,
) -> dict:
    productos = cargar_productos(db_path)
    demanda = generar_demanda(productos, dias, semilla)
    inicio = fecha_inicio_simulacion(db_path)
    logger.info("Demanda congelada: %s productos x %s dias", len(productos), dias)

    resultados = [simular_politica(productos, demanda, dias, lead_time, "reactiva")]
    predictor = Predictor.cargar()
    info = predictor.get_model_info()
    for u in umbrales:
        resultados.append(
            simular_politica(
                productos, demanda, dias, lead_time, "predictiva", predictor, u,
                red_seguridad=red_seguridad,
            )
        )

    base = resultados[0]["unidades_no_servidas"]
    for r in resultados:
        r["mejora_servicio_pct"] = round(
            100 * (base - r["unidades_no_servidas"]) / max(base, 1), 1
        )

    fechas = [(inicio + timedelta(days=d)).isoformat() for d in range(dias)]
    return {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dias": dias,
        "lead_time_dias": lead_time,
        "productos": len(productos),
        "fecha_inicio": inicio.isoformat(),
        "version_modelo": info["version_modelo"],
        "origen_modelo": info["origen_datos"],
        "estado_validacion": info["estado_validacion"],
        "fechas": fechas,
        "politicas": resultados,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Compara politicas de reposicion")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--dias", type=int, default=365)
    parser.add_argument("--lead-time", type=int, default=config.LEAD_TIME_DIAS)
    parser.add_argument("--semilla", type=int, default=777)
    parser.add_argument("--umbral", type=float, action="append", default=None)
    parser.add_argument(
        "--sin-red",
        action="store_true",
        help="Desactiva la red de seguridad (reproduce el comportamiento degenerado)",
    )
    parser.add_argument("--salida", type=Path, default=config.ARTIFACTS_DIR / "reports")
    args = parser.parse_args()

    umbrales = args.umbral or [0.8]
    resultado = comparar(
        args.db, args.dias, args.lead_time, args.semilla, umbrales,
        red_seguridad=not args.sin_red,
    )

    tabla = pd.DataFrame(
        [
            {k: v for k, v in r.items() if not k.startswith("serie_")}
            for r in resultado["politicas"]
        ]
    ).set_index("politica")
    print("\n=== Comparacion de politicas (misma demanda) ===")
    print(tabla.to_string())
    print(
        "\ndias_agotado_utiles cuenta solo productos CON demanda."
        "\nLa metrica que decide es unidades_no_servidas."
    )

    args.salida.mkdir(parents=True, exist_ok=True)
    destino = args.salida / NOMBRE_JSON
    destino.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    tabla.to_csv(args.salida / "comparacion_politicas.csv")
    logger.info("Guardado en %s", destino)


if __name__ == "__main__":
    main()
