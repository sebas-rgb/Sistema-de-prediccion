# API — Fase 1

```
Pipeline (.joblib)  ->  inference.Predictor  ->  FastAPI  ->  JSON
```

FastAPI es una capa delgada: no entrena, no simula, no lee Excel, no hace
feature engineering. Solo valida JSON, llama al `Predictor` y serializa.

## Archivos

| Archivo | Rol |
|---|---|
| `api/main.py` | app, lifespan, endpoints, manejo de errores |
| `api/schemas.py` | contrato Pydantic (lo que Spring mapeará a DTOs) |
| `api/dependencies.py` | inyección del `Predictor` desde `app.state` |
| `tests/test_api.py` | 20 tests con modelo controlado |
| `tests/test_api_integracion.py` | cadena completa con el artefacto real |

## Ejecución

```bash
uvicorn inventory_ml.api.main:app --reload
```

Funciona desde cualquier directorio (el paquete está instalado con `-e`).
Swagger en `http://127.0.0.1:8000/docs`.

## Endpoints

| Método | Ruta | Códigos |
|---|---|---|
| GET | `/health` | 200 ok · 503 degradado |
| GET | `/api/v1/model/info` | 200 · 503 |
| POST | `/api/v1/predict` | 200 · 422 · 503 · 500 |
| POST | `/api/v1/predict/batch` | 200 · 422 · 503 · 500 |

## Prueba manual

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/model/info

curl -X POST http://127.0.0.1:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"codigo":"188486","stock_actual":12,"consumo_promedio":4.5,
       "consumo_minimo":1,"consumo_maximo":18,"reposicion_promedio":120,
       "frecuencia_movimiento":0.42,"clase":"Alta"}'

curl -X POST http://127.0.0.1:8000/api/v1/predict/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[{"codigo":"111","stock_actual":2,"consumo_promedio":9,
       "consumo_minimo":1,"consumo_maximo":25,"reposicion_promedio":80,
       "frecuencia_movimiento":0.55,"clase":"Alta"}]}'
```

## Decisiones documentadas

**Prefijo `/api/v1`** para el contrato de negocio; `/health` queda en la raíz
porque es una sonda de infraestructura, no parte del contrato. Cuesta nada ahora
y permite convivencia de versiones cuando el target se rediseñe.

**`/health` devuelve 503 cuando el modelo falta.** Así un readiness probe o un
balanceador lo detecta por código de estado sin leer el cuerpo. El cuerpo sigue
siendo `{"status":"degraded","model_loaded":false}`.

**La app arranca aunque el modelo falle.** No se aborta el arranque: queda
degradada, lo reporta en `/health` y `/predict` responde 503. Nunca devuelve
predicciones inventadas ni valores por defecto.

**`MAX_BATCH_SIZE = 500`.** El catálogo activo es de 400 productos, así que 500
permite puntuarlo entero en una sola llamada dejando margen, y acota la memoria
por petición. Configurable por entorno.

**Sin CORS.** Spring Boot llama servidor-a-servidor, donde CORS no aplica.
Habilitarlo solo si algún día lo consume un navegador.

**Sin autenticación todavía.** No hay infraestructura de auth en el proyecto y
la API no se expone públicamente en esta fase. Antes de exponerla hace falta al
menos una API key o red privada.

**Errores sin filtraciones.** El detalle técnico va al log; el cliente recibe un
mensaje genérico. Hay un test que verifica que una excepción con una ruta dentro
del mensaje no llega a la respuesta.

## Estado del modelo

`origen_modelo: SIMULADO` y `estado_validacion: NO_VALIDADO_CON_DATOS_REALES`
salen de la metadata del artefacto y viajan en **cada** respuesta, no solo en
`/model/info`. Un consumidor no puede leer una predicción sin ver su estado.
Cambiar a un modelo real solo requiere reentrenar con otras constantes:
el contrato HTTP no cambia.

## Anomalía conocida

Un producto con `stock_actual = 0` recibe MENOS probabilidad (~0.30) que uno con
`stock_actual = 3` (~0.97). Causa: el target está contaminado por la política de
reposición del simulador (lead time 30 = horizonte 30). Documentado en
`tests/test_api_integracion.py::test_stock_cero_deberia_ser_el_maximo_riesgo`
como `xfail`; cuando se rediseñe el target, ese test pasará y habrá que quitarle
el marcador. **Spring Boot no debería tomar decisiones de compra con este
artefacto todavía** — la integración técnica sí puede construirse.
