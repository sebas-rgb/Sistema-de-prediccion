# Cambio de target — 3 archivos Python

Solo Python. **No se toca nada de Spring**: endpoints, schemas, DTOs y la
tabla siguen igual. Cambia qué significa el número, no el contrato.

| Archivo | Cambio |
|---|---|
| `src/inventory_ml/features/dataset.py` | el target ahora es el mínimo de la ventana |
| `src/inventory_ml/training/train.py` | versión 2.0.0 + `definicion_target` en metadata |
| `tests/test_api_integracion.py` | el `xfail` pasa a test real + monotonía |

## El cambio

```python
# antes — una foto al final del horizonte
stock[t + 30] <= 0

# ahora — toda la ventana, incluido hoy
min(stock[t .. t + 30]) <= 0
```

## Después de copiar

```bash
python -m inventory_ml.training.train
pytest -q                                   # 40 passed
```

No hace falta volver a perfilar ni simular: la `inventario.db` sirve igual,
solo cambia cómo se calcula la etiqueta a partir de ella.

Reinicia uvicorn para que cargue el artefacto nuevo (`--reload` no detecta un
`.joblib` nuevo, solo cambios de código).

## Qué esperar

Riesgo por stock, resto de features constante:

```
stock    0 -> 100.0%  ALTO
stock    9 -> 100.0%  ALTO
stock   30 ->  98.4%  ALTO
stock  100 ->  73.6%  ALTO
stock  400 ->  11.1%  BAJO
```

## Dos advertencias honestas

**Las métricas suben, pero no porque el modelo sea mejor.** Pasaron de 0.92 a
0.96 de accuracy y de 0.96 a 0.99 de ROC-AUC. La causa es que el target nuevo
es más fácil: "stock 0 hoy" implica agotamiento por definición, y esa parte el
modelo la acierta trivialmente. No presentes esa mejora como si el modelo
hubiera aprendido más — el target cambió, y comparar los dos números es
comparar peras con manzanas.

**Los productos muertos en cero salen 100% ALTO.** Es correcto según la
definición (están en cero y ahí seguirán), pero no son una prioridad de
compra: nadie los consume. Si la lista de riesgo ALTO se te llena de muertos,
filtra por `consumo_promedio > 0` en la vista. La probabilidad responde
"¿estará sin stock?", no "¿debería comprarlo?" — son preguntas distintas y
conviene tenerlo claro al sustentar.
