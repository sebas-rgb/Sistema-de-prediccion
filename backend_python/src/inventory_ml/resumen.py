"""Resumen compacto del inventario para alimentar al asistente.

No se le manda el CSV completo al modelo: 400 filas crudas son caras, lentas y
producen peores respuestas que un resumen curado. Aqui se destila lo que
realmente importa para decidir compras.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from inventory_ml import config
from inventory_ml.inference import Predictor
from inventory_ml.repository import estado_en_fecha


def construir_resumen(
    predictor: Predictor,
    db_path: Path | None = None,
    fecha: date | None = None,
    top: int | None = None,
) -> dict:
    """Estado agregado del inventario en una fecha, listo para el prompt."""
    db_path = Path(db_path or config.DB_PATH)
    top = top or config.LLM_TOP_RIESGO

    # limite alto: se necesita el catalogo entero para agregar bien
    fecha_efectiva, total, registros = estado_en_fecha(
        db_path, fecha=fecha, limite=100_000, desplazamiento=0
    )
    predicciones = predictor.predict_batch(registros) if registros else []

    filas = [
        {
            "codigo": reg["codigo"],
            "stock": reg["stock_actual"],
            "clase": reg["clase"],
            "consumo": reg["consumo_promedio"],
            "prob": pred["probabilidad_agotamiento"],
            "riesgo": pred["nivel_riesgo"],
        }
        for reg, pred in zip(registros, predicciones)
    ]

    # Los productos sin consumo no son prioridad de compra aunque esten en cero
    con_demanda = [f for f in filas if f["consumo"] > 0]
    en_cero = [f for f in con_demanda if f["stock"] <= 0]

    conteo_riesgo: dict[str, int] = {"ALTO": 0, "MEDIO": 0, "BAJO": 0}
    for f in filas:
        conteo_riesgo[f["riesgo"]] = conteo_riesgo.get(f["riesgo"], 0) + 1

    conteo_clase: dict[str, int] = {}
    for f in filas:
        conteo_clase[f["clase"]] = conteo_clase.get(f["clase"], 0) + 1

    criticos = sorted(con_demanda, key=lambda f: -f["prob"])[:top]

    info = predictor.get_model_info()
    return {
        "fecha": fecha_efectiva.isoformat(),
        "total_productos": total,
        "productos_con_demanda": len(con_demanda),
        "productos_sin_stock_con_demanda": len(en_cero),
        "conteo_por_riesgo": conteo_riesgo,
        "conteo_por_clase": conteo_clase,
        "criticos": criticos,
        "modelo": {
            "version": info["version_modelo"],
            "horizonte_dias": info["horizonte_dias"],
            "origen_datos": info["origen_datos"],
            "estado_validacion": info["estado_validacion"],
        },
    }


def resumen_a_texto(resumen: dict) -> str:
    """Version en texto plano: mas barata en tokens que el JSON con llaves."""
    lineas = [
        f"Fecha del inventario: {resumen['fecha']}",
        f"Productos en catalogo: {resumen['total_productos']}",
        f"Con demanda historica: {resumen['productos_con_demanda']}",
        f"Sin stock y con demanda: {resumen['productos_sin_stock_con_demanda']}",
        "",
        "Distribucion de riesgo: "
        + ", ".join(f"{k}={v}" for k, v in resumen["conteo_por_riesgo"].items()),
        "Distribucion por clase de rotacion: "
        + ", ".join(f"{k}={v}" for k, v in resumen["conteo_por_clase"].items()),
        "",
        f"Top {len(resumen['criticos'])} productos de mayor riesgo (solo con demanda):",
        "codigo | stock | clase | consumo_promedio | probabilidad | nivel",
    ]
    for f in resumen["criticos"]:
        lineas.append(
            f"{f['codigo']} | {f['stock']:g} | {f['clase']} | "
            f"{f['consumo']:.2f} | {f['prob']:.1%} | {f['riesgo']}"
        )

    m = resumen["modelo"]
    lineas += [
        "",
        f"Modelo {m['version']}, horizonte {m['horizonte_dias']} dias, "
        f"origen {m['origen_datos']}, validacion {m['estado_validacion']}.",
    ]
    return "\n".join(lineas)
