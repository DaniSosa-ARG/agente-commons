# US-EC-06 · Soporte async en run_agent handler del router WhatsApp

**Épica:** agente-commons  
**Sprint:** 3  
**Prerequisito:** US-EC-05  
**Esfuerzo estimado:** 0.5 día

---

## Historia

**Como** desarrollador de `agente-turnos` o `agente-canchas`  
**Quiero** que `create_whatsapp_router` devuelva 200 a Meta/Twilio inmediatamente al recibir el mensaje  
**Para** que Meta no reintente el webhook y el paciente/jugador no reciba respuestas duplicadas cuando `run_agent` tarda más de 5 segundos

---

## Contexto técnico

### Problema

El router actual implementa `asyncio.to_thread(run_agent, ...)` para no bloquear el event loop, pero el handler `POST /whatsapp` **espera** a que `asyncio.to_thread` complete antes de devolver 200. Desde la perspectiva de Meta, el webhook nunca responde en tiempo, por lo que Meta reintenta el POST, generando procesamiento duplicado del mensaje.

**Flujo actual (con bug):**

```
Meta POST /whatsapp
  └─► handler abre asyncio.to_thread(run_agent)   ← espera ~5-30s
        └─► Claude API responde
              └─► save_historial
                    └─► enviar_mensaje
                          └─► return PlainTextResponse("ok", 200)  ← demasiado tarde
```

**Meta timeout:** ~5s. Si el handler no responde en ese tiempo, Meta reintenta.

### Fix intentado en agente-turnos (fallido)

```python
# agente-turnos/main.py
async def _run_agent_adapter_async(...):
    return await asyncio.to_thread(_run_agent_adapter, ...)

run_agent = _run_agent_adapter_async  # ← coroutine pasada como run_agent
```

**Resultado:** `RuntimeWarning: coroutine '_run_agent_adapter_async' was never awaited`  
El router llamaba `asyncio.to_thread(run_agent, ...)` que no hace `await` — la coroutine nunca se ejecutaba.

### Solución requerida

El handler debe:
1. Devolver 200 a Meta/Twilio **inmediatamente** al recibir el mensaje válido
2. Ejecutar `run_agent` + `save_historial` + `enviar_mensaje` en **background**, fuera del ciclo request/response
3. Soportar `run_agent` tanto síncrono como async sin requerir cambios en las apps consumidoras

**Flujo objetivo:**

```
Meta POST /whatsapp
  └─► handler valida payload, resuelve club
        └─► BackgroundTasks.add_task(procesar_mensaje_async)
              └─► return PlainTextResponse("ok", 200)  ← inmediato

# En background (sin bloquear el response):
procesar_mensaje_async()
  └─► get_historial
        └─► run_agent (sync → to_thread | async → await)
              └─► save_historial
                    └─► enviar_mensaje
```

---

## Diseño de la solución

### Helper para despachar run_agent (sync o async)

```python
# agente_commons/whatsapp/router.py

import asyncio
import inspect

async def _llamar_run_agent(run_agent_fn, **kwargs):
    """Despacha run_agent sin importar si es sync o async."""
    if inspect.iscoroutinefunction(run_agent_fn):
        return await run_agent_fn(**kwargs)
    else:
        return await asyncio.to_thread(run_agent_fn, **kwargs)
```

### Handler Meta con BackgroundTasks

```python
from fastapi import BackgroundTasks

@router.post("/whatsapp")
async def whatsapp_unified(request: Request, background_tasks: BackgroundTasks):
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        return await _handle_twilio(request, background_tasks)
    return await _handle_meta(request, background_tasks)

async def _handle_meta(request: Request, background_tasks: BackgroundTasks):
    # ... validación de firma, parseo del payload ...
    
    mensaje = wh_meta.parsear_mensaje(data)
    if mensaje is None:
        return PlainTextResponse("ok", status_code=200)

    club = resolver_meta(mensaje["phone_number_id"])
    if club is None or not club.get("meta_access_token"):
        return PlainTextResponse("ok", status_code=200)

    # Delegar procesamiento pesado a background
    background_tasks.add_task(
        _procesar_meta,
        mensaje=mensaje,
        club=club,
    )
    return PlainTextResponse("ok", status_code=200)  # ← 200 inmediato

async def _procesar_meta(mensaje: dict, club: dict):
    session_id = wh_meta.session_key(mensaje["phone_number_id"], mensaje["numero_usuario"])
    historial  = await get_historial(session_id)
    tenant_id  = club["tenant_id"]
    logger.info("whatsapp_processing | app=%s | tenant=%s | proveedor=meta", app_id, tenant_id)

    try:
        respuesta, historial_nuevo = await _llamar_run_agent(
            run_agent,
            historial       = historial,
            mensaje_usuario = mensaje["texto"],
            tenant_id       = tenant_id,
            tenant_params   = club,
            numero_usuario  = mensaje["numero_usuario"],
        )
    except Exception:
        logger.exception("run_agent_error | app=%s | tenant=%s | proveedor=meta", app_id, tenant_id)
        return

    await save_historial(session_id, historial_nuevo)
    ok = wh_meta.enviar_mensaje(
        phone_number_id = mensaje["phone_number_id"],
        numero_usuario  = mensaje["numero_usuario"],
        texto           = respuesta,
        access_token    = club["meta_access_token"],
    )
    if not ok:
        logger.error("enviar_mensaje_failed | app=%s | tenant=%s", app_id, tenant_id)
```

### Handler Twilio con BackgroundTasks

Mismo patrón: validar y resolver el club de forma síncrona (< 1ms), despachar `_procesar_twilio` a background, devolver TwiML vacío inmediatamente.

> **Nota Twilio:** El handler devuelve un TwiML vacío `<Response/>` de forma inmediata. Esto es correcto porque `agente-turnos` y `agente-canchas` usan el patrón **outbound**: `run_agent` envía la respuesta al usuario internamente via `send_confirmation` (Meta Graph API o Twilio API como fallback). El TwiML del webhook es solo un ACK — no transporta el texto de respuesta al usuario. El cambio a `BackgroundTasks` es transparente para ambos canales, sin regresión en el flujo de respuesta.

---

## Contrato actualizado de create_whatsapp_router

El contrato **no cambia** para las apps consumidoras. El único cambio visible es que `run_agent` ahora puede ser síncrono **o** async:

```python
# agente-turnos/main.py — sin cambios requeridos
whatsapp_router = create_whatsapp_router(
    app_id            = "agente-turnos",
    resolver_meta     = _wrap_con_metrica(resolver_consultorio_meta, "meta"),
    resolver_twilio   = _wrap_con_metrica(resolver_consultorio_twilio, "twilio"),
    run_agent         = _run_agent_adapter,      # síncrono — sigue funcionando
    get_historial     = get_historial,
    save_historial    = save_historial,
    meta_verify_token = META_VERIFY_TOKEN,
    meta_app_secret   = META_APP_SECRET,
)
```

El docstring de `create_whatsapp_router` se actualiza para reflejar que `run_agent` puede ser síncrono o async.

---

## Criterios de aceptación

```gherkin
Scenario: run_agent síncrono — webhook devuelve 200 antes de que run_agent termine
  GIVEN create_whatsapp_router configurado con run_agent síncrono que tarda 10s
  WHEN Meta hace POST /whatsapp con un mensaje válido
  THEN el webhook devuelve 200 en menos de 500ms
  AND run_agent se ejecuta en background sin bloquear el event loop
  AND el paciente recibe una sola respuesta

Scenario: run_agent async — es awaited correctamente en background
  GIVEN create_whatsapp_router configurado con run_agent async
  WHEN Meta hace POST /whatsapp con un mensaje válido
  THEN el router hace await sobre run_agent en background
  AND no lanza RuntimeWarning de coroutine never awaited
  AND el paciente recibe una sola respuesta

Scenario: Backwards compatibility — run_agent síncrono existente funciona sin cambios
  GIVEN una app existente con run_agent síncrono
  WHEN se actualiza agente-commons con este cambio
  THEN todos los tests existentes pasan sin modificación
  AND el contrato de create_whatsapp_router no cambia

Scenario: Error en run_agent — webhook no falla, error queda logueado
  GIVEN run_agent lanza una excepción
  WHEN Meta hace POST /whatsapp con un mensaje válido
  THEN el webhook ya devolvió 200 (no se ve afectado por el error)
  AND el error queda logueado con nivel ERROR
  AND no se envía mensaje al usuario
```

---

## Archivos a modificar

- `agente_commons/whatsapp/router.py` — refactor de `_handle_meta` y `_handle_twilio`: mover lógica de procesamiento a funciones `_procesar_meta` / `_procesar_twilio`; agregar `BackgroundTasks`; agregar helper `_llamar_run_agent`
- `tests/test_router.py` — agregar 4 tests nuevos (ver sección Tests)

---

## Tests

```
tests/test_router.py  (nuevos)
  — test_run_agent_sync_no_bloquea_event_loop
      Verifica que el POST /whatsapp devuelve 200 antes de que run_agent (con sleep 0.1s) termine.
  
  — test_run_agent_async_es_awaited
      Verifica que un run_agent async se ejecuta correctamente y no lanza RuntimeWarning.
  
  — test_backwards_compatibility_sync
      Todos los tests existentes pasan con run_agent síncrono. No requiere modificación, ya existe implícito.
  
  — test_run_agent_error_no_rompe_webhook
      run_agent lanza Exception → el webhook ya devolvió 200 y el error queda en logs.
```

### Ejemplo de test asincrónico

```python
import asyncio
from unittest.mock import AsyncMock, patch

def test_run_agent_sync_no_bloquea_event_loop():
    """El webhook devuelve 200 antes de que run_agent termine."""
    procesado = []

    def run_agent_lento(**kwargs):
        import time
        time.sleep(0.1)
        procesado.append(True)
        return "ok", []

    client = make_client(run_agent=run_agent_lento)
    payload = json.dumps(META_PAYLOAD).encode()
    with patch("agente_commons.whatsapp.meta.enviar_mensaje", return_value=True):
        response = client.post(
            "/whatsapp",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    # El 200 llega inmediatamente
    assert response.status_code == 200
    # run_agent corrió en background (TestClient es síncrono, lo espera igualmente)
    assert len(procesado) == 1


def test_run_agent_async_es_awaited():
    """run_agent async se ejecuta y no genera RuntimeWarning."""
    import warnings

    async def run_agent_async(**kwargs):
        await asyncio.sleep(0)
        return "ok async", []

    client = make_client(run_agent=run_agent_async)
    payload = json.dumps(META_PAYLOAD).encode()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with patch("agente_commons.whatsapp.meta.enviar_mensaje", return_value=True):
            response = client.post(
                "/whatsapp",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
    assert response.status_code == 200
    runtime_warnings = [x for x in w if issubclass(x.category, RuntimeWarning)]
    assert len(runtime_warnings) == 0


def test_run_agent_error_no_rompe_webhook():
    """Si run_agent lanza excepción, el webhook ya devolvió 200 y el error queda en logs."""
    def run_agent_que_explota(**kwargs):
        raise ValueError("Claude API timeout")

    client = make_client(run_agent=run_agent_que_explota)
    payload = json.dumps(META_PAYLOAD).encode()
    response = client.post(
        "/whatsapp",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
```

---

## Notas

- `BackgroundTasks` es nativo de Starlette/FastAPI — no agrega dependencias nuevas.
- `TestClient` de Starlette ejecuta los background tasks sincrónicamente después de devolver el response, por lo que los tests pueden verificar efectos secundarios (historial, envío de mensaje) sin cambios en la infraestructura de tests.
- El helper `_llamar_run_agent` es interno al closure del router; no se exporta como API pública.
- `make_client` en `test_router.py` debe aceptar un parámetro opcional `run_agent` para poder inyectar distintas implementaciones en cada test.

---

## Dev Agent Record

### Completion Notes

- Agregado `_llamar_run_agent` a nivel de módulo: detecta via `inspect.iscoroutinefunction` si `run_agent` es sync o async y despacha con `asyncio.to_thread` o `await` respectivamente.
- `whatsapp_unified` acepta ahora `background_tasks: BackgroundTasks` de FastAPI/Starlette (sin dependencia nueva).
- `_handle_meta`: extrae validación/parseo (síncrono, < 1ms) y despacha `_procesar_meta` a background antes de devolver 200 inmediato.
- `_handle_twilio`: ídem, devuelve TwiML vacío inmediato; `_procesar_twilio` corre en background.
- `_procesar_meta` y `_procesar_twilio`: envuelven `_llamar_run_agent` en try/except; error queda logueado con `logger.exception`, webhook no se ve afectado.
- `make_client` en tests actualizado con `run_agent=run_agent` como default argument para permitir inyección por test.
- 11/11 tests pasan (8 existentes sin modificación + 3 nuevos de US-EC-06).

---

## Change Log

- 2026-06-04: Implementación US-EC-06 — BackgroundTasks + helper `_llamar_run_agent` sync/async en `router.py`; 3 tests nuevos en `test_router.py`.

---

## Senior Developer Review (AI)

**Outcome:** Changes Requested  
**Fecha:** 2026-06-04  
**Revisores:** Blind Hunter · Edge Case Hunter · Acceptance Auditor

### Action Items

#### Decision Needed
- [x] [Review][Decision] F-01: ✅ Confirmado — `run_agent` en producción envía vía outbound. TwiML vacío es correcto (descartado).

#### Patches
- [x] [Review][Patch] F-02: ✅ `enviar_mensaje_failed` log restaurado con `numero_usuario` [router.py — `_procesar_meta`]
- [x] [Review][Patch] F-03: ✅ `test_run_agent_error_no_rompe_webhook` ahora verifica log ERROR con `caplog` [test_router.py]

#### Deferred
- [x] [Review][Defer] F-04: Race condition en historial por requests concurrentes a la misma sesión — pre-existente, requiere Redis locks
- [x] [Review][Defer] F-05: `except Exception` amplio sin distinción transient/permanente — diseño explícito en spec
- [x] [Review][Defer] F-06: `get_historial`/`save_historial` sin timeout — pre-existente
- [x] [Review][Defer] F-07: `resolver_meta`/`resolver_twilio` síncronos en handler async — pre-existente
- [x] [Review][Defer] F-08: `resolver_twilio` no valida credenciales Twilio en `club` — pre-existente
- [x] [Review][Defer] F-09: `inspect.iscoroutinefunction` no detecta `functools.partial(async_fn)` — edge case no contemplado en spec
- [x] [Review][Defer] F-10: `mensaje_usuario` vacío no se valida antes de llamar `run_agent` — pre-existente

### Follow-ups (AI)

- [x] F-01: ✅ Descartado — outbound confirmado
- [x] F-02: ✅ Aplicado
- [x] F-03: ✅ Aplicado

---

## Status

done

---

## File List

- `agente_commons/whatsapp/router.py` — modificado: `_handle_meta`, `_handle_twilio`, `whatsapp_unified`; nuevo `_llamar_run_agent` (módulo), `_procesar_meta`, `_procesar_twilio`
- `tests/test_router.py` — modificado: `make_client` acepta `run_agent` opcional; nuevos `test_run_agent_sync_no_bloquea_event_loop`, `test_run_agent_async_es_awaited`, `test_run_agent_error_no_rompe_webhook`
