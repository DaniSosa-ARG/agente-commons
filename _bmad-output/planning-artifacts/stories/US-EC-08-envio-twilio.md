# US-EC-08 · Envío activo de respuesta en canal Twilio

**Repo:** agente-commons  
**Sprint:** 6  
**Prioridad:** Alta  
**Estado:** 🔁 review  
**Dependencias:** US-EC-05 (router unificado)  

---

## Historia

**Como** paciente que escribe por WhatsApp vía Twilio  
**Quiero** recibir la respuesta del agente en mi WhatsApp  
**Para** poder continuar la conversación normalmente

---

## Contexto

Con la adopción de agente-commons (US-29), el router Twilio pasó a usar background tasks — responde TwiML vacío inmediatamente y procesa el agente en background. Esto funciona bien para Meta que envía via API separada, pero **Twilio Sandbox no recibe la respuesta** porque:

- El TwiML vacío no envía nada al paciente
- `_procesar_twilio` procesa el agente y guarda el historial pero nunca envía la respuesta

Antes de agente-commons, el webhook era sincrónico — el agente corría en el request y la respuesta volvía en el TwiML del 200. Con background tasks eso ya no es posible, entonces hay que enviar la respuesta via Twilio API, igual que hace Meta con `wh_meta.enviar_mensaje`.

---

## Decisiones de diseño

| Decisión | Detalle |
|----------|---------|
| Simétrico a Meta | `_procesar_twilio` llama a `wh_twilio.enviar_mensaje` al final, igual que `_procesar_meta` |
| Credenciales como parámetros | `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_from` se pasan a `create_whatsapp_router` |
| Opcional | Si las credenciales no se pasan, el canal Twilio sigue funcionando sin envío activo (backward compat) |
| `enviar_mensaje` en twilio_helper | Nueva función simétrica a `wh_meta.enviar_mensaje` |
| Número destino | `numero_jugador` con prefijo `whatsapp:+` — usar `telefono_para_twilio` de agente_commons.telefono |
| Error no bloquea | Si falla el envío, loguea y continúa — no relanza excepción |
| Bump versión | `0.3.0` en `pyproject.toml` |

---

## Archivos a crear/modificar

### agente-commons
```
agente_commons/whatsapp/twilio_helper.py   ← agregar enviar_mensaje()
agente_commons/whatsapp/router.py          ← parámetros nuevos + llamada a enviar_mensaje
agente_commons/whatsapp/__init__.py        ← exportar enviar_mensaje si aplica
pyproject.toml                             ← bump versión a 0.3.0
CHANGELOG.md                               ← entrada v0.3.0
tests/test_twilio_envio.py                 ← tests nuevos
```

### agente-turnos
```
main.py   ← pasar TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM al crear el router
```

---

## Implementación

### agente_commons/whatsapp/twilio_helper.py — agregar

```python
def enviar_mensaje(
    numero_destino: str,
    texto: str,
    account_sid: str,
    auth_token: str,
    from_: str,
) -> bool:
    """
    Envía un mensaje WhatsApp via Twilio API.
    Simétrico a wh_meta.enviar_mensaje para el canal Twilio.
    numero_destino debe estar en formato normalizado (sin whatsapp: ni +).
    """
    try:
        from twilio.rest import Client
        from agente_commons.telefono import telefono_para_twilio
        client = Client(account_sid, auth_token)
        client.messages.create(
            from_=from_,
            to=telefono_para_twilio(numero_destino),
            body=texto,
        )
        return True
    except Exception as e:
        logger.error("twilio_enviar_mensaje_error | error=%s", str(e))
        return False
```

### agente_commons/whatsapp/router.py — modificar create_whatsapp_router

```python
def create_whatsapp_router(
    app_id:              str,
    resolver_meta:       Callable[[str], dict | None],
    resolver_twilio:     Callable[[str], dict | None],
    run_agent:           Callable,
    get_historial:       Callable[[str], Awaitable[list]],
    save_historial:      Callable[[str, list], Awaitable[None]],
    meta_verify_token:   str = "",
    meta_app_secret:     str = "",
    # Nuevos parámetros opcionales para envío activo Twilio
    twilio_account_sid:  str = "",
    twilio_auth_token:   str = "",
    twilio_whatsapp_from: str = "",
) -> APIRouter:
```

Y en `_procesar_twilio`, agregar al final:

```python
        # Envío activo de respuesta (simétrico a Meta)
        if twilio_account_sid and twilio_auth_token and twilio_whatsapp_from:
            ok = wh_twilio.enviar_mensaje(
                numero_destino = numero_jugador,
                texto          = _respuesta,
                account_sid    = twilio_account_sid,
                auth_token     = twilio_auth_token,
                from_          = twilio_whatsapp_from,
            )
            if not ok:
                logger.error(
                    "enviar_mensaje_twilio_failed | app=%s | tenant=%s | numero=%s",
                    app_id, tenant_id, numero_jugador,
                )
```

### main.py en agente-turnos — modificar

```python
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM

whatsapp_router = create_whatsapp_router(
    app_id               = "agente-turnos",
    resolver_meta        = _wrap_con_metrica(resolver_consultorio_meta,   "meta"),
    resolver_twilio      = _wrap_con_metrica(resolver_consultorio_twilio, "twilio"),
    run_agent            = _run_agent_adapter,
    get_historial        = get_historial,
    save_historial       = save_historial,
    meta_verify_token    = META_VERIFY_TOKEN,
    meta_app_secret      = META_APP_SECRET,
    twilio_account_sid   = TWILIO_ACCOUNT_SID  or "",
    twilio_auth_token    = TWILIO_AUTH_TOKEN   or "",
    twilio_whatsapp_from = TWILIO_WHATSAPP_FROM or "",
)
```

---

## Criterios de aceptación

```gherkin
Scenario: Paciente recibe respuesta del agente por Twilio
  GIVEN un paciente que escribe por WhatsApp vía Twilio Sandbox
  WHEN el agente procesa el mensaje y genera una respuesta
  THEN el paciente recibe el mensaje en su WhatsApp
  AND los logs muestran "BEGIN Twilio API Request" después del procesamiento

Scenario: Error de envío no rompe el flujo
  GIVEN Twilio API falla al enviar la respuesta
  WHEN _procesar_twilio intenta enviar
  THEN loguea el error con "enviar_mensaje_twilio_failed"
  AND no lanza excepción
  AND el historial se guardó correctamente

Scenario: Sin credenciales Twilio no intenta enviar
  GIVEN twilio_account_sid="" (no configurado)
  WHEN _procesar_twilio termina de procesar
  THEN no llama a wh_twilio.enviar_mensaje
  AND no lanza excepción

Scenario: Número destino en formato correcto
  GIVEN numero_jugador="5491158530263" (normalizado por normalizar_numero)
  WHEN enviar_mensaje construye el "to"
  THEN usa telefono_para_twilio → "whatsapp:+5491158530263"

Scenario: Backward compat — router sin credenciales Twilio funciona igual
  GIVEN create_whatsapp_router sin parámetros twilio_*
  WHEN llega un mensaje Twilio
  THEN procesa normalmente sin envío activo
  AND no rompe
```

---

## Tests

### tests/test_twilio_envio.py (en agente-commons)

| Test | Objetivo |
|------|----------|
| `test_ec08_enviar_mensaje_twilio_exitoso` | Llama a Twilio API con parámetros correctos |
| `test_ec08_enviar_mensaje_twilio_formato_numero` | `to` = `whatsapp:+549...` |
| `test_ec08_enviar_mensaje_twilio_error_no_relanza` | Fallo → `False`, no excepción |
| `test_ec08_procesar_twilio_llama_enviar_mensaje` | `_procesar_twilio` llama a `enviar_mensaje` con la respuesta del agente |
| `test_ec08_procesar_twilio_sin_credenciales_no_envia` | Sin SID → no llama a `enviar_mensaje` |

---

## Orden de implementación

| Paso | Repo | Qué hacer |
|------|------|-----------|
| 1 | agente-commons | Agregar `enviar_mensaje` en `twilio_helper.py` |
| 2 | agente-commons | Actualizar `create_whatsapp_router` con parámetros nuevos |
| 3 | agente-commons | Agregar llamada a `enviar_mensaje` en `_procesar_twilio` |
| 4 | agente-commons | Crear `tests/test_twilio_envio.py` — pytest verde |
| 5 | agente-commons | Bump versión a `0.3.0` + CHANGELOG |
| 6 | agente-commons | `git push` |
| 7 | agente-turnos | Actualizar `pip install agente-commons` |
| 8 | agente-turnos | Actualizar `main.py` con parámetros nuevos |
| 9 | agente-turnos | `pytest tests/ -v` — 443+ tests en verde |
| 10 | agente-turnos | `git push` → Railway rebuild |
| 11 | — | Test manual: escribir "Hola" por Twilio → recibir respuesta |

---

## Dev Agent Record

### Notas de implementación (agente-commons)

**Implementado el 2026-06-14:**

- Agregada `enviar_mensaje()` en `agente_commons/whatsapp/twilio_helper.py`:
  - Importa `Client` a nivel de módulo (facilita mocking en tests)
  - Importa `telefono_para_twilio` de `agente_commons.telefono` (US-EC-07)
  - Retorna `True`/`False` — nunca relanza excepción
- Actualizados parámetros de `create_whatsapp_router` en `router.py`:
  - Nuevos parámetros opcionales: `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_from`
  - Backward compat: sin credenciales el comportamiento anterior se mantiene
- `_procesar_twilio` llama a `enviar_mensaje` al finalizar (simétrico a `_procesar_meta`)
- Bump versión `0.2.0 → 0.3.0` en `pyproject.toml` y `__init__.py`
- Suite completa: **31/31 tests pasan**, sin regresiones

**Nota de implementación:** El spec original tenía `from twilio.rest import Client` dentro de la función. Se movió a nivel de módulo para que `patch("agente_commons.whatsapp.twilio_helper.Client")` funcione en los tests.

**Pendiente (agente-turnos — repo separado):** pasos 7-11.

### File List

```
agente_commons/whatsapp/twilio_helper.py   ← MODIFICADO (enviar_mensaje + imports)
agente_commons/whatsapp/router.py          ← MODIFICADO (params nuevos + llamada enviar_mensaje)
agente_commons/__init__.py                 ← MODIFICADO (versión 0.3.0)
tests/test_twilio_envio.py                 ← NUEVO (5 tests)
pyproject.toml                             ← MODIFICADO (versión 0.3.0)
CHANGELOG.md                               ← MODIFICADO (entrada v0.3.0)
```

### Change Log

- 2026-06-14: US-EC-08 — envío activo Twilio implementado; versión bumpeada a 0.3.0

## Review Findings

- [x] [Review][Defer] Consumer app wiring is outside this repo — Wiring de credenciales Twilio en main.py de agente-turnos: pasar `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_from` a `create_whatsapp_router` para activar envío activo US-EC-08. Deferido porque este review está acotado a `agente-commons` y el wiring vive en el repo consumidor. [deferred]
- [x] [Review][Patch] Twilio reply destination is double-prefixed [agente_commons/whatsapp/router.py:132]
- [x] [Review][Patch] Twilio API send blocks inside async background task [agente_commons/whatsapp/router.py:131]
- [x] [Review][Defer] Full phone number is logged on Twilio send failure [agente_commons/whatsapp/router.py:140] — deferred, follows existing logging pattern also present in Meta send failure logging.
