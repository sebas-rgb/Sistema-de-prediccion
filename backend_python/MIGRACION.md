# Fase 0 — Reorganización previa a FastAPI

Este esqueleto cubre lo que el documento de objetivos daba por hecho pero no existía.
Cuando termines esta guía, el brief de FastAPI se vuelve ejecutable tal cual está escrito.

## Estado

| Pieza | Estado |
|---|---|
| `config.py` (rutas, horizonte, umbrales de riesgo) | ✅ hecho |
| `features/dataset.py` (contrato de columnas + encoding fijo) | ✅ hecho |
| `training/train.py` (Pipeline + metadata) | ✅ hecho |
| `inference/predictor.py` | ✅ hecho |
| `tests/test_contrato_modelo.py` (8 tests) | ✅ pasan |
| `ingestion/` (tu `main.py` + `crear_sqlite_db.py`) | ⬜ pendiente, paso 2 |
| `simulation/` (tu `simulador.py`) | ⬜ pendiente, paso 3 |
| `reporting/riesgo.py` (CSV para Java) | ✅ hecho |
| `api/` (FastAPI) | ⬜ fase siguiente |

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

`pip install -e .` es lo que elimina el problema de las rutas relativas: a partir
de aquí puedes ejecutar cualquier módulo desde cualquier directorio.

## Paso 1 — Retirar `riesgo_agotamiento.py` y el modelo viejo

`riesgo_agotamiento.py` era el script de entrenamiento. Hacía tres cosas
mezcladas, que ahora viven separadas:

| Parte del script | Ahora |
|---|---|
| construcción del target y merge | `features.construir_dataset()` |
| split + fit + `joblib.dump` | `training/train.py` |
| scoring del stock actual | `inference.Predictor.predict_batch()` |
| umbrales 70/40 y CSV de salida | `config.nivel_riesgo()` + `reporting/riesgo.py` |

Sus hiperparámetros (`n_estimators=200, max_depth=12, random_state=42`) se
conservaron tal cual en `construir_pipeline()`. `--balancear` añade
`class_weight="balanced"`, que **no** estaba en el original; queda opcional.

`models/modelo_agotamiento.pkl` se archiva en `legacy/`: fue entrenado con el
split aleatorio y con el encoding frágil, así que sus probabilidades no son
confiables. No lo cargues desde `inference`.

Reentrenar cuesta segundos:

```bash
python -m inventory_ml.training.train --db data/inventario.db
```

Esto genera `artifacts/models/stockout_simulated_v1.joblib` **y** su
`.metadata.json` con versión, algoritmo, horizonte, `origen_datos=SIMULADO` y
`estado_validacion=NO_VALIDADO_CON_DATOS_REALES`.

## Paso 2 — Mover `main.py` a `ingestion/perfilado.py`

Es el ETL Excel/CSV → perfil de productos JSON. Al moverlo:

- envuelve todo en `def perfilar(csv_path) -> list[dict]` y `def main()`;
- sustituye `exit()` por `raise SystemExit(1)` dentro de `main()`;
- sustituye el `except:` desnudo de `parse_fecha` por `except (ValueError, TypeError)`;
- corrige `round(x, 2) if dias_hasta_agotarse else None` → `if dias_hasta_agotarse is not None`
  (hoy un valor `0.0` se convierte en `None` silenciosamente);
- añade `np.random.seed(SEMILLA)` antes del muestreo del sample, o el JSON
  cambia en cada ejecución y la simulación deja de ser reproducible;
- toma la ruta del CSV como argumento, no como constante relativa al cwd.

`crear_sqlite_db.py` puede borrarse: `simulador.py` elimina y recrea la DB de
todos modos, y sus dos esquemas no coinciden (`stock_inicial REAL` vs `INTEGER`).
Deja **un solo** DDL, en `simulation/esquema.sql` o dentro del simulador.

## Paso 3 — Mover `simulador.py` a `simulation/simulador.py`

- envuélvelo en `def simular(config, productos, db_path)` + `main()`;
- **la semilla debe ser un parámetro, no un valor fijo del config**. Hoy
  `random.seed(config["semilla_random"])` hace que cada corrida produzca datos
  idénticos, así que la "validación externa" de `validar_modelo.py` estaba
  evaluando sobre los mismos datos de entrenamiento. Usa `--semilla` distinta
  para generar un set de validación de verdad;
- `p["stock_promedio"]` se lee del JSON pero nunca se guarda en la tabla
  `productos`: o lo añades al esquema o lo dejas fuera del cálculo de reposición;
- saca `fecha_inicio = datetime(2026,1,1)` al config.

## Paso 4 — Regenerar los CSV que consume Java

`riesgo_productos.csv`, `alto_riesgo.csv`, `riesgo_medio.csv`, `riesgo_bajo.csv`
y `top50_riesgo.csv` los produce ahora:

```bash
python -m inventory_ml.reporting.riesgo --db data/inventario.db
```

Salen a `artifacts/reports/`. Este módulo existe solo para que Spring Boot siga
funcionando con sus CSV estáticos hasta que consuma la API; después se borra.
Compara una corrida contra tus CSV actuales antes de apuntar Java a la ruta
nueva: las probabilidades **van a cambiar**, porque el modelo viejo estaba
entrenado con leakage.

## Paso 5 — Retirar `validar_modelo.py`

Su construcción de dataset ya vive, vectorizada, en `features/construir_dataset()`,
y su evaluación ya vive en `training/train.py` con split temporal. Si quieres
conservar la validación contra una simulación independiente, reescríbela como
`training/validar.py` que importe `construir_dataset` y `Predictor` — sin volver
a codificar `clase` a mano.

## Decisiones tomadas (documentadas para el informe final)

0. **Bugs corregidos del script original**: split aleatorio sobre serie temporal
   (el mismo producto caía en train y test con filas casi idénticas → métricas
   infladas), y doble codificación independiente de `clase` con `.cat.codes`
   en entrenamiento e inferencia (con un solo producto siempre devuelve 0).
1. **Encoding de `clase`**: `OrdinalEncoder` con categorías fijas
   `["Muerto", "Baja", "Media", "Alta"]` dentro del Pipeline. Orden ordinal por
   nivel de actividad, no alfabético. `handle_unknown="use_encoded_value"` con
   `-1` para que una clase nueva no reviente la inferencia.
2. **Clase positiva**: se resuelve con `list(pipeline.classes_).index(1)`, nunca
   asumiendo `[:, 1]`. Cubierto por test.
3. **Split temporal** en lugar de aleatorio: con series por producto, un split
   aleatorio filtra el futuro al entrenamiento e infla las métricas.
4. **Umbrales de riesgo** (ALTO > 0.70, MEDIO 0.40–0.70, BAJO < 0.40) viven solo
   en `config.nivel_riesgo()`. Ningún otro archivo los repite.
5. **`origen_datos` / `estado_validacion`** se escriben en la metadata en tiempo
   de entrenamiento y se propagan a cada respuesta. Cambiar a un modelo real
   solo requiere reentrenar con otras constantes, sin tocar código de la API.

## Nota sobre la calidad del modelo

Las features de producto (`consumo_promedio`, `clase`, etc.) son **constantes por
producto**: lo único que varía en el tiempo es `stock_actual`. Con datos de un
simulador determinista, el modelo aprende sobre todo la regla del propio
simulador. Las métricas serán buenas y **no significarán casi nada** hasta que
entren datos reales. Por eso `NO_VALIDADO_CON_DATOS_REALES` no es un formalismo:
es literalmente el estado del modelo.

## Siguiente fase

Con el `Predictor` en pie, FastAPI queda como capa delgada:

```
POST /predict  →  Predictor.predict(dict)        →  Pipeline
POST /predict/batch  →  Predictor.predict_batch(list)  →  Pipeline (1 sola llamada)
GET  /model/info     →  Predictor.get_model_info()
GET  /health         →  ¿existe el Predictor en app.state?
```

El `lifespan` de FastAPI llama a `Predictor.cargar()` una vez; si lanza
`ModeloNoDisponibleError`, la app arranca con `model_loaded=false` y `/predict`
devuelve 503.
