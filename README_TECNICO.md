# Documentación técnica — Predicción de agotamiento de inventario

Documento de sustentación. Explica **qué hace cada archivo, qué algoritmo se usa,
por qué se eligió, cómo se evalúa y qué limitaciones tiene**.

Para instalar y ejecutar, ver [`README.md`](README.md).

---

## 0. Lo primero: qué es y qué NO es este proyecto

Esta sección existe para que no te sorprendan en la sustentación. Todo lo que
sigue es verificable en el código.

| Lo que suele decirse | Lo que hay realmente | Dónde verificarlo |
|---|---|---|
| "Redes neuronales" | **Random Forest** (bosque de 200 árboles de decisión) | `training/train.py:104-110` |
| "Agente de IA" | **Sí**: bucle de *tool calling* con 3 herramientas | `api/asistente.py` + `herramientas.py` |
| "Predice el inventario" | Predice **una probabilidad binaria**: ¿se agota en 30 días, sí o no? | `features/dataset.py:100` |
| "Con datos de la empresa" | Perfilado desde datos reales, pero **entrenado sobre una simulación** | `artifacts/models/*.metadata.json` → `"origen_datos": "SIMULADO"` |

**La diferencia que queda no es un error.** Son decisiones técnicas defendibles
y la sección [§12](#12-preguntas-que-te-van-a-hacer-y-cómo-responderlas) te da
el argumento para cada una. Lo que sí sería un error es afirmar en la
sustentación algo que el código no hace: el jurado abre `train.py` y se cae el
proyecto.

Si el requisito de grado **exige literalmente** una red neuronal, ver
[§16](#16-si-el-requisito-exige-red-neuronal).

---

## 1. El problema

Un laboratorio óptico maneja ~400 referencias. El proceso actual de compra es
**reactivo**: se pide cuando el stock llega a cero. Como el proveedor tarda
30 días (*lead time*), cada quiebre son 30 días sin producto.

La pregunta que el proyecto responde es:

> Dado el estado de un producto **hoy**, ¿cuál es la probabilidad de que se
> quede sin stock en algún momento de los próximos 30 días?

Con esa probabilidad se puede pedir **antes** de llegar a cero. La sección
[§9](#9-el-experimento-contrafactual-la-prueba-de-que-sirve) demuestra
cuantitativamente que eso reduce los quiebres.

---

## 2. Arquitectura general

```
   Excel/CSV mensuales del laboratorio        (datos reales de movimiento)
              │
              ▼  ingestion/perfilado.py       perfila cada producto:
      productos_perfilados.json               clase, consumos, rotación
              │
              ▼  simulation/simulador.py      genera 365 días de movimientos
        inventario.db  (SQLite)               diarios producto a producto
              │
              ▼  features/dataset.py          construye el dataset supervisado
       X (7 features) + y (agotado_30d)       y define la etiqueta
              │
              ▼  training/train.py            entrena el Pipeline y lo serializa
   stockout_simulated_v1.joblib + metadata
              │
              ▼  inference/predictor.py       única puerta de entrada a predecir
              │
              ├──▶ api/            FastAPI  (puerto 8000)
              │      ├── /api/v1/predict           predicción bajo demanda
              │      ├── /api/v1/inventario        estado + predicción
              │      ├── /api/v1/experimento       comparación de políticas
              │      └── /api/v1/asistente         LLM sobre el inventario
              │
              ├──▶ reporting/riesgo.py    CSV estáticos (legado)
              └──▶ simulation/experimento.py   experimento contrafactual
                                 │
                                 ▼
                    Spring Boot (puerto 8080)  ──▶  navegador
                    proxy + sesión + Thymeleaf
```

**Dos procesos separados a propósito.** Python hace ML; Java hace autenticación,
sesión e interfaz. Se comunican por HTTP. FastAPI puede quedarse en la red
interna: el navegador nunca la toca directamente
(`InventarioController.java`, comentario de clase).

---

## 3. Fase 1 — Ingesta y perfilado (`ingestion/perfilado.py`)

**Entrada:** un CSV consolidado de los Excel mensuales del laboratorio, con
columnas de fecha, código y unidades. Las columnas se detectan por heurística
(`detectar_columnas`, línea 71) porque los exports no tienen nombres estables.

**Qué calcula.** Para cada producto se toma su serie histórica de stock `s` y se
calculan las diferencias día a día, `diffs = np.diff(s)`:

| Métrica | Cálculo | Significado |
|---|---|---|
| `frecuencia_movimiento` | `cambios / (len(s)-1)` | fracción de días con movimiento, ∈ [0,1] |
| `consumo_promedio` | media de `abs(diffs[diffs<0])` | cuánto sale por movimiento de salida |
| `consumo_minimo` / `consumo_maximo` | min/max de esas bajas | rango de la salida |
| `reposicion_promedio` | media de `diffs[diffs>0]` | tamaño típico de una entrada |
| `punto_reorden` | `consumo_promedio × 30` | referencia clásica de inventarios |

**Clasificación de rotación** (`clasificar`, línea 96) — regla de negocio, no
aprendida:

```
frecuencia == 0     → "Muerto"    (nunca se movió)
frecuencia < 0.05   → "Baja"
frecuencia < 0.20   → "Media"
frecuencia ≥ 0.20   → "Alta"
```

**Salidas:** `productos_perfilados.json` (todos) y `productos_muestra.json`
(100 por clase, muestreo con semilla fija → reproducible).

**Detalles que vale la pena mencionar en la defensa:**

- `normalizar_codigo` (línea 55): pandas lee códigos numéricos como `float64`,
  así que `str(codigo)` produce `"782123.0"`. Sin esta corrección, ningún cruce
  contra los códigos reales del sistema funcionaría.
- El muestreo usa semilla fija. Antes cambiaba en cada corrida y los resultados
  no eran reproducibles — requisito básico de un trabajo experimental.

---

## 4. Fase 2 — Simulación (`simulation/simulador.py`)

### ¿Por qué simular?

El histórico real tiene un problema estructural: **son fotos mensuales de stock,
no un registro diario de transacciones**. Con ~12 puntos por producto no se puede
construir un dataset supervisado con ventanas de 30 días. Se necesitan series
diarias.

La simulación **no inventa productos**: toma los perfiles estadísticos reales
(consumo medio, mínimo, máximo, frecuencia, clase) y genera 365 días de
movimientos consistentes con esas estadísticas. Es un *generador de datos
sintéticos parametrizado por la realidad*.

### El bucle de simulación

Por cada día y cada producto (`simular`, línea 116):

```python
# 1. Llegan las órdenes de restock cuya fecha_llegada ya pasó
# 2. Con probabilidad = frecuencia_movimiento, hay consumo:
#       consumo ~ Uniforme(consumo_minimo, consumo_maximo)
#       stock = max(0, stock - consumo)
# 3. Si stock <= 0 y no hay pedido pendiente:
#       se emite orden que llega en lead_time (30) días   ← POLÍTICA REACTIVA
# 4. Se guarda el snapshot (fecha, codigo, stock)
```

**Esquema SQLite** (constante `DDL`, línea 39): `productos`, `inventario`
(PK compuesta `codigo, fecha`), `ordenes_restock`, `movimientos`.

**El paso 3 es la política actual del laboratorio**, codificada explícitamente.
Es el punto de comparación del experimento de la [§9](#9-el-experimento-contrafactual-la-prueba-de-que-sirve).

**Semilla como parámetro, no constante.** Con semilla fija en config, cada
corrida producía datos idénticos, así que una supuesta "validación externa"
evaluaba sobre los mismos datos de entrenamiento. Con `--semilla 99` se genera
un conjunto de validación genuinamente distinto.

---

## 5. Fase 3 — Construcción del dataset (`features/dataset.py`)

Este es **el archivo más importante del proyecto**. Define el contrato de
features y, sobre todo, la etiqueta.

### 5.1 Las 7 features

```python
COLUMNAS_NUMERICAS = [
    "stock_actual",           # unidades hoy
    "consumo_promedio",       # unidades por movimiento de salida
    "consumo_minimo",
    "consumo_maximo",
    "reposicion_promedio",    # tamaño típico de reposición
    "frecuencia_movimiento",  # fracción de días con movimiento
]
COLUMNA_CATEGORICA = "clase"  # Muerto / Baja / Media / Alta
```

El **orden es parte del contrato**. Reordenar sin reentrenar rompe la inferencia
silenciosamente: el pipeline recibiría `consumo_promedio` donde espera
`stock_actual` y seguiría devolviendo números, solo que equivocados.

### 5.2 Codificación de `clase` — un bug de libro, corregido

El código anterior usaba:

```python
df["clase"].astype("category").cat.codes    # ← MAL
```

Eso asigna códigos **según los valores presentes en cada lote**. Si un lote trae
`["Alta", "Baja"]` → Alta=0, Baja=1. Si el siguiente trae `["Baja", "Media"]` →
Baja=0, Media=1. **La misma clase recibe números distintos en cada llamada.** El
modelo predice sobre un espacio de features que cambia en cada petición.

La corrección: `OrdinalEncoder` con categorías fijas y explícitas, dentro del
Pipeline (`train.py:88`):

```python
CLASES = ["Muerto", "Baja", "Media", "Alta"]   # orden por nivel de actividad
OrdinalEncoder(categories=[CLASES],
               handle_unknown="use_encoded_value", unknown_value=-1)
```

El orden es **ordinal semántico** (nivel de rotación creciente), no alfabético.
`handle_unknown` evita que una clase nueva en producción tumbe la inferencia.

Hay un test que fija esto: `test_encoding_clase_no_depende_del_lote`.

### 5.3 La etiqueta — la decisión conceptual central

```python
agotado_30d = 1   ⟺   min( stock[t], stock[t+1], ..., stock[t+30] ) ≤ 0
```

**Por qué el mínimo de la ventana y no `stock[t+30] ≤ 0`.**

La versión ingenua mira una sola foto al final del horizonte. Pero en el
simulador el pedido llega exactamente a los 30 días. Resultado: un producto que
pasó 29 días en cero quedaba etiquetado como **"no agotado"** solo porque el día
30 ya había llegado mercancía.

El modelo aprendía literalmente que *estar en cero no es un problema*, y
asignaba riesgo **BAJO** a productos ya agotados. La etiqueta estaba
contaminada por la política de reposición.

Con el mínimo de la ventana, cualquier día en cero dentro del horizonte marca el
caso, y la pregunta que responde el modelo pasa a ser la útil:
**"¿me quedaré sin producto en los próximos 30 días?"**

**Implementación** (`_stock_minimo_futuro`, línea 79). `rolling()` mira hacia
atrás, no hacia adelante. El truco es invertir la serie, aplicar el rolling y
devolverla al orden original:

```python
invertida = stock[::-1]
invertida.rolling(horizonte + 1, min_periods=horizonte + 1).min()[::-1]
```

`min_periods = ventana` fuerza `NaN` en los últimos 30 días de cada producto:
son filas donde el futuro no se conoce completo, y se descartan
(`dropna`, línea 138). **Etiquetar con información incompleta sería fuga de
datos.**

### 5.4 Validaciones defensivas

- Snapshots duplicados `(codigo, fecha)` → `ContratoFeaturesError`.
- `merge(..., validate="many_to_one")` → falla si un código está duplicado en
  `productos`.
- Filas de inventario sin producto asociado → error explícito, no `NaN` silencioso.

**Tamaño resultante:** 107.200 filas de entrenamiento + 26.800 de prueba.

---

## 6. Fase 4 — Entrenamiento (`training/train.py`)

### 6.1 El algoritmo: Random Forest

```python
RandomForestClassifier(
    n_estimators=200,       # 200 árboles
    max_depth=12,           # profundidad máxima
    class_weight=None,      # opcional: "balanced" con --balancear
    n_jobs=-1,              # todos los núcleos
    random_state=42,        # reproducible
)
```

**Cómo funciona, en tres párrafos** (esto es lo que hay que saber explicar):

**Un árbol de decisión** parte los datos con preguntas de umbral sobre una
feature: *¿`stock_actual` ≤ 8?* → sí por un lado, no por el otro. En cada nodo
elige la pregunta que mejor separa las dos clases, medida con el **índice Gini**:

$$\text{Gini} = 1 - \sum_k p_k^2$$

donde $p_k$ es la proporción de la clase $k$ en el nodo. Gini = 0 significa nodo
puro (todos de la misma clase). El árbol crece recursivamente hasta
`max_depth=12` o hasta que los nodos son puros. Al final, cada hoja contiene una
proporción de casos positivos → esa es su probabilidad.

**Un solo árbol sobreajusta**: memoriza el ruido del entrenamiento. El
**bosque** ataca eso con dos fuentes de aleatoriedad:

1. **Bagging** — cada árbol se entrena sobre una muestra bootstrap (con
   reemplazo) del dataset, así que ninguno ve exactamente los mismos datos.
2. **Subespacio aleatorio** — en cada nodo se considera solo un subconjunto
   aleatorio de features (por defecto √7 ≈ 2 de las 7), lo que descorrelaciona
   los árboles entre sí.

La predicción final es el **promedio de las 200 probabilidades**. Promediar
estimadores con sesgo bajo y varianza alta reduce la varianza sin aumentar el
sesgo — es el argumento clásico a favor de los métodos de ensamble.

**Por qué Random Forest y no otra cosa** (respuesta preparada):

- Son **400 productos con 7 features tabulares**. En datos tabulares de este
  tamaño, los ensambles de árboles igualan o superan a las redes neuronales, y
  la literatura lo respalda de forma consistente
  (Grinsztajn et al., *"Why do tree-based models still outperform deep learning
  on tabular data?"*, NeurIPS 2022).
- **Cero preprocesamiento numérico**: los árboles parten por umbrales, así que
  no hay que escalar ni normalizar. Una red neuronal sin `StandardScaler`
  simplemente no converge bien.
- **Interpretabilidad**: `feature_importances_` da una explicación directa de
  por qué un producto es de riesgo alto. En un proyecto donde una persona debe
  confiar en la sugerencia para gastar dinero, eso no es un lujo.
- **Robustez a outliers y a features en escalas dispares** (`stock_actual` en
  cientos, `frecuencia_movimiento` en [0,1]).
- **Entrena en segundos** en un portátil, sin GPU.

### 6.2 El artefacto es un Pipeline completo

```python
Pipeline([
    ("preproceso", ColumnTransformer([...OrdinalEncoder sobre 'clase'...],
                                     remainder="passthrough")),
    ("modelo",     RandomForestClassifier(...)),
])
```

Se serializa **encoding + modelo juntos** con `joblib`. Motivo: si el encoding
viviera fuera, la inferencia tendría que reimplementarlo, y cualquier
divergencia entre entrenamiento e inferencia (*training/serving skew*) sería
silenciosa. Con el Pipeline eso es imposible por construcción.

### 6.3 Split temporal, no aleatorio

```python
def split_temporal(dataset, test_size=0.2):
    fechas = dataset["fecha"].sort_values().unique()
    corte = fechas[int(len(fechas) * (1 - test_size))]
    train = dataset[dataset["fecha"] <  corte]    # pasado
    test  = dataset[dataset["fecha"] >= corte]    # futuro
```

**Este es un punto de defensa fuerte.** Un `train_test_split` aleatorio sobre
series temporales mezcla días del futuro en el entrenamiento. Como los
snapshots de un mismo producto en días consecutivos son casi idénticos, el
modelo prácticamente **memoriza** el conjunto de prueba y las métricas se
inflan de forma irreal. El split por fecha reproduce la situación real:
entrenar con lo que ya pasó, evaluar sobre lo que aún no había ocurrido.

Corte del modelo actual: **2026-09-26**.

### 6.4 No se asume la clase positiva

```python
clases = list(pipeline.classes_)
indice_positiva = clases.index(1)
proba = pipeline.predict_proba(X_test)[:, indice_positiva]
```

`predict_proba(X)[:, 1]` es un idiom tan común como frágil: el orden de
`classes_` depende de los valores presentes al entrenar. Si el índice se
invierte, el sistema reporta probabilidades **exactamente al revés** sin lanzar
ningún error. Hay un test específico para esto
(`test_clase_positiva_no_se_asume`).

### 6.5 Metadata junto al artefacto

Se escribe `stockout_simulated_v1.metadata.json` con: versión, algoritmo,
horizonte, definición del target, features y su orden, corte temporal, semilla,
métricas, y dos campos que **viajan hasta la interfaz en cada respuesta HTTP**:

```json
"origen_datos": "SIMULADO",
"estado_validacion": "NO_VALIDADO_CON_DATOS_REALES"
```

Un modelo sin trazabilidad de con qué se entrenó no es auditable. Que la
advertencia esté en el contrato de la API y no en un pie de página de la
documentación es una decisión deliberada: es imposible usar el sistema sin verla.

### 6.6 Métricas de entrenamiento (holdout temporal)

| Métrica | Valor |
|---|---|
| Accuracy | 0,955 |
| ROC-AUC | 0,988 |
| Filas de prueba | 26.800 |
| Positivos reales en prueba | 8.510 (31,8 %) |

**No presentes solo esto.** Ver la sección siguiente: es la que un jurado
exigente va a pedir.

---

## 7. Fase 5 — Evaluación honesta (`training/evaluar.py`)

Módulo aparte, con una tesis explícita: **accuracy no sirve aquí**, y un modelo
que no le gana a una regla trivial es un modelo que sobra.

### 7.1 El baseline: una división

```python
dias_cobertura = stock_actual / consumo_promedio
# si dias_cobertura < horizonte → se agota
```

Esa es la regla de inventarios de toda la vida. **Si el Random Forest no le gana
de forma clara, el proyecto no se justifica.** Comparar contra un baseline
trivial es lo que separa un experimento de una demostración.

### 7.2 Las métricas que sí importan

| Métrica | Por qué |
|---|---|
| **Precision / Recall** sobre la clase positiva | con 68 % de negativos, "nunca se agota" ya da 68 % de accuracy |
| **PR-AUC** | con clases desbalanceadas, ROC-AUC es optimista; PR-AUC no |
| **Brier score** | mide calibración: error cuadrático medio de la probabilidad |
| **Tabla de calibración** | cuando dice 80 %, ¿se agota el 80 % de las veces? |

La calibración importa porque **la salida se usa como umbral de decisión**
(pedir si P ≥ 0,8). Una probabilidad descalibrada convierte ese umbral en un
número arbitrario.

### 7.3 Cómo ejecutarlo

```powershell
python -m inventory_ml.training.evaluar
```

Imprime la tabla comparativa modelo vs. baseline, la calibración por tramos, y
la conclusión explícita:

```
PR-AUC: el modelo supera al baseline por +X.XXXX
```

Y si la ventaja es ≤ 0,02, lo dice sin adornos:
*"La ventaja es marginal: la regla trivial ya resuelve el problema."*

> **Ejecuta esto antes de la sustentación** y lleva la salida. Es la evidencia
> que convierte "entrené un modelo" en "demostré que el modelo aporta".

---

## 8. Inferencia y niveles de riesgo

### 8.1 `inference/predictor.py`

Punto de entrada **único** para predecir. La API no hace `joblib.load` ni
feature engineering: solo valida JSON → llama al Predictor → serializa.

- `Predictor.cargar()` — valida que el artefacto exista, sea cargable, tenga
  `predict_proba` y exponga `classes_`. Cada fallo lanza `ModeloNoDisponibleError`
  con un mensaje distinto.
- `predict_batch()` — **vectorizado**: N registros → 1 sola llamada al Pipeline.
  Con 400 productos, la diferencia contra un bucle es de dos órdenes de magnitud.
- `predict()` — un producto; reutiliza exactamente `predict_batch([registro])[0]`,
  así que individual y lote **no pueden divergir**. Hay un test que lo verifica
  (`test_batch_coincide_con_individual`).
- `get_model_info()` — solo campos publicables, sin rutas del sistema de archivos.

### 8.2 Umbrales de riesgo (`config.py:56`)

```python
P > 0.70            → ALTO
0.40 ≤ P ≤ 0.70     → MEDIO
P < 0.40            → BAJO
```

Una única función, `nivel_riesgo()`, es la autorizada a aplicarlos en todo el
proyecto. Están parametrizados por variable de entorno
(`UMBRAL_RIESGO_ALTO`, `UMBRAL_RIESGO_MEDIO`).

> **Sé honesto si te preguntan:** estos cortes son **convención de negocio**, no
> optimizados sobre una curva precision-recall ni sobre un costo esperado. La
> forma correcta de fijarlos sería con una matriz de costos (costo de quiebre vs.
> costo de capital inmovilizado). Está en las limitaciones.

Reparto actual sobre los productos activos: **54 ALTO / 7 MEDIO / 261 BAJO**.

---

## 9. El experimento contrafactual (la prueba de que sirve)

`simulation/experimento.py`. **Si tienes que defender una sola cosa, defiende
esta.** Una métrica de clasificación dice que el modelo acierta; este
experimento dice que **usarlo cambia el resultado del negocio**.

### 9.1 Diseño

Se comparan dos políticas de reposición sobre **exactamente la misma demanda**:

| Política | Regla |
|---|---|
| **Reactiva** (actual) | pedir cuando `stock ≤ 0` |
| **Predictiva** (modelo) | pedir cuando `P(agotamiento) ≥ 0,8`, **manteniendo la reactiva como red de seguridad** |

**El control experimental.** La demanda diaria se genera **una sola vez** y se
congela (`generar_demanda`, línea 60). Ambos brazos enfrentan la misma secuencia,
incluida la demanda que la política reactiva no puede atender por estar en cero.

Sin eso, cada brazo vería un flujo aleatorio distinto y **la comparación no
significaría nada**. Es el equivalente a un ensayo pareado: se aísla el efecto
de la política eliminando el azar como variable.

### 9.2 La red de seguridad

Sin ella, la política predictiva **abandona** los productos que el modelo no
marca: nunca llegan al umbral, nunca se piden, y el resultado degenera. Con red
de seguridad, la política predictiva es estrictamente *"lo mismo que hoy, más
anticipación"*. La bandera `--sin-red` reproduce el comportamiento degenerado
si quieren verlo.

### 9.3 Resultados (365 días, 400 productos, lead time 30 días)

| | Reactiva | Predictiva @ 0,8 |
|---|---|---|
| Días-producto agotado (con demanda) | 25.273 | **14.473** |
| **Unidades no servidas** | 83.716 | **48.014** |
| **Fill rate** | 45,3 % | **68,6 %** |
| Pedidos emitidos | 980 | 1.347 |
| Stock promedio | 19,2 | 26,4 |
| **Mejora en servicio** | — | **+42,6 %** |

**Cómo leer esto — y no lo vendas de más:**

- La métrica que decide es **`unidades_no_servidas`**: demanda real que no se
  pudo atender. Baja un 42,6 %.
- **Ese resultado no es gratis.** Se emiten 367 pedidos más (+37 %) y el capital
  inmovilizado sube 38 % (stock promedio de 19,2 a 26,4). Es el compromiso
  clásico servicio ↔ inventario, y el proyecto lo cuantifica en vez de
  esconderlo.
- Un fill rate del 45 % en la política reactiva es malísimo, y es **exactamente
  el punto**: con lead time de 30 días, pedir cuando ya llegaste a cero garantiza
  un mes sin producto. El sistema no arregla un proceso bueno; arregla uno
  estructuralmente roto.
- `dias_agotado_utiles` cuenta solo productos **con demanda**: un producto
  "Muerto" en cero no es un problema, nadie lo consume.

El resultado se precalcula (tarda ~11 s) y se sirve desde JSON: demasiado lento
para una petición HTTP y no cambia entre visitas.

```powershell
python -m inventory_ml.simulation.experimento --umbral 0.5 --umbral 0.8 --umbral 0.9
```

> Corre esto con varios umbrales y lleva la tabla. Muestra la **curva de
> compromiso** completa, no un solo punto — es una respuesta mucho más sólida a
> "¿por qué 0,8?".

---

## 10. La API (FastAPI)

### 10.1 Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/health` | sonda; 200 si el modelo está cargado, 503 si no |
| `GET` | `/api/v1/model/info` | metadata del modelo activo |
| `POST` | `/api/v1/predict` | predice un producto enviado por el cliente |
| `POST` | `/api/v1/predict/batch` | hasta 500 productos, una pasada vectorizada |
| `GET` | `/api/v1/inventario/fechas` | ventana temporal disponible |
| `GET` | `/api/v1/inventario` | estado en una fecha + predicción, paginado |
| `GET` | `/api/v1/experimento` | comparación de políticas precalculada |
| `POST` | `/api/v1/asistente` | pregunta en lenguaje natural |

Documentación interactiva en `http://127.0.0.1:8000/docs`.

### 10.2 Decisiones de diseño defendibles

**Carga única en el `lifespan`** (`main.py:41`). El modelo se carga **una vez al
arrancar**, no por petición. Cargar un joblib de 200 árboles en cada request
sería absurdo. Y si el artefacto falta, **el arranque no aborta**: la app queda
degradada y lo reporta en `/health`, para que un readiness probe lo detecte.

**Ruta versionada `/api/v1`.** El consumidor es Spring Boot; un cambio de
contrato futuro debe poder convivir con el actual. `/health` queda fuera porque
es infraestructura, no negocio.

**Los errores nunca filtran stack traces** (`main.py:83-116`). Tres handlers:
`ContratoFeaturesError` → 422, `ModeloNoDisponibleError` → 503, `Exception` →
500 genérico. El detalle técnico va al log; al cliente solo un mensaje.
Hay un test: `test_error_de_inferencia_no_filtra_stacktrace`.

**Sin CORS, a propósito.** Spring Boot consume la API servidor a servidor, donde
CORS no aplica. Habilitarlo sería abrir una superficie que nadie necesita.

**`InventarioItem` NO expone `agotado_30d`** (`schemas.py`, comentario de clase).
Esa es la **etiqueta real**, y solo se conoce 30 días después. Mostrarla en una
vista del día actual sería mostrar el futuro. Hay un test:
`test_no_expone_la_etiqueta_real`.

**Validación en el borde con Pydantic**: `frecuencia_movimiento` ∈ [0,1], stocks
≥ 0, `clase` restringida a un `Literal` de las cuatro válidas, batch entre 1 y
500. Entrada inválida → 422 antes de tocar el modelo.

---

## 11. El agente (`api/asistente.py` + `herramientas.py` + `resumen.py`)

### 11.1 Qué es: un agente con herramientas

```
pregunta del usuario
      + resumen curado del inventario (contexto base)
      + system prompt con reglas
            ↓
   ┌──▶ el modelo decide: ¿respondo, o me falta algo?
   │         ↓ me falta
   │    emite tool_calls  →  se ejecuta la función en Python
   │         ↓                        ↓
   └──── ve el resultado ◀────  vuelve como mensaje "tool"
             ↓ ya puedo responder
        respuesta en texto
```

Eso es el ciclo **razonamiento → acción → observación** que define a un agente:
el modelo no recibe todo masticado, **decide qué le falta, lo pide, y usa el
resultado**. El bucle está en `asistente.py:preguntar`, con tope de
`MAX_ITERACIONES = 5` vueltas.

**Las tres herramientas** (`herramientas.py`):

| Herramienta | Qué hace | Envuelve |
|---|---|---|
| `consultar_producto(codigo)` | busca un producto por código (parcial) y lo puntúa | `repository.estado_en_fecha` |
| `simular_escenario(codigo, niveles_stock[])` | **contrafactual**: recalcula la probabilidad para varios niveles de stock hipotéticos de una vez | `Predictor.predict_batch` |
| `comparar_politicas()` | cifras del experimento reactiva vs. predictiva | el JSON precalculado |

Ninguna inventa lógica de negocio: son fachadas sobre código que ya existía.
Lo nuevo es que **el modelo decide cuándo llamarlas**.

**Por qué se sigue inyectando el resumen** además de dar herramientas: las
preguntas frecuentes ("¿qué priorizo?") se responden en **una sola vuelta**, sin
gastar iteraciones ni latencia. Las herramientas cubren lo que el resumen no
puede anticipar. Es la diferencia entre un agente ágil y uno que consulta la
base de datos para todo.

**Trazabilidad.** La respuesta incluye `herramientas_usadas`, y la interfaz las
pinta como etiquetas debajo de cada respuesta. Es la **evidencia visible** de
que hay un agente y no un chat: el jurado ve qué consultó por su cuenta.

### 11.1.1 Decisiones del bucle que vale la pena defender

Las tres salieron de probar contra el proveedor real, no de teoría:

**Las herramientas viajan también en la vuelta final.** Al agotar las
iteraciones se fuerza una última llamada para que concluya. La versión ingenua
era omitir `tools`, pero eso equivale a `tool_choice: "none"` y el proveedor
responde **400 — "Tool choice is none, but model called a tool"** si el modelo
insiste. La solución es instruirlo *por mensaje* ("ya no puedes usar más
herramientas, responde con lo que tienes"), no quitarle las herramientas.

**`simular_escenario` acepta varios niveles por llamada.** Con un nivel por
llamada, la pregunta natural —"¿cuánto stock necesita para dejar de ser riesgo
alto?"— es un tanteo, y el agente gastaba **las 5 vueltas probando 1, 2, 5 y
10 unidades** sin llegar a responder. Barriendo un rango de una vez, la misma
pregunta se resuelve en **2 llamadas y la mitad de tokens**, y además todos los
escenarios se resuelven en una sola pasada vectorizada del Pipeline.

**El system prompt le dice cuáles son los umbrales de riesgo.** Sin eso el
modelo tanteaba a ciegas — literalmente respondía "no conozco el umbral que
define cada nivel". Los valores se interpolan desde `config`, así que si los
umbrales cambian, el agente se entera.

**Toda herramienta devuelve `{"error": ...}` en vez de lanzar.** Una excepción
aborta la conversación entera; un error como texto el modelo lo lee, lo entiende
y lo explica o reintenta con otros argumentos. Hay un test que lo fija con una
herramienta inventada (`test_herramienta_inexistente_no_rompe_la_conversacion`).

### 11.2 El resumen curado (`resumen.py`)

**No se le manda el CSV completo al modelo.** 400 filas crudas son caras, lentas
y producen peores respuestas. Se destila:

- fecha, total de productos, cuántos tienen demanda histórica,
- cuántos están **sin stock y con demanda** (los que importan),
- distribución por nivel de riesgo y por clase de rotación,
- **top 15 de mayor probabilidad, filtrando los productos sin consumo**,
- versión, origen y estado de validación del modelo.

Se serializa en **texto plano tabular**, no JSON: menos tokens que las llaves y
comillas, misma información.

El filtro `consumo > 0` es una regla de negocio real: un producto "Muerto" en
stock cero tiene probabilidad de agotamiento altísima **y es completamente
irrelevante** — nadie lo consume. Sin ese filtro, el top 15 se llenaría de ruido.
Hay un test: `test_resumen_excluye_productos_sin_demanda_de_los_criticos`.

### 11.3 El system prompt

Siete reglas explícitas, y las dos primeras son las que importan para la
sustentación:

1. El modelo predictivo es **SIMULADO y no validado**; las probabilidades son
   orientativas, no hechos.
2. **El agente no decide.** Nunca dice "compra X"; dice "X aparece como
   prioridad porque...". La persona decide.

Las otras cinco: no inventar cifras fuera del resumen ni de las herramientas, no
priorizar productos muertos, cuándo usar cada herramienta, **cuáles son los
umbrales de riesgo** (interpolados desde `config`, para que el agente sepa a qué
cifra apuntar), y ser breve en español.

> Esto es defendible como diseño responsable: un LLM que decide compras sobre un
> modelo no validado sería negligente. El sistema está construido para **asistir
> el juicio humano**, no para reemplazarlo.

### 11.5 Límite del proveedor — léelo antes de la demo

El `.env` apunta a **Groq** con `openai/gpt-oss-120b`. El tier gratuito tiene un
límite de **8.000 tokens por minuto**, y un agente consume bastante más que un
chat: el historial completo se reenvía en cada vuelta, así que una pregunta con
dos herramientas gasta ~4.000 tokens.

**En la práctica: dos o tres preguntas por minuto.** Si te pasas, el proveedor
responde 429, la API lo traduce a un 503 limpio y la interfaz dice que el
asistente no está disponible — no se rompe nada, pero queda feo en vivo.

Mitigaciones ya aplicadas en `config.py`: `LLM_MAX_TOKENS = 1200` (Groq cuenta
`prompt + max_tokens` contra el límite, así que un techo alto provoca 429 antes
de generar nada) y `LLM_TOP_RIESGO = 10` (cada fila del resumen se paga en cada
vuelta). Para la sustentación: **espacia las preguntas** o sube de tier.

### 11.4 Seguridad de la clave

La `LLM_API_KEY` se lee de entorno (`.env`), vive **solo en el proceso de
Python**, viaja en la cabecera `Authorization` y **nunca** aparece en el cuerpo,
en la respuesta, en los logs ni en el navegador. Spring Boot hace de proxy y
tampoco la conoce. Sin clave configurada → 503 limpio.

Hay cuatro tests solo sobre esto: `test_la_clave_va_en_la_cabecera_y_no_en_el_cuerpo`,
`test_la_clave_nunca_llega_al_cliente`, `test_error_del_proveedor_no_filtra_detalles`,
`test_sin_api_key_devuelve_503`.

Todos los fallos del proveedor (HTTP, red, respuesta malformada) se capturan y
se traducen a un 503 genérico: el cuerpo de error de un proveedor de LLM puede
traer detalles de la cuenta, y eso va al log, nunca al cliente.

---

## 12. La capa Spring Boot

`PredictionClient.java` es el **único punto de contacto** con la API de Python.

- **Timeouts explícitos**: 3 s de conexión, 45 s de lectura (el asistente tarda
  más). Sin timeouts, una FastAPI caída deja hilos de Tomcat colgados hasta
  agotar el pool.
- **Captura `Exception`, no solo `RestClientException`**: en Jackson 3 los
  errores de deserialización son *unchecked* y se escapaban del catch anterior
  sin dejar rastro.
- **Degradación elegante**: todo devuelve `Optional`; el controlador traduce
  vacío a 503. Si Python está caído, la interfaz lo dice en vez de reventar.
- **`/health` con 503 no es excepción**: es una respuesta válida que significa
  "degradado", y se maneja con `onStatus(...)` en vez de dejarla lanzar.

`InventarioController` es un proxy: el navegador nunca habla con FastAPI
directamente, así que Python puede vivir en la red interna y la sesión de Spring
Security sigue protegiendo el acceso.

---

## 13. Pruebas

56 tests en 5 archivos. Lo relevante no es el número, sino **qué fijan**:

| Archivo | Qué protege |
|---|---|
| `test_contrato_modelo.py` | la clase positiva no se asume; el encoding de `clase` no depende del lote; el target se construye al horizonte correcto |
| `test_api.py` | contrato HTTP, validación, batch, y que los errores no filtren stack traces |
| `test_api_inventario.py` | paginación, filtros, y que **no se exponga la etiqueta real** |
| `test_api_asistente.py` | que la API key nunca salga del proceso; manejo de fallos del LLM; **el bucle del agente**: que ejecute la herramienta y le devuelva el resultado, que el contrafactual sea monótono, que una herramienta inventada no rompa la conversación, y que el bucle siempre termine |
| `test_api_integracion.py` | **coherencia del comportamiento**: stock cero es riesgo máximo, y el riesgo decrece cuando sube el stock |

Los dos últimos de `test_api_integracion.py` son los interesantes: no comprueban
un valor exacto, comprueban que **el modelo se comporta como debe** — más stock,
menos riesgo. Un modelo que rompa esa monotonía está mal aunque su accuracy sea
alta.

```powershell
pytest -q
```

---

## 14. Limitaciones (dilas tú antes de que las digan ellos)

1. **El modelo está entrenado con datos simulados.** El perfilado viene de datos
   reales, pero las series diarias son sintéticas. **Nunca ha visto un solo día
   real de operación.** El sistema lo declara en cada respuesta HTTP
   (`origen_datos: SIMULADO`, `estado_validacion: NO_VALIDADO_CON_DATOS_REALES`).

2. **Riesgo de circularidad.** El modelo aprende de un simulador cuyas reglas
   también las escribimos nosotros. Que acierte con ROC-AUC 0,988 demuestra que
   aprendió **la dinámica del simulador**, no necesariamente la del laboratorio.
   Validar con historia real es el trabajo pendiente número uno.

3. **Los umbrales de riesgo son convención**, no optimización sobre una matriz
   de costos (quiebre vs. capital inmovilizado). Ver [§8.2](#82-umbrales-de-riesgo-configpy56).

4. **El lead time es una constante de 30 días** para todos los productos. En la
   realidad varía por proveedor y por temporada.

5. **La demanda simulada es uniforme e independiente**: sin estacionalidad, sin
   tendencia, sin correlación entre productos. La realidad tiene las tres.

6. **No hay reentrenamiento automático ni monitoreo de deriva.** Un modelo en
   producción se degrada; aquí no hay nada que lo detecte.

7. **El agente no recuerda conversaciones anteriores**: cada pregunta arranca
   de cero. El bucle de herramientas vive dentro de una sola petición.

8. **SQLite**, adecuado para la demostración, no para concurrencia real. El
   módulo `repository.py` está aislado precisamente para que migrar a PostgreSQL
   no toque el contrato HTTP.

---

## 15. Preguntas que te van a hacer, y cómo responderlas

**"¿Esto usa redes neuronales?"**
> No. Usa Random Forest, un ensamble de 200 árboles de decisión. Lo elegí porque
> con 400 productos y 7 features tabulares los métodos de árboles rinden igual o
> mejor que el aprendizaje profundo — está documentado en la literatura, por
> ejemplo Grinsztajn et al. en NeurIPS 2022 — y además dan interpretabilidad:
> puedo mostrar por qué un producto es de riesgo alto. En un sistema que sugiere
> gastar dinero, eso importa. Si el requisito formal exige una red, la
> arquitectura lo permite: el Pipeline aísla el estimador y cambiarlo por un
> `MLPClassifier` es una línea más un `StandardScaler`.

**"¿Qué es exactamente el agente de IA?"**
> Es un agente con herramientas. Recibe un resumen del inventario, y si no le
> alcanza, decide por su cuenta qué consultar: puede buscar un producto en la
> base de datos, simular escenarios de stock hipotéticos contra el modelo
> predictivo, o leer las cifras del experimento de políticas. Ejecuta esas
> llamadas, ve el resultado y razona sobre él, hasta cinco vueltas. La respuesta
> devuelve qué herramientas usó, y la interfaz las muestra, así que es
> verificable. Lo que deliberadamente **no** hace es decidir: el system prompt le
> prohíbe recomendar compras, porque el modelo predictivo aún no está validado
> con datos reales. Asiste el juicio de la persona, no lo reemplaza.

**"Demuéstrame que el agente no es un chat con el contexto pegado."**
> Pregúntale por un producto que no está en el resumen, o algo hipotético: "¿cuánto
> stock necesita el 611270 para dejar de ser riesgo alto?". El resumen solo trae
> el top 10 y el stock real, así que esa respuesta no existe en el contexto. El
> agente consulta el producto, barre varios niveles de stock contra el modelo, y
> arma la tabla. Debajo de la respuesta aparecen las etiquetas de las
> herramientas que invocó.

**"¿Por qué simulaste los datos? ¿No es hacer trampa?"**
> El histórico real son fotos mensuales de stock, no transacciones diarias. Con
> doce puntos por producto no se puede construir un dataset con ventanas de 30
> días. La simulación no inventa productos: toma los perfiles estadísticos reales
> — consumo medio, mínimo, máximo, frecuencia de movimiento, clase de rotación —
> y genera series diarias consistentes con ellos. Y el sistema declara ese origen
> en cada respuesta de la API, precisamente para que nadie lo confunda con un
> modelo productivo.

**"¿Cómo sé que el modelo sirve y no es solo accuracy alta?"**
> Por dos vías. Primera: el módulo `evaluar.py` lo compara contra un baseline
> trivial — stock dividido por consumo promedio — con PR-AUC, que es la métrica
> correcta con clases desbalanceadas, más una tabla de calibración. Segunda, y
> más importante: el experimento contrafactual. Comparo la política actual contra
> la política con modelo sobre exactamente la misma demanda congelada, y las
> unidades de demanda no atendida bajan 42,6 %. Eso mide impacto en el negocio,
> no solo acierto estadístico.

**"¿Por qué el umbral 0,8?"**
> Es un parámetro, no una constante: `--umbral` acepta varios valores y el
> experimento genera la curva completa. Con 0,8 la mejora en servicio es 42,6 %
> con un aumento de 38 % en capital inmovilizado. La forma rigurosa de fijarlo
> sería con una matriz de costos reales de quiebre versus costo de capital, y eso
> está declarado en las limitaciones.

**"¿Qué pasa si el modelo se cae?"**
> La API arranca igual, en modo degradado, y lo reporta en `/health` con un 503
> para que un readiness probe lo detecte. Spring Boot lo maneja con `Optional` y
> la interfaz muestra el estado en vez de romperse. Ningún error filtra stack
> traces al cliente.

**"¿Cuál fue el error técnico más grave que encontraste?"**
> La definición de la etiqueta. La versión original miraba el stock una sola vez,
> a los 30 días exactos. Pero en el simulador el pedido llega justo a los 30 días,
> así que un producto que pasaba 29 días en cero quedaba etiquetado como "no
> agotado". El modelo aprendía que estar en cero no era un problema y asignaba
> riesgo BAJO a productos ya agotados. Lo corregí usando el mínimo del stock en
> toda la ventana, y la pregunta que responde el modelo pasó a ser la correcta.
> El segundo fue el encoding de la clase con `.cat.codes`, que asignaba códigos
> distintos según qué valores traía cada lote.

**"¿Está listo para producción?"**
> No, y el sistema lo dice de forma explícita en cada respuesta HTTP. Falta lo
> principal: validar con historia real del laboratorio. Después de eso, calibrar
> los umbrales con costos reales, lead times por proveedor, y monitoreo de deriva
> del modelo.

---

## 16. Si el requisito exige red neuronal

El agente ya está implementado ([§11](#11-el-agente-apiasistentepy--herramientaspy--resumenpy)).
Queda la red neuronal, y es un cambio pequeño porque la arquitectura la aísla.

El Pipeline separa preprocesamiento de estimador, así que solo cambia el segundo
paso (`training/train.py:construir_pipeline`). Una red neuronal **sí** necesita
escalado, a diferencia de los árboles:

```python
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

# ColumnTransformer: OrdinalEncoder sobre 'clase' + StandardScaler sobre las numéricas
modelo = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42)
```

Todo lo demás — dataset, split temporal, evaluación, API, tests — funciona sin
tocarse: el `Predictor` solo exige `predict_proba` y `classes_`, y la metadata
lee el nombre del algoritmo por reflexión.

Lo honesto sería **entrenar las dos y comparar** con `evaluar.py`: eso convierte
el requisito en un resultado experimental, y es mejor sustentación que usar una
red porque sí.

---

## 17. Índice de archivos

| Archivo | Responsabilidad |
|---|---|
| `config.py` | única fuente de rutas, horizonte, umbrales y configuración del LLM |
| `ingestion/perfilado.py` | CSV real → perfil estadístico por producto |
| `ingestion/main.py` | script original, **legado**; lo reemplaza `perfilado.py` |
| `simulation/simulador.py` | perfiles → 365 días de movimientos en SQLite |
| `simulation/experimento.py` | experimento contrafactual reactiva vs. predictiva |
| `features/dataset.py` | contrato de features + construcción de la etiqueta |
| `training/train.py` | entrena el Pipeline, split temporal, escribe metadata |
| `training/evaluar.py` | evaluación honesta contra baseline trivial |
| `inference/predictor.py` | carga del artefacto y predicción vectorizada |
| `repository.py` | acceso de solo lectura al inventario (aislado para migrar a PostgreSQL) |
| `resumen.py` | destila el inventario a un contexto compacto para el LLM |
| `reporting/riesgo.py` | CSV estáticos de riesgo, **legado**; borrable cuando Java use la API |
| `api/main.py` | app FastAPI, lifespan, manejo de errores, `/predict` |
| `api/dependencies.py` | inyección del Predictor sin estado global |
| `api/schemas.py` | contrato HTTP (Pydantic) |
| `api/inventario.py` | estado del inventario + predicción |
| `api/experimento.py` | sirve el experimento precalculado |
| `api/asistente.py` | bucle del agente: LLM + herramientas + resumen inyectado |
| `herramientas.py` | las 3 herramientas que el agente puede invocar |
| `PredictionClient.java` | único punto de contacto de Spring con FastAPI |
| `InventarioController.java` | proxy HTTP para el navegador |

---

## 18. Orden de ejecución completo

```powershell
cd backend_python

python -m inventory_ml.ingestion.perfilado      # CSV real → perfiles
python -m inventory_ml.simulation.simulador     # perfiles → inventario.db
python -m inventory_ml.training.train           # → modelo.joblib + metadata
python -m inventory_ml.training.evaluar         # ← LLEVA ESTA SALIDA
python -m inventory_ml.simulation.experimento --umbral 0.5 --umbral 0.8 --umbral 0.9
python -m inventory_ml.reporting.riesgo         # CSV de riesgo (legado)

pytest -q                                       # 45 tests
uvicorn inventory_ml.api.main:app --reload      # API en :8000, docs en /docs
```

Luego, en otra terminal, la interfaz Spring Boot en `:8080`.
