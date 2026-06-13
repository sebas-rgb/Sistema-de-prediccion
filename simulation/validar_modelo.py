import sqlite3
import pandas as pd
import joblib
import os

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)

HORIZONTE = 30

# Rutas organizadas
BASE_DIR = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE_DIR, "db")
MODELS_DIR = os.path.join(BASE_DIR, "models")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ----------------------------------
# Cargar modelo ya entrenado
# ----------------------------------

model_path = os.path.join(MODELS_DIR, "modelo_agotamiento.pkl")
modelo = joblib.load(model_path)

# ----------------------------------
# Leer nueva simulación
# ----------------------------------

db_path = os.path.join(DB_DIR, "inventario.db")
conn = sqlite3.connect(db_path)

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
# Construir dataset exactamente igual
# ----------------------------------

targets = []

for codigo, g in inventario.groupby("codigo"):
    g = g.sort_values("fecha")
    stocks = g["stock"].values
    fechas = g["fecha"].values
    for i in range(len(g) - HORIZONTE):
        stock_actual = stocks[i]
        fecha_actual = fechas[i]
        stock_futuro = stocks[i + HORIZONTE]
        targets.append({
            "codigo": codigo,
            "fecha": fecha_actual,
            "stock_actual": stock_actual,
            "agotado_30d": int(stock_futuro <= 0)
        })

dataset = pd.DataFrame(targets)

# ----------------------------------
# Unir características producto
# ----------------------------------

dataset = dataset.merge(
    productos,
    on="codigo",
    how="left"
)

dataset["clase"] = (
    dataset["clase"]
    .astype("category")
    .cat.codes
)

# Keep only the most recent observation per codigo (that has a 30-day forward look)
dataset = dataset.sort_values("fecha", ascending=False)
dataset = dataset.drop_duplicates(subset=["codigo"], keep="first")

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
# Evaluar modelo
# ----------------------------------

pred = modelo.predict(X)

print("\n====================")
print("VALIDACIÓN EXTERNA")
print("====================")

print("\nAccuracy")
print(
    accuracy_score(
        y,
        pred
    )
)

print("\nReporte")
print(
    classification_report(
        y,
        pred
    )
)

print("\nMatriz")
print(
    confusion_matrix(
        y,
        pred
    )
)

# ----------------------------------
# Probabilidades
# ----------------------------------

probas = modelo.predict_proba(X)

dataset[
    "probabilidad_agotamiento"
] = probas[:, 1]

print("\nProbabilidad promedio:")
print(
    dataset[
        "probabilidad_agotamiento"
    ].mean()
)

print("\nTop ejemplos:")

print(
    dataset[[
        "codigo",
        "stock_actual",
        "probabilidad_agotamiento"
    ]]
    .sort_values(
        "probabilidad_agotamiento",
        ascending=False
    )
    .head(20)
)

dataset.to_csv(
    os.path.join(RESULTS_DIR, "validacion_externa.csv"),
    index=False
)

print(
    "\nArchivo generado:"
)
print(
    os.path.join(RESULTS_DIR, "validacion_externa.csv")
)