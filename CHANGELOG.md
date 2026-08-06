# Changelog

## [0.4.0] — Agosto 2026

- US-EC-09: `parsear_mensaje()` reconoce mensajes `interactive.type="list_reply"`
  (paciente tocó una fila de un mensaje de lista interactiva de Meta)
  - Aditivo — el branch de mensajes de texto no cambia, `_procesar_meta`/`_handle_meta`
    no requieren ningún cambio
  - Devuelve el mismo shape de dict que para texto (`phone_number_id`,
    `numero_usuario`, `texto`) — el consumidor no necesita saber que es un list_reply
  - `id` y `title` del row elegido viajan codificados en `texto`, separados por el
    nuevo marker exportado `LIST_REPLY_MARKER` (`agente_commons.whatsapp.meta`)
  - Tipos de `interactive` distintos a `list_reply` (ej. `button_reply`) se ignoran
    igual que un tipo de mensaje no soportado — se loguea y se devuelve `None`
  - Bloqueante de US-55 en `agente-turnos` (selección de motivo por lista interactiva)

## [0.3.0] — Junio 2026

- US-EC-08: Envío activo de respuesta en canal Twilio (`twilio_helper.enviar_mensaje`)
  - `create_whatsapp_router` acepta `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_from`
  - `_procesar_twilio` envía la respuesta del agente via Twilio API (simétrico a Meta)
  - Sin credenciales configuradas, el comportamiento anterior se mantiene (backward compat)

## [0.2.0] — Junio 2026

- US-EC-07: Módulo `agente_commons/telefono.py` con normalización centralizada de teléfonos
  - `normalizar_telefono_bd`: convierte cualquier formato al dígito local sin código país ni prefijo 9
  - `telefono_para_twilio`: formatea para Twilio WhatsApp (`whatsapp:+549...`)
  - `telefono_para_meta`: formatea para Meta Graph API (`549...`)

## [0.1.0] — Mayo 2026

- Estructura inicial del paquete
