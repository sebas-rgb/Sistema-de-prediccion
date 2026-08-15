"""Contrato de features del proyecto.

Este modulo es la UNICA fuente de verdad sobre:
  - que columnas entran al modelo y en que orden;
  - como se codifica la variable categorica `clase`.

training, inference y la futura API importan de aqui. Nadie reimplementa esto.
"""

from __future__ import annotations

import pandas as pd

from inventory_ml.config import HORIZONTE_DIAS

# ---------------------------------------------------------------
# Contrato de columnas
# ---------------------------------------------------------------

COLUMNA_CATEGORICA = "clase"

COLUMNAS_NUMERICAS: list[str] = [
    "stock_actual",
    "consumo_promedio",
    "consumo_minimo",
    "consumo_maximo",
    "reposicion_promedio",
    "frecuencia_movimiento",
]

# Orden estable que espera el Pipeline. NO reordenar sin reentrenar.
FEATURES: list[str] = COLUMNAS_NUMERICAS + [COLUMNA_CATEGORICA]

# Orden ordinal explicito por nivel de actividad (no alfabetico).
# El bug del codigo anterior era usar .astype("category").cat.codes, que
# depende de que valores aparecen en cada lote. Esto es fijo para siempre.
CLASES: list[str] = ["Muerto", "Baja", "Media", "Alta"]
CLASE_DESCONOCIDA = -1

TARGET = f"agotado_{HORIZONTE_DIAS}d"


class ContratoFeaturesError(ValueError):
    """La entrada no cumple el contrato de features esperado."""


def validar_columnas(df: pd.DataFrame) -> None:
    faltantes = [c for c in FEATURES if c not in df.columns]
    if faltantes:
        raise ContratoFeaturesError(f"Faltan columnas requeridas: {faltantes}")


def preparar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve el DataFrame con exactamente las columnas de FEATURES, en orden.

    No codifica `clase`: de eso se encarga el Pipeline (OrdinalEncoder).
    """
    validar_columnas(df)
    salida = df.loc[:, FEATURES].copy()
    for col in COLUMNAS_NUMERICAS:
        salida[col] = pd.to_numeric(salida[col], errors="coerce")
    salida[COLUMNA_CATEGORICA] = salida[COLUMNA_CATEGORICA].astype(str)
    return salida


# ---------------------------------------------------------------
# Construccion del dataset supervisado
# ---------------------------------------------------------------


def construir_dataset(
    inventario: pd.DataFrame,
    productos: pd.DataFrame,
    horizonte_dias: int = HORIZONTE_DIAS,
) -> pd.DataFrame:
    """Cruza snapshots diarios de inventario con atributos de producto.

    Supuesto: `inventario` tiene exactamente un snapshot por (codigo, dia)
    y los dias son contiguos por producto (lo garantiza el simulador).
    Bajo ese supuesto, shift(-horizonte) equivale a mirar el stock a N dias.

    Devuelve columnas: codigo, fecha, FEATURES..., TARGET.
    """
    inv = inventario.copy()
    inv["fecha"] = pd.to_datetime(inv["fecha"])
    inv = inv.sort_values(["codigo", "fecha"])

    duplicados = inv.duplicated(subset=["codigo", "fecha"]).sum()
    if duplicados:
        raise ContratoFeaturesError(
            f"Hay {duplicados} snapshots duplicados (codigo, fecha) en inventario"
        )

    inv["stock_futuro"] = inv.groupby("codigo")["stock"].shift(-horizonte_dias)
    inv = inv.dropna(subset=["stock_futuro"])
    inv[TARGET] = (inv["stock_futuro"] <= 0).astype(int)
    inv = inv.rename(columns={"stock": "stock_actual"})

    prods = productos.copy()
    prods["codigo"] = prods["codigo"].astype(str)
    inv["codigo"] = inv["codigo"].astype(str)

    dataset = inv.merge(prods, on="codigo", how="left", validate="many_to_one")

    sin_producto = dataset[COLUMNA_CATEGORICA].isna().sum()
    if sin_producto:
        raise ContratoFeaturesError(
            f"{sin_producto} filas de inventario sin producto asociado"
        )

    return dataset[["codigo", "fecha", *FEATURES, TARGET]]
