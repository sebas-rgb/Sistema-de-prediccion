# El .env ahora sí se lee

Antes `config.py` solo miraba `os.environ`, así que el `.env` no hacía nada.
Corregido: se carga con python-dotenv al importar la configuración.

## Archivos

| Archivo | Cambio |
|---|---|
| `src/inventory_ml/config.py` | carga `.env` al importar |
| `pyproject.toml` | añade `python-dotenv` |
| `.env.example` | limpio, sin el `MAX_BATCH_SIZE` duplicado |

```bash
pip install -e .
```

## Cómo se usa

Crea un `.env` en la raíz de `backend_python/` (junto a `pyproject.toml`):

```
LLM_API_KEY=gsk_tu_clave_nueva
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

**Sin `#` delante.** Una línea comentada es una línea que no existe: por eso
`.env.example` viene todo comentado, es una plantilla, no una configuración.

Luego, sin variables de entorno ni nada:

```bash
uvicorn inventory_ml.api.main:app --reload
```

## Prioridad

Lo que definas en la terminal gana sobre el `.env` (`override=False`). Así
puedes probar otro modelo un rato sin editar el archivo:

```powershell
$env:LLM_MODEL="llama-3.1-8b-instant"
uvicorn inventory_ml.api.main:app --reload
```

Para volver al valor del `.env`, cierra esa terminal o usa
`Remove-Item Env:LLM_MODEL`.

## Comprobar que agarró la clave

```bash
python -c "from inventory_ml import config; print(config.llm_configurado(), config.LLM_MODEL)"
```

Debe imprimir `True` y el modelo. Si sale `False`, el `.env` no está donde
config lo busca o la línea sigue comentada.

## Seguridad

`.env` ya está en `.gitignore`. Comprueba que no lo hayas subido antes:

```bash
git log --all --full-history -- .env
```

Si aparece algo, esa clave está comprometida y hay que revocarla — borrarla del
repositorio no basta, queda en el historial.
