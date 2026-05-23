# US-EC-05 · Router WhatsApp unificado en agente-commons

**Épica:** agente-commons  
**Sprint:** 2  
**Prerequisito:** US-EC-02  
**Esfuerzo estimado:** 1 día

---

## Historia

**Como** desarrollador  
**Quiero** un router unificado en `agente-commons` que detecte automáticamente si el request viene de Twilio o Meta  
**Para** que cada app exponga un único endpoint `POST /whatsapp` sin duplicar lógica de detección

---

## Contexto técnico

Twilio envía requests como `application/x-www-form-urlencoded` (form-data).  
Meta envía requests como `application/json`.

El router detecta el `Content-Type` y delega al handler correcto. Cada app pasa sus propias funciones de resolución de tenant y ejecución del agente como callbacks — el router no conoce la lógica de negocio de cada app.

---

## Diseño del router

```python
# agente_commons/whatsapp/router.py

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
from typing import Callable, Awaitable
from . import meta as wh_meta
from . import twilio_helper as wh_twilio


def create_whatsapp_router(
    app_id:          str,
    resolver_meta:   Callable[[str], dict | None],
    resolver_twilio: Callable[[str], dict | None],
    run_agent:       Callable,
    get_historial:   Callable[[str], Awaitable[list]],
    save_historial:  Callable[[str, list], Awaitable[None]],
    meta_verify_token: str = "",
    meta_app_secret:   str = "",
) -> APIRouter:
    router = APIRouter()

    @router.get("/whatsapp")
    async def whatsapp_verify(
        hub_mode:         str = Query(None, alias="hub.mode"),
        hub_verify_token: str = Query(None, alias="hub.verify_token"),
        hub_challenge:    str = Query(None, alias="hub.challenge"),
    ):
        if meta_verify_token and hub_mode == "subscribe" and hub_verify_token == meta_verify_token:
            return PlainTextResponse(hub_challenge or "", status_code=200)
        raise HTTPException(status_code=403, detail="Verificación fallida")

    @router.post("/whatsapp")
    async def whatsapp_unified(request: Request):
        content_type = request.headers.get("content-type", "")

        if "application/x-www-form-urlencoded" in content_type:
            return await _handle_twilio(request)
        else:
            return await _handle_meta(request)

    async def _handle_twilio(request: Request) -> PlainTextResponse:
        form           = await request.form()
        From           = form.get("From", "")
        To             = form.get("To", "")
        Body           = form.get("Body", "")
        numero_club    = wh_twilio.normalizar_numero(To)
        numero_jugador = wh_twilio.normalizar_numero(From)

        club = resolver_twilio(numero_club)
        if club is None:
            return wh_twilio.twiml_response(
                "Este número no está disponible. Comuníquese directamente con el club."
            )

        session_id    = wh_twilio.session_key(numero_club, numero_jugador)
        historial     = await get_historial(session_id)
        tenant_id = club["tenant_id"]
        logger.info("whatsapp_incoming | app=%s | tenant=%s | proveedor=twilio", app_id, tenant_id)
        respuesta, historial_nuevo = run_agent(
            historial       = historial,
            mensaje_usuario = Body,
            tenant_id       = tenant_id,
            tenant_params   = club,
            numero_usuario  = numero_jugador,
        )
        await save_historial(session_id, historial_nuevo)
        return wh_twilio.twiml_response(respuesta)

    async def _handle_meta(request: Request) -> PlainTextResponse:
        payload_bytes = await request.body()
        signature     = request.headers.get("X-Hub-Signature-256", "")

        if meta_app_secret and not wh_meta.verificar_firma(payload_bytes, signature, meta_app_secret):
            raise HTTPException(status_code=403, detail="Firma inválida")

        try:
            import json
            data = json.loads(payload_bytes)
        except Exception:
            return PlainTextResponse("ok", status_code=200)

        mensaje = wh_meta.parsear_mensaje(data)
        if mensaje is None:
            return PlainTextResponse("ok", status_code=200)

        phone_number_id = mensaje["phone_number_id"]
        numero_usuario  = mensaje["numero_usuario"]
        texto           = mensaje["texto"]

        club = resolver_meta(phone_number_id)
        if club is None:
            return PlainTextResponse("ok", status_code=200)

        if not club.get("meta_access_token"):
            return PlainTextResponse("ok", status_code=200)

        tenant_id  = club["tenant_id"]
        session_id = wh_meta.session_key(phone_number_id, numero_usuario)
        historial  = await get_historial(session_id)
        logger.info("whatsapp_incoming | app=%s | tenant=%s | proveedor=meta", app_id, tenant_id)
        respuesta, historial_nuevo = run_agent(
            historial       = historial,
            mensaje_usuario = texto,
            tenant_id       = tenant_id,
            tenant_params   = club,
            numero_usuario  = numero_usuario,
        )
        await save_historial(session_id, historial_nuevo)

        wh_meta.enviar_mensaje(
            phone_number_id = phone_number_id,
            numero_usuario  = numero_jugador,
            texto           = respuesta,
            access_token    = club["meta_access_token"],
        )
        return PlainTextResponse("ok", status_code=200)

    return router
```

---

## Contrato del resolver

Cada app debe devolver un dict con esta estructura:

```python
{
    "app_id":             "agente-canchas",  # identifica la app — definido por la app
    "tenant_id":          123,               # club_id, consultorio_id, etc.
    "meta_access_token":  "...",
    "mensaje_bienvenida": "...",
    "mensaje_desborde":   "...",
    "telefono_recepcion": "...",
}
```

El router pasa `app_id` y `tenant_id` a `run_agent` y los incluye en todos los logs:

```python
logger.info("whatsapp_incoming | app=%s | tenant=%s | proveedor=%s", app_id, tenant_id, proveedor)
```

### Mapeo por app

```python
# agente-canchas — resolver devuelve
{
    "app_id":    "agente-canchas",
    "tenant_id": row["club_id"],
    ...
}

# agente-turnos — resolver devuelve
{
    "app_id":    "agente-turnos",
    "tenant_id": row["consultorio_id"],
    ...
}
```

---

## Uso en agente-canchas (main.py)

```python
from agente_commons.whatsapp.router import create_whatsapp_router

whatsapp_router = create_whatsapp_router(
    app_id            = "agente-canchas",
    resolver_meta     = resolver_club_meta,
    resolver_twilio   = resolver_club_twilio,
    run_agent         = run_agent,
    get_historial     = get_historial,
    save_historial    = save_historial,
    meta_verify_token = META_VERIFY_TOKEN,
    meta_app_secret   = META_APP_SECRET,
)
app.include_router(whatsapp_router)
```

## Uso en agente-turnos (main.py)

```python
whatsapp_router = create_whatsapp_router(
    app_id            = "agente-turnos",
    resolver_meta     = resolver_consultorio_meta,
    resolver_twilio   = resolver_consultorio,
    run_agent         = run_agent,
    get_historial     = get_historial,
    save_historial    = save_historial,
    meta_verify_token = META_VERIFY_TOKEN,
    meta_app_secret   = META_APP_SECRET,
)
app.include_router(whatsapp_router)
```

**Endpoints a eliminar de main.py en cada app:**
- `GET /whatsapp`
- `POST /whatsapp`
- `POST /whatsapp-twilio`

---

## Criterios de aceptación

```gherkin
Scenario: Request de Twilio (form-data) procesado correctamente
  GIVEN un POST /whatsapp con Content-Type application/x-www-form-urlencoded
  AND campos From, To, Body de Twilio
  WHEN el router recibe el request
  THEN detecta proveedor Twilio por Content-Type
  AND ejecuta el agente con club resuelto por numero Twilio
  AND responde con TwiML

Scenario: Request de Meta (JSON) procesado correctamente
  GIVEN un POST /whatsapp con Content-Type application/json
  AND payload JSON de Meta con mensaje de texto
  WHEN el router recibe el request
  THEN detecta proveedor Meta por Content-Type
  AND ejecuta el agente con club resuelto por phone_number_id
  AND responde "ok" 200

Scenario: Status update de Meta ignorado
  GIVEN un POST /whatsapp con payload Meta sin messages
  WHEN el router lo recibe
  THEN responde "ok" 200 sin ejecutar el agente

Scenario: Firma Meta inválida rechazada
  GIVEN un POST /whatsapp con X-Hub-Signature-256 inválida
  AND META_APP_SECRET configurado
  WHEN el router lo recibe
  THEN responde 403

Scenario: Verificación webhook Meta
  GIVEN GET /whatsapp con hub.verify_token correcto
  WHEN el router lo recibe
  THEN responde con hub.challenge y 200
```

---

## Tests

```
tests/test_router.py
  — twilio_request_procesado
  — meta_request_procesado
  — meta_status_update_ignorado
  — meta_firma_invalida
  — meta_verificacion_webhook
```

---

## Notas

- El router usa el patrón factory (`create_whatsapp_router`) para recibir las dependencias de cada app sin acoplarse a ellas.
- `agente-turnos` usará el mismo router con sus propios resolvers (`resolver_consultorio_meta`, `resolver_consultorio`).
- Una vez implementado, `main.py` de `agente-canchas` queda significativamente más limpio.
