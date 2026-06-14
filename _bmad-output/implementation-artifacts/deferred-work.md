# Deferred Work

## Deferred from: code review of US-EC-08-envio-twilio (2026-06-14)

- **Consumer app wiring is outside this repo** (`agente-turnos/main.py`): pass `twilio_account_sid`, `twilio_auth_token`, and `twilio_whatsapp_from` into `create_whatsapp_router` to activate Twilio sending. Deferred because this review is scoped to `agente-commons`; the wiring belongs in the consuming repo.
- **Full phone number is logged on Twilio send failure** (`agente_commons/whatsapp/router.py:140`): the new Twilio failure path logs `numero_jugador` directly. Deferred because the same logging pattern already exists in Meta send failure logging and should be handled as a cross-channel logging/privacy policy cleanup.

## Deferred from: code review of US-EC-06-async-run-agent-handler (2026-06-04)

- **F-04 Race condition en historial por requests concurrentes** (`router.py:_procesar_meta/_procesar_twilio`): dos requests simultáneos al mismo `session_id` harán `get_historial` y `save_historial` sin sincronización; el segundo save pisará el primero. Requiere Redis locks o estructura atómica. Pre-existente.
- **F-05 `except Exception` amplio sin retry** (`router.py:_procesar_meta/_procesar_twilio`): errores transitorios (timeout Claude API) y permanentes (input inválido) reciben el mismo tratamiento. Diseño explícito en spec; posible mejora: retry con backoff para errores de red.
- **F-06 `get_historial`/`save_historial` sin timeout** (`router.py`): si Redis cuelga, el background task cuelga indefinidamente. Pre-existente; agregar `asyncio.wait_for(coro, timeout=...)`.
- **F-07 `resolver_meta`/`resolver_twilio` síncronos en handler async** (`router.py`): si los resolvers hacen I/O (DB lookup), bloquean el event loop. Pre-existente.
- **F-08 `resolver_twilio` no valida credenciales Twilio en `club`** (`router.py:_handle_twilio`): no existe check equivalente al `club.get("meta_access_token")` para Twilio. Pre-existente.
- **F-09 `inspect.iscoroutinefunction` no detecta `functools.partial(async_fn)`** (`router.py:_llamar_run_agent`): si un consumidor pasa `functools.partial(async_fn)` como `run_agent`, se corre en `asyncio.to_thread` en vez de awaited. Fix: `inspect.iscoroutinefunction(getattr(fn, 'func', fn))`.
- **F-10 `mensaje_usuario` vacío no validado antes de run_agent** (`router.py`): body vacío o mensaje sin texto se pasa a `run_agent`. Pre-existente.

## Deferred from: code review of US-EC-05-router-whatsapp-unificado (2026-05-22)

- **`enviar_mensaje` bloquea el event loop** (`agente_commons/whatsapp/meta.py:88`): usa `requests.post` (sync) dentro de handler async FastAPI. Migrar a `httpx` async o usar `asyncio.to_thread`. Pre-existente en meta.py.
- **Race condition en historial**: lectura-modificación-escritura del historial no es atómica. Si dos mensajes llegan simultáneamente al mismo `session_id`, el último `save_historial` gana y se pierde la otra vuelta. Requiere lock o estructura atómica a nivel Redis/storage.
- **multipart/form-data de Twilio routed al handler Meta**: Twilio usa `multipart/form-data` para mensajes con media (MMS/WhatsApp media). Esos requests caen al handler Meta, fallan el parse JSON y retornan "ok" silencioso. Agregar detección de `multipart/form-data`.
- **Sin validación de firma Twilio** (`router.py:_handle_twilio`): Twilio envía `X-Twilio-Signature` que debería validarse para prevenir spoofing. Hardening de seguridad, separado de esta story.
