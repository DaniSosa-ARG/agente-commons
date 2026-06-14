# Changelog

## [0.2.0] — Junio 2026

- US-EC-07: Módulo `agente_commons/telefono.py` con normalización centralizada de teléfonos
  - `normalizar_telefono_bd`: convierte cualquier formato al dígito local sin código país ni prefijo 9
  - `telefono_para_twilio`: formatea para Twilio WhatsApp (`whatsapp:+549...`)
  - `telefono_para_meta`: formatea para Meta Graph API (`549...`)

## [0.1.0] — Mayo 2026

- Estructura inicial del paquete
