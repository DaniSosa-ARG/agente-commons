# Handbook — US: Soporte async en run_agent handler

## Contexto del problema

`agente-turnos` usa `agente-commons` como paquete externo para manejar
los webhooks de WhatsApp (Meta y Twilio) a través de `create_whatsapp_router`.

El router recibe un parámetro `run_agent` que es la función que procesa
cada mensaje entrante. Actualmente `create_whatsapp_router` espera una
función **síncrona**.

El problema: `run_agent` en `agente-turnos` llama a la API de Anthropic
(Claude Sonnet), que tarda entre 5 y 30 segundos. Durante ese tiempo,
el event loop de FastAPI queda **bloqueado**, el webhook no devuelve 200
a Meta, Meta reintenta el webhook, y el mensaje se procesa dos veces
generando respuestas y confirmaciones duplicadas al paciente.

## Síntoma observado en producción

- Meta envía un mensaje al webhook POST /whatsapp
- El agente tarda >5s en responder (llamada a Anthropic API)
- Meta no recibe 200 a tiempo → reintenta el POST
- El agente procesa el mismo mensaje dos veces
- El paciente recibe dos respuestas y/o dos confirmaciones de turno

## Intento de fix fallido

En `agente-turnos/main.py` se intentó wrappear el adapter en una coroutine:

```python
async def _run_agent_adapter_async(...):
    return await asyncio.to_thread(_run_agent_adapter, ...)
```

Y pasarla al router:
```python
run_agent = _run_agent_adapter_async,
```

**Resultado:** `RuntimeWarning: coroutine '_run_agent_adapter_async' was never awaited`

`agente-commons` llama `run_agent(...)` sincrónicamente — no hace `await`,
por lo que la coroutine nunca se ejecuta y el handler explota con 500.

## Solución requerida

`create_whatsapp_router` debe detectar si `run_agent` es una coroutine
(función async) y hacer `await` sobre ella, o correr la función síncrona
en un thread pool con `asyncio.to_thread`.

La solución más robusta es que el handler interno del router use siempre
`asyncio.to_thread` si `run_agent` es síncrono, o `await` si es async.

```python
import asyncio, inspect

async def _llamar_run_agent(run_agent_fn, *args, **kwargs):
    if inspect.iscoroutinefunction(run_agent_fn):
        return await run_agent_fn(*args, **kwargs)
    else:
        return await asyncio.to_thread(run_agent_fn, *args, **kwargs)
```

Esto hace que:
- El webhook devuelva 200 a Meta **inmediatamente** al recibir el mensaje
- `run_agent` corra en background sin bloquear el event loop
- No se requiera ningún cambio en `agente-turnos`

## Contrato actual de create_whatsapp_router

```python
whatsapp_router = create_whatsapp_router(
    app_id            = "agente-turnos",
    resolver_meta     = _wrap_con_metrica(resolver_consultorio_meta, "meta"),
    resolver_twilio   = _wrap_con_metrica(resolver_consultorio_twilio, "twilio"),
    run_agent         = _run_agent_adapter,      # función síncrona
    get_historial     = get_historial,           # función async
    save_historial    = save_historial,          # función async
    meta_verify_token = META_VERIFY_TOKEN,
    meta_app_secret   = META_APP_SECRET,
)
```

El cambio debe ser **backwards compatible** — si `run_agent` es síncrono,
sigue funcionando igual que antes pero sin bloquear el event loop.

## Criterios de aceptación (Gherkin)

```gherkin
Scenario: run_agent síncrono no bloquea el event loop
  GIVEN create_whatsapp_router configurado con run_agent síncrono
  WHEN Meta hace POST /whatsapp con un mensaje
  THEN el webhook devuelve 200 antes de que run_agent termine
  AND run_agent se ejecuta en un thread pool sin bloquear el event loop
  AND el paciente recibe una sola respuesta

Scenario: run_agent async es awaited correctamente
  GIVEN create_whatsapp_router configurado con run_agent async
  WHEN Meta hace POST /whatsapp con un mensaje
  THEN el router hace await sobre run_agent
  AND no lanza RuntimeWarning de coroutine never awaited
  AND el paciente recibe una sola respuesta

Scenario: Backwards compatibility — comportamiento funcional no cambia
  GIVEN cualquier implementación existente de run_agent (sync o async)
  WHEN se actualiza agente-commons con este cambio
  THEN los tests existentes pasan sin modificación
  AND el contrato de create_whatsapp_router no cambia
```

## Archivos a modificar en agente-commons

El cambio está concentrado en el handler interno del router de Meta
(y opcionalmente Twilio). Buscar dónde se hace la llamada a `run_agent`
dentro de `create_whatsapp_router` o el handler que registra y reemplazar
la llamada síncrona por la versión con `inspect.iscoroutinefunction`.

## Impacto en agente-turnos

Cero cambios requeridos. `_run_agent_adapter` sigue siendo síncrono.
`agente-commons` lo corre en `asyncio.to_thread` automáticamente.

## Tests sugeridos

- `test_run_agent_sync_no_bloquea_event_loop`
- `test_run_agent_async_es_awaited`
- `test_backwards_compatibility_sync`
- `test_no_mensaje_duplicado_bajo_latencia`
