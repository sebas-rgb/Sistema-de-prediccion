# Ejecución: de los Excel al modelo

Todo lo demás es derivado y se regenera con estos cuatro comandos.

## Qué guardas y qué borras

| Guardas | Borras / archivas |
|---|---|
| `data/raw/inventarios/*.xlsx` (los meses) | `inventario.db` (las tres copias) |
| `data/raw/inventario_consolidado.csv` | `modelo_agotamiento.pkl` (las dos copias) |
| | `results/*.csv`, `figures/*.png` |
| | `productos_simulacion*.json` |
| | `inventario_clasificado.xlsx`, `inventario_simulacion.xlsx` |
| | `main.py`, `simulador.py`, `crear_sqlite_db.py`, `riesgo_agotamiento.py`, `validar_modelo.py` |

Archiva en `legacy/` en vez de borrar, hasta que compares resultados.

## La cadena

```bash
# 1. Perfilar: CSV histórico -> productos con clase y estadísticas
python -m inventory_ml.ingestion.perfilado --n-por-clase 100

# 2. Simular: 400 productos x 365 días -> data/inventario.db
python -m inventory_ml.simulation.simulador --dias 365

# 3. Entrenar: -> artifacts/models/stockout_simulated_v1.joblib + metadata
python -m inventory_ml.training.train

# 4. Reportar: -> artifacts/reports/*.csv (los que hoy lee Java)
python -m inventory_ml.reporting.riesgo
```

Cada paso lee la salida del anterior desde rutas por defecto de `config.py`.
Todos aceptan `--` para sobrescribir.

## Set de validación independiente

El bug del simulador original era la semilla fija: repetir la simulación daba
datos idénticos, así que la "validación externa" no validaba nada. Ahora:

```bash
python -m inventory_ml.simulation.simulador --semilla 99 --db data/validacion.db
```

Eso sí es un set nuevo. Ojo: sigue siendo el **mismo generador**, así que mide
consistencia, no capacidad predictiva sobre la realidad.

## Verificado

La cadena completa corre de punta a punta: 1.440 filas de CSV crudo → 60
productos perfilados → 365 días simulados → dataset de 20.100 filas → split
temporal → artefacto + metadata → CSV de riesgo. Con tus 400 productos los
números serán mayores; la mecánica es la misma.

## Sobre los Excel mensuales

`inventario_consolidado.csv` es la entrada del paso 1. No sé cómo lo generabas
desde los `.xlsx` mensuales — si era manual, ese es el único hueco que queda por
automatizar. Pásame un mes de muestra y lo añado como `ingestion/consolidar.py`.
