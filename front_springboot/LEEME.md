# Spring — copiar respetando rutas

La estructura de este zip refleja la de tu proyecto, así que puedes
superponerla sobre `back/` directamente.

| Archivo | Destino | Estado |
|---|---|---|
| `dto/InventarioDTO.java` | `com.maple.back.dto` | nuevo |
| `services/prediction/PredictionClient.java` | paquete nuevo dentro de `services` | nuevo |
| `controller/InventarioController.java` | `com.maple.back.controller` | nuevo |
| `static/menu-inventario.js` | ya lo tienes ahí; reemplázalo | reemplaza |
| `templates/menu.html` | reemplaza el tuyo | reemplaza |

## Falta un paso manual

En `application.properties`:

```properties
prediction.api.url=http://127.0.0.1:8000
```

Es la única línea. **No** añadas
`spring.jackson.property-naming-strategy=SNAKE_CASE`: es global y cambiaría el
JSON de todos tus endpoints actuales, incluido el de notificaciones. El mapeo
snake_case va con `@JsonProperty` campo por campo dentro del DTO.

## Qué cambió en menu.html

Sobre tu versión, solo tres cosas; el resto es idéntico (modal de datos,
navbar, campana, WebSocket, footer, todo intacto):

1. El `<script defer>` que hacía `fetch('/temp/validacion_externa.csv')` se
   reemplazó por `<script th:src="@{/menu-inventario.js}" defer></script>`.
2. Se quitó la columna **Agotado 30d** del `<thead>` (la tabla queda en 6
   columnas) y la última pasó a llamarse "Riesgo de agotamiento", que ahora
   muestra el porcentaje y el nivel con color.
3. Se añadió un `<input type="date" id="fechaInventario">` junto al buscador.

`/temp/validacion_externa.csv` ya no se usa: puedes borrar esa carpeta cuando
verifiques que la tabla carga.

## Orden

1. Levanta FastAPI primero.
2. Copia los archivos, añade la línea al `.properties`.
3. Arranca Spring y entra a `/menu`.

Si la tabla dice "Servicio de predicción no disponible", FastAPI no está
arriba o la URL del `.properties` no coincide.
