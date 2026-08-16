# Predicción de agotamiento de inventario

Pipeline de machine learning que estima la probabilidad de que un producto se
quede sin stock dentro de un horizonte de 30 días, expuesto por una API y
consumido por una aplicación Spring Boot.

```
Excel mensuales
      ↓  ingestion      perfila productos: clase, consumos, rotación
   productos.json
      ↓  simulation     genera un año de movimientos diarios
   inventario.db
      ↓  features       construye el dataset supervisado
      ↓  training       entrena el Pipeline y guarda .joblib + metadata
   modelo.joblib
      ↓  inference      Predictor: carga el modelo y predice
      ↓  api            FastAPI: capa HTTP delgada
      ↓
   Spring Boot → navegador
```

> **El modelo activo está entrenado con datos SIMULADOS y no ha sido validado
> con historia real.** Cada respuesta de la API lo indica explícitamente. Es una
> demostración técnica funcional, no un sistema listo para decidir compras.

---

# 1. Instalación desde cero

## Requisitos

- **Python 3.10 o superior.** Comprueba con `python --version`.
  Si dice 3.9 o menos, instala una versión nueva desde python.org.
- Git (opcional, solo si clonas el repositorio).

En Windows, al instalar Python marca la casilla **"Add Python to PATH"**. Si no
lo hiciste, el comando `python` no funcionará desde la terminal.

## Paso 1 — Situarte en la carpeta correcta

Todos los comandos se ejecutan desde `backend_python/`, la carpeta que contiene
`pyproject.toml`. **No desde `src/`.**

```powershell
cd C:\ruta\a\InventarioPred\backend_python
```

Verifica que estás bien:

```powershell
dir pyproject.toml      # Windows
ls pyproject.toml       # Linux / macOS
```

Si dice que no existe, estás en la carpeta equivocada.

## Paso 2 — Crear el entorno virtual

Aísla las dependencias del proyecto de tu Python del sistema.

```powershell
python -m venv .venv
```

Activarlo:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

Sabrás que funcionó porque la terminal muestra `(.venv)` al principio de la
línea. **Hay que activarlo cada vez que abras una terminal nueva.**

> Si PowerShell dice *"no se puede cargar el archivo porque la ejecución de
> scripts está deshabilitada"*, ejecuta una vez:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

## Paso 3 — Instalar el paquete

```powershell
pip install -e ".[dev]"
```

Esto instala pandas, scikit-learn, FastAPI, uvicorn y demás, **y además registra
`inventory_ml` como paquete**. Eso último es lo que permite ejecutar
`python -m inventory_ml.algo` desde cualquier directorio sin errores de rutas.

El `-e` significa "editable": si cambias el código, no hay que reinstalar. Las
comillas alrededor de `".[dev]"` son obligatorias en PowerShell.

Comprueba que quedó bien:

```powershell
python -c "import inventory_ml; print(inventory_ml.__version__)"
```

Debe imprimir un número de versión. Si dice `ModuleNotFoundError`, el
`pip install -e .` falló o no tienes el entorno activado.

## Paso 4 — Configuración (opcional)

Todos los valores tienen defaults sensatos en `src/inventory_ml/config.py`. Solo
necesitas un `.env` si quieres cambiar algo o usar el asistente de IA.

```powershell
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS
```

Edita `.env` y **descomenta** (quita el `#`) lo que quieras cambiar. Una línea
comentada no existe: `.env.example` viene todo comentado porque es una
plantilla, no una configuración.

```
LLM_API_KEY=tu_clave_aqui
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

El `.env` está en `.gitignore` y **nunca** debe subirse al repositorio.

---

# 2. Generar el modelo

Los datos y el modelo no vienen en el repositorio: se generan. Ejecuta los
cuatro comandos **en este orden**, porque cada uno consume la salida del
anterior.

```powershell
# 1. Perfilar el histórico real -> 400 productos (100 por clase de rotación)
python -m inventory_ml.ingestion.perfilado --n-por-clase 100

# 2. Simular un año de movimientos -> data/inventario.db
python -m inventory_ml.simulation.simulador --dias 365

# 3. Entrenar -> artifacts/models/stockout_simulated_v1.joblib + metadata
python -m inventory_ml.training.train

# 4. Generar los CSV de riesgo (los que consumía Java antes de la API)
python -m inventory_ml.reporting.riesgo
```

El paso 1 necesita `data/raw/inventario_consolidado.csv`. Si tienes los Excel
mensuales sin consolidar, ese paso aún es manual.

Tarda menos de un minuto en total. Entrada esperada del paso 3:

```
INFO: Dataset construido: 134000 filas
INFO: Split temporal en 2026-09-26 | train=107200 test=26800
INFO: Metricas holdout temporal: {'accuracy': 0.96, 'roc_auc': 0.99, ...}
INFO: Artefacto guardado en .../stockout_simulated_v1.joblib
```

## Verificar que el modelo sirve

```powershell
# ¿acierta? -> métricas sobre datos no vistos, comparadas con una regla trivial
python -m inventory_ml.training.evaluar

# ¿sirve? -> misma demanda, política reactiva vs. política con el modelo
python -m inventory_ml.simulation.experimento --dias 365 --umbral 0.3 --umbral 0.5 --umbral 0.8
```

El segundo comando además genera el JSON que alimenta el gráfico comparativo de
la página web. **Hay que volver a ejecutarlo cada vez que reentrenes**, o el
gráfico mostrará el modelo anterior.

---

# 3. Levantar la API

```powershell
uvicorn inventory_ml.api.main:app --reload
```

Queda en `http://127.0.0.1:8000`. Documentación interactiva en
`http://127.0.0.1:8000/docs` — desde ahí puedes probar todos los endpoints sin
escribir un solo comando.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/health` | ¿está viva y con modelo cargado? 200 / 503 |
| GET | `/api/v1/model/info` | metadata del modelo activo |
| POST | `/api/v1/predict` | predicción de un producto |
| POST | `/api/v1/predict/batch` | varios productos, vectorizado (máx. 500) |
| GET | `/api/v1/inventario` | estado del inventario en una fecha + predicción |
| GET | `/api/v1/inventario/fechas` | rango de fechas disponible |
| GET | `/api/v1/experimento` | comparación de políticas (precalculado) |
| POST | `/api/v1/asistente` | pregunta en lenguaje natural (requiere `LLM_API_KEY`) |

## Probar a mano

En **Windows PowerShell**, `curl` es un alias de `Invoke-WebRequest` y **no**
entiende `-X`, `-H` ni `-d`. Usa `Invoke-RestMethod`:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/model/info

$body = @{
    codigo                = "188486"
    stock_actual          = 12
    consumo_promedio      = 4.5
    consumo_minimo        = 1
    consumo_maximo        = 18
    reposicion_promedio   = 120
    frecuencia_movimiento = 0.42
    clase                 = "Alta"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/predict `
  -ContentType "application/json" -Body $body
```

En **Linux, macOS o Git Bash**:

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"codigo":"188486","stock_actual":12,"consumo_promedio":4.5,
       "consumo_minimo":1,"consumo_maximo":18,"reposicion_promedio":120,
       "frecuencia_movimiento":0.42,"clase":"Alta"}'
```

O simplemente usa `/docs`, que es más cómodo que cualquiera de los dos.

---

# 4. Tests

```powershell
pytest -q
```

Deben pasar **51**. Cubren: carga del modelo, comportamiento cuando falta,
validación de entradas, los cuatro endpoints principales, límites del batch,
que la probabilidad corresponda a la clase positiva correcta, que el riesgo
decrezca al subir el stock, que los errores no filtren rutas ni claves, y una
prueba de integración con el artefacto real.

Si el artefacto no existe, los tests de integración se saltan solos (verás
`skipped`) — el resto funciona igual.

---

# 5. Problemas comunes

**`ModuleNotFoundError: No module named 'inventory_ml'`**
No ejecutaste `pip install -e .`, o el entorno virtual no está activado.
Comprueba que la terminal muestre `(.venv)`.

**`No se encontró data/raw/inventario_consolidado.csv`**
Falta el CSV de entrada del paso 1. Debe estar en `data/raw/`.

**`/health` responde `{"status":"degraded","model_loaded":false}`**
No has entrenado todavía. Ejecuta los pasos 1 a 3 de la sección 2.

**La API responde con el modelo viejo después de reentrenar**
`--reload` de uvicorn detecta cambios en el **código**, no un `.joblib` nuevo.
Detén el servidor (Ctrl+C) y vuelve a arrancarlo.

**`/api/v1/experimento` devuelve 503**
Falta generar el JSON:
`python -m inventory_ml.simulation.experimento --dias 365 --umbral 0.8`

**El asistente devuelve 503 diciendo que falta `LLM_API_KEY`**
Revisa que en `.env` la línea **no** empiece con `#`. Verifica con:
`python -c "from inventory_ml import config; print(config.llm_configurado())"`

**`curl: A parameter cannot be found that matches parameter name 'X'`**
Estás en PowerShell, donde `curl` es otra cosa. Usa `Invoke-RestMethod`, o
llama al curl real con `curl.exe`.

**`Activate.ps1 no se puede cargar porque la ejecución de scripts está deshabilitada`**
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

**Cualquier comando falla con rutas raras**
Estás ejecutando desde la carpeta equivocada. Todos los comandos van desde
`backend_python/`, la que contiene `pyproject.toml`.

---

# 6. Estructura del proyecto

```
backend_python/
├── pyproject.toml           dependencias y configuración del paquete
├── .env.example             plantilla de configuración
├── data/
│   ├── raw/                 CSV histórico (única fuente irreemplazable)
│   ├── interim/             productos perfilados (generado)
│   └── inventario.db        simulación (generado)
├── artifacts/
│   ├── models/              .joblib + metadata (generado)
│   └── reports/             CSV y JSON de resultados (generado)
├── src/inventory_ml/
│   ├── config.py            rutas, horizonte, umbrales de riesgo
│   ├── repository.py        lectura del inventario simulado
│   ├── resumen.py           contexto compacto para el asistente
│   ├── ingestion/           Excel/CSV → perfil de productos
│   ├── simulation/          simulador y experimento de políticas
│   ├── features/            contrato de columnas y target
│   ├── training/            entrenamiento y evaluación
│   ├── inference/           Predictor
│   ├── reporting/           CSV de riesgo
│   └── api/                 FastAPI
└── tests/
```

Todo lo que está bajo `data/` (salvo `raw/`) y `artifacts/` es **generado**: se
puede borrar y reconstruir con los cuatro comandos. Lo único irreemplazable es
`data/raw/`.

---

# 7. Decisiones de diseño

**Una sola fuente para cada cosa.** Los umbrales de riesgo (ALTO > 70%,
MEDIO 40–70%, BAJO < 40%) viven solo en `config.nivel_riesgo()`. El contrato de
features vive solo en `features/dataset.py`. Ningún otro archivo los repite.

**El encoding va dentro del Pipeline.** `clase` se codifica con un
`OrdinalEncoder` de categorías fijas `["Muerto","Baja","Media","Alta"]` dentro
del artefacto. El código original lo hacía con `.astype("category").cat.codes`
por separado en entrenamiento e inferencia, lo que daba códigos distintos según
qué clases trajera cada lote — y con un solo producto siempre devolvía 0.

**Split temporal, no aleatorio.** Con series diarias por producto, un split
aleatorio pone filas casi idénticas en train y test e infla las métricas.

**La clase positiva se verifica.** Se resuelve con
`list(pipeline.classes_).index(1)`, nunca asumiendo `predict_proba(X)[:, 1]`.
Hay un test.

**El modelo se carga una vez**, en el `lifespan` de FastAPI, no por petición.

**El origen del modelo viaja en cada respuesta**, no solo en `/model/info`.
`origen_modelo: SIMULADO` y `estado_validacion: NO_VALIDADO_CON_DATOS_REALES`
salen de la metadata del artefacto. Cambiar a un modelo validado con datos
reales no requiere tocar el contrato HTTP.

**Definición del target:** un producto cuenta como agotado si su stock llega a
cero **en algún momento** dentro del horizonte, no solo el último día:

```
min(stock[t .. t+30]) <= 0
```

La versión anterior miraba solo `stock[t+30]`, y como en el simulador la
reposición llegaba exactamente a los 30 días, un producto que pasaba 29 días en
cero quedaba etiquetado como "no agotado". El modelo aprendía que estar en cero
no era problema y asignaba riesgo BAJO a productos ya agotados.

**Sin CORS ni autenticación.** Spring Boot llama servidor a servidor, donde CORS
no aplica. La API no se expone públicamente; si algún día se hace, necesita al
menos una API key.

**Los errores no filtran detalles.** El stack trace va al log; el cliente recibe
un mensaje genérico. Hay tests que verifican que ni rutas internas ni claves
llegan a la respuesta.

---

# 8. Limitaciones honestas

Estas no son defectos de implementación: son límites del enfoque, y conviene
tenerlos claros antes de presentar cualquier número.

**Circularidad.** El modelo se entrena y se evalúa sobre datos del mismo
simulador. Las métricas miden si aprendió las reglas del generador, no si
predice el inventario real. Un ROC-AUC de 0.99 no significa que funcione en
producción.

**Features estáticas.** `consumo_promedio`, `clase` y las demás son constantes
por producto: lo único que varía en el tiempo es `stock_actual`. El modelo tiene
poco de dónde aprender más allá de eso.

**La predicción se auto-invalida al usarla.** El modelo aprendió el
comportamiento del inventario *bajo la política de pedir al llegar a cero*. Si
compras anticipadamente, cambias el mundo que aprendió. Por eso el experimento
mantiene la política reactiva como red de seguridad en vez de sustituirla.

**Horizonte igual al lead time.** Ambos son 30 días, así que un aviso a 30 días
vista llega justo cuando el pedido tardaría 30 en llegar: cero margen. Para
ganar holgura, el horizonte debería superar al lead time. Es cambiar
`HORIZONTE_DIAS` y reentrenar.

**Los productos "Muerto" en cero salen con riesgo ALTO.** Es correcto según la
definición del target — están en cero y ahí seguirán — pero no son prioridad de
compra porque nadie los consume. La probabilidad responde "¿estará sin stock?",
no "¿debería comprarlo?".

---

# 9. Frontend (Spring Boot)

La aplicación Java consume esta API a través de `PredictionClient`, que es el
único punto de contacto con Python. El navegador nunca llama a FastAPI
directamente: pasa por Spring, de modo que la API puede quedarse en la red
interna.

Configuración necesaria en `application.properties`:

```properties
prediction.api.url=http://127.0.0.1:8000
```

**Levanta FastAPI antes que Spring.** Si no, la tabla mostrará "servicio no
disponible" hasta que recargues.
