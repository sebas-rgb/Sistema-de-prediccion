"""Herramientas que el asistente puede invocar por su cuenta.

Aqui vive el salto de "asistente" a "agente": en vez de recibir un resumen fijo
y responder de una, el modelo decide que le falta, lo pide, y usa el resultado.

Cada funcion envuelve logica que YA existe en el proyecto (repository,
Predictor, el experimento precalculado). No hay reglas de negocio nuevas: solo
la fachada que el modelo sabe llamar.

CONTRATO
--------
    funcion(predictor, fecha, **argumentos_del_modelo) -> dict serializable

Devuelven un dict con la clave "error" en vez de lanzar. Una excepcion aqui
aborta la conversacion entera; un error en texto el modelo lo lee, lo entiende
y lo explica o reintenta con otros argumentos.

Las salidas son deliberadamente compactas: cada resultado vuelve al prompt en
la siguiente vuelta del bucle, asi que un dict grande se paga en tokens en
todas las iteraciones restantes.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Callable

from inventory_ml import config
from inventory_ml.inference import Predictor
from inventory_ml.repository import estado_en_fecha
from inventory_ml.simulation.experimento import NOMBRE_JSON

logger = logging.getLogger(__name__)

# Tope de filas por consulta. El modelo puede afinar el filtro si necesita mas;
# devolver el catalogo entero encarece cada iteracion siguiente.
LIMITE_CONSULTA = 10

# El modelo puede encadenar herramientas, pero no indefinidamente. Cada vuelta
# reenvia el historial completo, asi que el tope no solo evita un bucle
# infinito: acota el gasto de tokens del peor caso.
MAX_ITERACIONES = 5

# Escenarios de stock por llamada a simular_escenario. Suficiente para barrer
# un rango util en una sola vuelta sin inflar el resultado que vuelve al prompt.
MAX_ESCENARIOS = 8


# ---------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------


def consultar_producto(
    predictor: Predictor, fecha: date | None, codigo: str
) -> dict[str, Any]:
    """Busca productos por codigo (coincidencia parcial) y los puntua."""
    fecha_efectiva, total, registros = estado_en_fecha(
        config.DB_PATH, fecha=fecha, codigo=codigo, limite=LIMITE_CONSULTA
    )
    if not registros:
        return {
            "error": f"Ningun producto contiene '{codigo}' en su codigo "
            f"en el inventario del {fecha_efectiva}."
        }

    predicciones = predictor.predict_batch(registros)
    return {
        "fecha": fecha_efectiva.isoformat(),
        "coincidencias": total,
        "mostrados": len(registros),
        "productos": [
            {
                "codigo": reg["codigo"],
                "stock": reg["stock_actual"],
                "clase": reg["clase"],
                "consumo_por_movimiento": reg["consumo_promedio"],
                "probabilidad_agotamiento": pred["probabilidad_agotamiento"],
                "nivel_riesgo": pred["nivel_riesgo"],
            }
            for reg, pred in zip(registros, predicciones)
        ],
    }


def _producto(fecha: date | None, codigo: str) -> dict | None:
    """Coincidencia exacta si la hay; si no, la primera parcial."""
    _, _, registros = estado_en_fecha(
        config.DB_PATH, fecha=fecha, codigo=codigo, limite=LIMITE_CONSULTA
    )
    return next((r for r in registros if r["codigo"] == codigo), registros[0]) if registros else None


def simular_escenario(
    predictor: Predictor,
    fecha: date | None,
    codigo: str,
    niveles_stock: list[float],
) -> dict[str, Any]:
    """Contrafactual: '¿y si este producto tuviera N unidades en vez de las que tiene?'

    Es la herramienta que convierte al asistente en algo util: responde
    preguntas que NO estan en el resumen porque dependen de una hipotesis que
    el usuario acaba de inventar.

    Acepta VARIOS niveles de una vez a proposito. La pregunta natural es
    "¿cuanto stock necesita para dejar de ser riesgo alto?", y responderla es
    tantear. Un nivel por llamada gastaba una vuelta del bucle por tanteo y el
    agente se quedaba sin iteraciones antes de encontrar la respuesta; ademas
    todos los escenarios se resuelven igual en una sola pasada vectorizada.
    """
    if isinstance(niveles_stock, (int, float)):  # el modelo mando un escalar
        niveles_stock = [niveles_stock]
    if not niveles_stock:
        return {"error": "Indica al menos un nivel de stock a simular."}
    if len(niveles_stock) > MAX_ESCENARIOS:
        return {"error": f"Maximo {MAX_ESCENARIOS} niveles de stock por llamada."}
    if any(n < 0 for n in niveles_stock):
        return {"error": "Los niveles de stock no pueden ser negativos."}

    actual = _producto(fecha, codigo)
    if actual is None:
        return {"error": f"No existe ningun producto con codigo '{codigo}'."}
    filas = [actual] + [{**actual, "stock_actual": n} for n in niveles_stock]

    predicciones = predictor.predict_batch(filas)
    real, escenarios = predicciones[0], predicciones[1:]
    return {
        "codigo": actual["codigo"],
        "clase": actual["clase"],
        "consumo_por_movimiento": actual["consumo_promedio"],
        "horizonte_dias": real["horizonte_dias"],
        "stock_real": actual["stock_actual"],
        "probabilidad_real": real["probabilidad_agotamiento"],
        "nivel_riesgo_real": real["nivel_riesgo"],
        "escenarios": [
            {
                "stock": n,
                "probabilidad": p["probabilidad_agotamiento"],
                "nivel_riesgo": p["nivel_riesgo"],
            }
            for n, p in zip(niveles_stock, escenarios)
        ],
    }


NIVELES = ["BAJO", "MEDIO", "ALTO"]


def stock_minimo(
    predictor: Predictor,
    fecha: date | None,
    codigo: str,
    nivel_objetivo: str = "MEDIO",
) -> dict[str, Any]:
    """Menor stock con el que el producto queda en `nivel_objetivo` o mejor.

    Antes el agente tanteaba con simular_escenario y leia mal el barrido (dijo
    "200 unidades" cuando a 200 seguia en ALTO). Aqui se resuelve exacto: una
    rejilla de enteros en una sola pasada vectorizada, y se exige que el nivel
    se MANTENGA para todo stock mayor de la rejilla. El bosque no es monotono:
    un valle aislado de probabilidad no cuenta como respuesta.
    """
    nivel_objetivo = str(nivel_objetivo).upper()
    if nivel_objetivo not in ("BAJO", "MEDIO"):
        return {"error": "nivel_objetivo debe ser 'MEDIO' (salir de ALTO) o 'BAJO'."}
    actual = _producto(fecha, codigo)
    if actual is None:
        return {"error": f"No existe ningun producto con codigo '{codigo}'."}

    # Tope: 10 veces el peor consumo sostenido durante el horizonte.
    tope = int(max(1000, actual["consumo_maximo"] * config.HORIZONTE_DIAS * 10))
    paso = max(1, tope // 3000)  # rejilla gruesa y luego enteros: 2 pasadas vectorizadas

    def evaluar(stocks: list[int]) -> list[dict]:
        return predictor.predict_batch([{**actual, "stock_actual": n} for n in stocks])

    def primero_estable(preds: list[dict]) -> int | None:
        """Indice desde el que TODOS los siguientes cumplen el objetivo."""
        indice = None
        for i in range(len(preds) - 1, -1, -1):
            if NIVELES.index(preds[i]["nivel_riesgo"]) > NIVELES.index(nivel_objetivo):
                break
            indice = i
        return indice

    real = predictor.predict(actual)
    rejilla = list(range(0, tope + 1, paso))
    preds = evaluar(rejilla)
    indice = primero_estable(preds)
    if indice is None:
        return {
            "codigo": actual["codigo"],
            "error": f"Ni con {tope} unidades el modelo lo baja a {nivel_objetivo}.",
        }
    if paso > 1 and indice > 0:
        # Afinar entre el ultimo punto que no cumplia y el elegido
        finos = list(range(rejilla[indice - 1] + 1, rejilla[indice] + 1))
        preds_finos = evaluar(finos)
        rejilla, preds, indice = finos, preds_finos, primero_estable(preds_finos)

    minimo = rejilla[indice]
    return {
        "codigo": actual["codigo"],
        "stock_real": actual["stock_actual"],
        "probabilidad_real": real["probabilidad_agotamiento"],
        "nivel_riesgo_real": real["nivel_riesgo"],
        "nivel_objetivo": nivel_objetivo,
        "stock_minimo": minimo,
        "unidades_a_agregar": max(0, minimo - actual["stock_actual"]),
        "probabilidad_en_minimo": preds[indice]["probabilidad_agotamiento"],
        "nivel_en_minimo": preds[indice]["nivel_riesgo"],
    }


def comparar_politicas(predictor: Predictor, fecha: date | None) -> dict[str, Any]:
    """Resultado del experimento contrafactual reactiva vs. predictiva."""
    ruta = config.ARTIFACTS_DIR / "reports" / NOMBRE_JSON
    if not ruta.exists():
        return {
            "error": "El experimento de comparacion de politicas todavia no se ha "
            "ejecutado, asi que no hay cifras que reportar."
        }
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"error": "El resultado del experimento esta corrupto."}

    # `fechas` y `serie_agotados` son series de 365 puntos: sirven para graficar,
    # no para razonar, y arruinarian el presupuesto de tokens.
    return {
        "dias_simulados": datos["dias"],
        "lead_time_dias": datos["lead_time_dias"],
        "productos": datos["productos"],
        "politicas": [
            {k: v for k, v in p.items() if k != "serie_agotados"}
            for p in datos["politicas"]
        ],
    }


# ---------------------------------------------------------------
# Lo que ve el modelo
# ---------------------------------------------------------------
# Las descripciones son parte funcional del sistema, no comentarios: son lo
# unico que el modelo tiene para decidir CUANDO llamar a cada herramienta. Una
# descripcion vaga produce un agente que no llama a nada, o que llama a todo.

DEFINICIONES: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_producto",
            "description": (
                "Consulta el estado y la probabilidad de agotamiento de un producto "
                "concreto por su codigo. Usala cuando el usuario pregunte por un "
                "codigo especifico que no aparece en el resumen del inventario. "
                "Acepta coincidencias parciales del codigo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "Codigo del producto, total o parcial.",
                    }
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simular_escenario",
            "description": (
                "Recalcula la probabilidad de agotamiento de un producto para uno o "
                "varios niveles de stock hipoteticos, en una sola llamada. Usala para "
                "'¿que pasaria si compro N unidades de X?' o para comparar cantidades "
                "concretas que proponga el usuario. Para buscar el stock que hace "
                "falta, usa stock_minimo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "description": "Codigo del producto."},
                    "niveles_stock": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": (
                            f"Hasta {MAX_ESCENARIOS} cantidades de stock a evaluar."
                        ),
                    },
                },
                "required": ["codigo", "niveles_stock"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stock_minimo",
            "description": (
                "Calcula EXACTAMENTE el menor stock con el que un producto deja de "
                "ser riesgo alto (nivel_objetivo MEDIO) o llega a riesgo bajo "
                "(nivel_objetivo BAJO). Usala SIEMPRE para '¿cuanto stock necesita X "
                "para dejar de ser riesgo alto?' o '¿cuanto debo comprar de X?'; no "
                "tantees con simular_escenario. Reporta stock_minimo y "
                "unidades_a_agregar tal cual."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "description": "Codigo del producto."},
                    "nivel_objetivo": {
                        "type": "string",
                        "enum": ["MEDIO", "BAJO"],
                        "description": "MEDIO = salir de riesgo alto (por defecto).",
                    },
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comparar_politicas",
            "description": (
                "Devuelve las cifras del experimento que compara la politica de "
                "reposicion actual (pedir cuando el stock llega a cero) contra la "
                "politica que anticipa usando el modelo, sobre la misma demanda "
                "simulada. Usala cuando pregunten si el modelo sirve, cuanto mejora "
                "el servicio, o cuanto inventario extra cuesta."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_REGISTRO: dict[str, Callable[..., dict]] = {
    "consultar_producto": consultar_producto,
    "simular_escenario": simular_escenario,
    "stock_minimo": stock_minimo,
    "comparar_politicas": comparar_politicas,
}


def ejecutar(
    nombre: str, argumentos: str, predictor: Predictor, fecha: date | None
) -> dict[str, Any]:
    """Despacha una llamada del modelo. NUNCA lanza: todo fallo vuelve como texto.

    `argumentos` llega como el JSON crudo que genero el modelo, que puede estar
    malformado o traer claves que la funcion no acepta.
    """
    funcion = _REGISTRO.get(nombre)
    if funcion is None:
        return {"error": f"La herramienta '{nombre}' no existe."}

    try:
        kwargs = json.loads(argumentos) if argumentos else {}
    except json.JSONDecodeError:
        return {"error": f"Los argumentos de '{nombre}' no son JSON valido."}
    if not isinstance(kwargs, dict):
        return {"error": f"Los argumentos de '{nombre}' deben ser un objeto JSON."}

    try:
        return funcion(predictor, fecha, **kwargs)
    except TypeError as exc:
        # Argumentos que no encajan con la firma: el modelo puede corregirse.
        return {"error": f"Argumentos invalidos para '{nombre}': {exc}"}
    except Exception as exc:
        logger.exception("Fallo la herramienta %s", nombre)
        return {"error": f"'{nombre}' fallo: {type(exc).__name__}"}
