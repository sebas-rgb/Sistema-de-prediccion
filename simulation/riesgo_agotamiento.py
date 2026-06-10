import sqlite3
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    accuracy_score,
    confusion_matrix
)

import joblib

HORIZONTE = 30

conn = sqlite3.connect("inventario.db")

inventario = pd.read_sql("""
SELECT *
FROM inventario
""", conn)

productos = pd.read_sql("""
SELECT *
FROM productos
""", conn)

conn.close()

inventario["fecha"] = pd.to_datetime(
    inventario["fecha"]
)

inventario = inventario.sort_values(
    ["codigo", "fecha"]
)

# ----------------------------------
# Crear target
# ----------------------------------

targets = []

for codigo, g in inventario.groupby("codigo"):

    g = g.sort_values("fecha")

    stocks = g["stock"].values

    for i in range(len(g) - HORIZONTE):

        stock_futuro = stocks[
            i + HORIZONTE
        ]

        targets.append({

            "codigo": codigo,

            "fecha": g.iloc[i]["fecha"],

            "stock_actual": stocks[i],

            "agotado_30d":
                int(stock_futuro <= 0)

        })

dataset = pd.DataFrame(targets)

# ----------------------------------
# Unir con info del producto
# ----------------------------------

dataset = dataset.merge(
    productos,
    on="codigo",
    how="left"
)

# ----------------------------------
# Clase -> número
# ----------------------------------

dataset["clase"] = (
    dataset["clase"]
    .astype("category")
    .cat.codes
)

# ----------------------------------
# Features
# ----------------------------------

X = dataset[[
    "stock_actual",
    "consumo_promedio",
    "consumo_minimo",
    "consumo_maximo",
    "reposicion_promedio",
    "frecuencia_movimiento",
    "clase"
]]

y = dataset["agotado_30d"]

# ----------------------------------
# Split
# ----------------------------------

X_train, X_test, y_train, y_test = (
    train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )
)

# ----------------------------------
# Modelo
# ----------------------------------

modelo = RandomForestClassifier(
    n_estimators=200,
    max_depth=12,
    random_state=42,
    n_jobs=-1
)

modelo.fit(
    X_train,
    y_train
)

pred = modelo.predict(X_test)

print("\nAccuracy")
print(
    accuracy_score(
        y_test,
        pred
    )
)

print("\nReporte")
print(
    classification_report(
        y_test,
        pred
    )
)

print("\nMatriz")
print(
    confusion_matrix(
        y_test,
        pred
    )
)

joblib.dump(
    modelo,
    "modelo_agotamiento.pkl"
)

# ----------------------------------
# Importancia de variables
# ----------------------------------

importancias = pd.DataFrame({
    "feature": X.columns,
    "importance": modelo.feature_importances_
})

print("\nImportancia variables:")
print(
    importancias
    .sort_values(
        "importance",
        ascending=False
    )
)

# ----------------------------------
# Obtener último stock conocido
# ----------------------------------

conn = sqlite3.connect("inventario.db")

ultimo_stock = pd.read_sql("""
SELECT i.codigo,
       i.stock
FROM inventario i
INNER JOIN (
    SELECT codigo,
           MAX(fecha) AS ultima_fecha
    FROM inventario
    GROUP BY codigo
) ult
ON i.codigo = ult.codigo
AND i.fecha = ult.ultima_fecha
""", conn)

conn.close()

# ----------------------------------
# Dataset para riesgo actual
# ----------------------------------

productos_actuales = productos.merge(
    ultimo_stock,
    on="codigo",
    how="left"
)

# Estadísticas antes de filtrar

total_productos = len(productos_actuales)

agotados = (
    productos_actuales["stock"] <= 0
).sum()

print(
    f"\nProductos totales: {total_productos}"
)

print(
    f"Productos agotados: {agotados}"
)

print(
    f"Productos activos: {total_productos - agotados}"
)

productos_actuales["clase"] = (
    productos_actuales["clase"]
    .astype("category")
    .cat.codes
)

# IMPORTANTÍSIMO:
# Deben llamarse EXACTAMENTE igual
# que durante el entrenamiento

X_riesgo = productos_actuales[[
    "stock",
    "consumo_promedio",
    "consumo_minimo",
    "consumo_maximo",
    "reposicion_promedio",
    "frecuencia_movimiento",
    "clase"
]].copy()

X_riesgo.columns = [
    "stock_actual",
    "consumo_promedio",
    "consumo_minimo",
    "consumo_maximo",
    "reposicion_promedio",
    "frecuencia_movimiento",
    "clase"
]

# ----------------------------------
# Predicción
# ----------------------------------

productos_actuales[
    "probabilidad_agotamiento"
] = modelo.predict_proba(
    X_riesgo
)[:, 1]

# ----------------------------------
# Quitar agotados
# ----------------------------------

productos_actuales = productos_actuales[
    productos_actuales["stock"] > 0
].copy()

# ----------------------------------
# Ordenar por riesgo
# ----------------------------------

productos_actuales = (
    productos_actuales
    .sort_values(
        "probabilidad_agotamiento",
        ascending=False
    )
)

# ----------------------------------
# Top riesgo
# ----------------------------------

alto_riesgo = productos_actuales[
    (
        productos_actuales[
            "probabilidad_agotamiento"
        ] > 0.70
    )
    &
    (
        productos_actuales["stock"] > 0
    )
]

riesgo_medio = productos_actuales[
    (
        productos_actuales[
            "probabilidad_agotamiento"
        ] >= 0.40
    )
    &
    (
        productos_actuales[
            "probabilidad_agotamiento"
        ] <= 0.70
    )
]

riesgo_bajo = productos_actuales[
    (
        productos_actuales[
            "probabilidad_agotamiento"
        ] < 0.40
    )
]

# ----------------------------------
# Guardar resultados
# ----------------------------------

productos_actuales.to_csv(
    "riesgo_productos.csv",
    index=False
)

productos_actuales.head(50).to_csv(
    "top50_riesgo.csv",
    index=False
)

alto_riesgo.to_csv(
    "alto_riesgo.csv",
    index=False
)

riesgo_medio.to_csv(
    "riesgo_medio.csv",
    index=False
)

riesgo_bajo.to_csv(
    "riesgo_bajo.csv",
    index=False
)

# ----------------------------------
# Resumen final
# ----------------------------------

print("\n=========================")
print("Modelo guardado")
print("modelo_agotamiento.pkl")
print("=========================")

print("\nArchivos generados:")

print("riesgo_productos.csv")
print("top50_riesgo.csv")
print("alto_riesgo.csv")
print("riesgo_medio.csv")
print("riesgo_bajo.csv")

print("\nResumen probabilidades:")

print(
    productos_actuales[
        "probabilidad_agotamiento"
    ].describe()
)

print(
    "\nProductos riesgo ALTO (>70%):",
    len(alto_riesgo)
)

print(
    "Productos riesgo MEDIO (40%-70%):",
    len(riesgo_medio)
)

print(
    "Productos riesgo BAJO (<40%):",
    len(riesgo_bajo)
)

print("\nTop 10 productos más riesgosos:")

print(
    productos_actuales[[
        "codigo",
        "stock",
        "probabilidad_agotamiento"
    ]]
    .head(10)
)