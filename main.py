from pathlib import Path
import pandas as pd
import numpy as np
import json

csv_path = Path("inventario_consolidado.csv")

excel_output = csv_path.with_name("inventario_simulacion.xlsx")
json_output = csv_path.with_name("productos_simulacion.json")
json_sample_output = csv_path.with_name("productos_simulacion_sample.json")

LEAD_TIME_DIAS = 30

if not csv_path.exists():
    print(f"No se encontró {csv_path.name}")
    exit()

df = pd.read_csv(csv_path)

fecha_col = next(
    (c for c in df.columns if "fecha" in c.lower()),
    None
)

codigo_col = next(
    (
        c for c in df.columns
        if "codigo" in c.lower()
        or "código" in c.lower()
    ),
    None
)

stock_col = next(
    (
        c for c in df.columns
        if "t.unid" in c.lower()
        or "unid" in c.lower()
    ),
    None
)

if not all([fecha_col, codigo_col, stock_col]):
    print("Columnas encontradas:")
    print(df.columns.tolist())
    exit()

# ------------------------
# Ordenar fechas
# ------------------------

def parse_fecha(valor):
    try:
        d, m, y = str(valor).split("_")
        return pd.Timestamp(
            year=int(y),
            month=int(m),
            day=int(d)
        )
    except:
        return pd.NaT

df["FechaReal"] = df[fecha_col].apply(parse_fecha)

df = df.sort_values(
    [codigo_col, "FechaReal"]
)

df[stock_col] = (
    pd.to_numeric(
        df[stock_col],
        errors="coerce"
    )
    .fillna(0)
)

resultados = []
productos_json = []

for codigo, g in df.groupby(codigo_col):

    s = g[stock_col].astype(float).values

    if len(s) < 2:
        continue

    diffs = np.diff(s)

    cambios = int(np.sum(diffs != 0))

    frecuencia = cambios / max(len(s) - 1, 1)

    # ------------------------
    # Clasificación
    # ------------------------

    if frecuencia == 0:
        clase = "Muerto"
    elif frecuencia < 0.05:
        clase = "Baja"
    elif frecuencia < 0.20:
        clase = "Media"
    else:
        clase = "Alta"

    bajas = np.abs(diffs[diffs < 0])
    subidas = diffs[diffs > 0]

    consumo_promedio = (
        float(bajas.mean())
        if len(bajas)
        else 0
    )

    consumo_maximo = (
        float(bajas.max())
        if len(bajas)
        else 0
    )

    consumo_minimo = (
        float(bajas.min())
        if len(bajas)
        else 0
    )

    reposicion_promedio = (
        float(subidas.mean())
        if len(subidas)
        else 0
    )

    reposicion_maxima = (
        float(subidas.max())
        if len(subidas)
        else 0
    )

    stock_actual = float(s[-1])

    stock_inicial = float(s[0])

    stock_promedio = float(np.mean(s))

    dias_hasta_agotarse = None

    if consumo_promedio > 0:
        dias_hasta_agotarse = (
            stock_actual /
            consumo_promedio
        )

    punto_reorden = (
        consumo_promedio *
        LEAD_TIME_DIAS
    )

    fila = {

        "Codigo": codigo,

        "Clase": clase,

        "Observaciones": len(s),

        "Cambios": cambios,

        "FrecuenciaMovimiento":
            round(frecuencia, 4),

        "StockInicial":
            round(stock_inicial, 2),

        "StockActual":
            round(stock_actual, 2),

        "StockPromedio":
            round(stock_promedio, 2),

        "StockMin":
            round(float(np.min(s)), 2),

        "StockMax":
            round(float(np.max(s)), 2),

        "VariacionTotal":
            round(
                float(np.max(s) - np.min(s)),
                2
            ),

        "ConsumoPromedio":
            round(consumo_promedio, 2),

        "ConsumoMaximo":
            round(consumo_maximo, 2),

        "ConsumoMinimo":
            round(consumo_minimo, 2),

        "ReposicionPromedio":
            round(reposicion_promedio, 2),

        "ReposicionMaxima":
            round(reposicion_maxima, 2),

        "DiasHastaAgotarse":
            round(dias_hasta_agotarse, 2)
            if dias_hasta_agotarse
            else None,

        "PuntoReorden":
            round(punto_reorden, 2)

    }

    resultados.append(fila)

    productos_json.append({

        "codigo": str(codigo),

        "clase": clase,

        "stock_actual":
            round(stock_actual, 2),

        "stock_promedio":
            round(stock_promedio, 2),

        "consumo_promedio":
            round(consumo_promedio, 2),

        "consumo_maximo":
            round(consumo_maximo, 2),

        "consumo_minimo":
            round(consumo_minimo, 2),

        "reposicion_promedio":
            round(reposicion_promedio, 2),

        "reposicion_maxima":
            round(reposicion_maxima, 2),

        "frecuencia_movimiento":
            round(frecuencia, 4),

        "dias_hasta_agotarse":
            round(dias_hasta_agotarse, 2)
            if dias_hasta_agotarse
            else None,

        "punto_reorden":
            round(punto_reorden, 2)

    })

# ------------------------
# Excel
# ------------------------

out = pd.DataFrame(resultados)

out.to_excel(
    excel_output,
    index=False
)

# ------------------------
# JSON completo
# ------------------------

with open(
    json_output,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        productos_json,
        f,
        ensure_ascii=False,
        indent=2
    )

# ------------------------
# JSON pequeño
# ------------------------

sample = []

for clase in [
    "Muerto",
    "Baja",
    "Media",
    "Alta"
]:

    subset = [
        p
        for p in productos_json
        if p["clase"] == clase
    ]

    n = min(100, len(subset))

    sample.extend(
        list(
            np.random.choice(
                subset,
                n,
                replace=False
            )
        )
    )

with open(
    json_sample_output,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        sample,
        f,
        ensure_ascii=False,
        indent=2
    )

print("Generados:")
print(excel_output)
print(json_output)
print(json_sample_output)