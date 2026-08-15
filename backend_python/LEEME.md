# Python — 5 archivos

Copia respetando la estructura: la carpeta `src/` y `tests/` de este zip se
superponen sobre las tuyas en `backend_python/`.

| Archivo | Estado |
|---|---|
| `src/inventory_ml/repository.py` | **nuevo** — lee el inventario simulado |
| `src/inventory_ml/api/inventario.py` | **nuevo** — el endpoint |
| `src/inventory_ml/api/schemas.py` | reemplaza — 3 schemas añadidos al final |
| `src/inventory_ml/api/main.py` | reemplaza — 2 líneas nuevas |
| `tests/test_api_inventario.py` | **nuevo** — 9 tests |

Si prefieres editar a mano en vez de sobrescribir, en `main.py` son solo estas
dos líneas:

```python
from inventory_ml.api.inventario import router as inventario_router   # con los imports
app.include_router(inventario_router)                                  # al final
```

## Verificar antes de tocar Java

```bash
pytest -q                                    # 38 passed, 1 xfailed
uvicorn inventory_ml.api.main:app --reload
```

Abre `http://127.0.0.1:8000/api/v1/inventario/fechas`. Si devuelve el rango de
tu simulación, el lado Python quedó listo.

No hay que reentrenar ni volver a simular: el endpoint usa la `inventario.db` y
el `.joblib` que ya tienes.
