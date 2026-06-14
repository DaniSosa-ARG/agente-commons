# Changelog

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
