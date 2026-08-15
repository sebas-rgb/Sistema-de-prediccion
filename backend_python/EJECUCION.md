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

## 5-6. Verificar que el modelo sirve

```bash
# ¿acierta? -> métricas sobre datos no vistos + comparación con regla trivial
python -m inventory_ml.training.evaluar

# ¿sirve? -> misma demanda, política reactiva vs política con el modelo
python -m inventory_ml.simulation.experimento --umbral 0.8
```

El experimento congela la demanda antes de empezar: ambos brazos enfrentan el
mismo flujo día a día, así que la diferencia viene de la política y no del azar.

### Cómo leer los resultados

`evaluar` compara contra `stock_actual / consumo_promedio < horizonte`, que es
una división. Si el modelo no le gana por un margen claro en PR-AUC, no aporta.
La tabla de calibración dice si un 80% significa de verdad 80%.

`experimento` muestra el trade-off real: bajar el umbral evita más quiebres pero
emite más pedidos y sube el stock promedio (capital parado). Elegir el umbral es
una decisión de negocio, no técnica.

### Tres límites que hay que tener presentes

1. **Circularidad.** El modelo se entrenó con datos del simulador y se prueba en
   el mismo simulador. Mide "¿aprendió las reglas del generador?", no "¿predice
   la realidad?". Los números serán buenos y no valen como validación.
2. **Cambio de política.** El modelo aprendió P(agotamiento) *bajo la política
   reactiva*. Al actuar sobre la predicción cambias el mundo que aprendió: las
   predicciones se auto-invalidan. Lo correcto a futuro es predecir consumo o
   días de cobertura, no el binario, o reentrenar sobre datos generados con la
   política nueva.
3. **`lead_time` = `horizonte` = 30.** Si pides el día que el modelo se activa a
   30 días vista, el pedido llega justo cuando ya te quedaste sin stock. Para
   ganar margen, el horizonte de predicción debe superar al lead time.

### El target está contaminado por la política (importante)

Comprobación sobre los datos de entrenamiento:

```
filas con stock_actual = 0  ->  target = 1 solo el 30% de las veces
probabilidad que el modelo asigna a un producto en cero: 0.05 - 0.30
```

Motivo: en el simulador, al llegar a cero se emite un pedido que llega
**exactamente a los 30 días**, justo el horizonte del target. La etiqueta acaba
significando *"seguirá agotado dado que alguien repone al llegar a cero"*, no
*"se va a agotar"*.

Consecuencia práctica: si la política predictiva sustituye a la reactiva en vez
de sumarse a ella, los productos ya agotados quedan abandonados (el modelo dice
que están bien, porque aprendió que se resuelven solos). Por eso
`simular_politica` mantiene la **red de seguridad**: pedir siempre que el stock
llegue a cero, además de anticiparse cuando el modelo se activa. `--sin-red`
reproduce el comportamiento degenerado.

Arreglo de fondo, para cuando toque: que el target no dependa de la reposición.
Opciones: predecir consumo o días de cobertura en vez del binario, o construir
un target contrafactual (¿se agotaría *sin* reposición?). Es un cambio en
`features.construir_dataset()` + reentrenar; no toca la API.

### Qué métrica manda

`dias_agotado` cuenta también los productos muertos, que están en cero porque
nadie los pide y a nadie le importan. `dias_agotado_utiles` excluye los que no
tienen demanda. La métrica que decide es **`unidades_no_servidas`** / `fill_rate`:
demanda que llegó y no pudiste atender.
