# Conectar Spring Boot con la API de predicción

```
navegador → Spring (/api/inventario) → FastAPI (/api/v1/inventario) → Predictor → Pipeline
```

El navegador **no** llama a FastAPI directamente: pasa por Spring. Así FastAPI
puede quedarse en la red interna y tu sesión de Spring sigue protegiendo el
acceso. Por eso tampoco hace falta CORS.

## Archivos

| Archivo | Dónde va |
|---|---|
| `InventarioDTO.java` | `com.maple.back.dto` |
| `PredictionClient.java` | `com.maple.back.services.prediction` |
| `InventarioController.java` | `com.maple.back.controller` |
| `menu-inventario.js` | reemplaza el `<script defer>` del CSV en `menu.html` |
| `application-prediccion.properties` | fusiona en tu `application.properties` |

## Pasos

1. Copia las tres clases Java a sus paquetes.
2. Añade `prediction.api.url=http://127.0.0.1:8000` a `application.properties`.
3. En `menu.html`, borra el bloque `<script defer>` que hace
   `fetch('/temp/validacion_externa.csv')` y pon el contenido de
   `menu-inventario.js`.
4. Quita la columna **Agotado 30d** del `<thead>` (queda en 6 columnas) y, si
   quieres el selector de fecha, añade junto al buscador:
   ```html
   <input type="date" id="fechaInventario"
          class="px-4 py-2 border border-sky-300 rounded-lg">
   ```
5. Levanta FastAPI (`uvicorn inventory_ml.api.main:app`) y luego Spring.

## Por qué cambia la tabla

**Se va `Agotado 30d`.** Es la etiqueta real: solo se conoce 30 días después.
En una vista del día actual, mostrarla sería mostrar el futuro. Si la quieres
para sustentar, va en una pantalla aparte de *validación histórica*, donde
comparas predicción contra lo que realmente pasó — que es otra cosa, y muy
defendible en un proyecto de grado.

**La paginación pasa al servidor.** Antes se descargaba el CSV completo al
navegador y se paginaba en JS. Con 400 productos daba igual; con 44.582 del
catálogo real, no.

**Aparece el estado del modelo.** La respuesta trae `origen_modelo` y
`estado_validacion`, y la vista los pinta como aviso. Quien mire la tabla ve
que el modelo es SIMULADO y no está validado. No es un detalle estético: es lo
que impide que alguien tome la pantalla por productiva.

## Decisiones

**Mapeo con `@JsonProperty` campo por campo**, no con
`spring.jackson.property-naming-strategy=SNAKE_CASE`. Esa propiedad es global y
cambiaría el JSON de todos tus endpoints actuales, incluido el de notificaciones.

**`@JsonIgnoreProperties(ignoreUnknown = true)`** en todos los DTOs: si Python
añade un campo, Java no se cae.

**Timeouts explícitos** (3 s conectar, 10 s leer). Sin ellos, una FastAPI caída
deja hilos de Tomcat colgados hasta agotar el pool.

**Degradación, no excepción.** `PredictionClient` devuelve `Optional.empty()` y
el controller responde 503; la tabla muestra "servicio no disponible" en vez de
una página en blanco o un stack trace.

## Pendiente

- El endpoint queda protegido por tu Spring Security actual; revisa que
  `/api/inventario/**` requiera sesión como el resto.
- FastAPI no tiene autenticación. Mientras sea `127.0.0.1` está bien; si algún
  día vive en otro host, necesita al menos una API key.
- La anomalía del `stock_actual = 0` sigue ahí: un producto agotado sale con
  riesgo BAJO. En la tabla se va a notar. Se arregla rediseñando el target.
