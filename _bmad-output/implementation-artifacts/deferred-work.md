# Deferred Work

## Deferred from: code review of US-EC-05-router-whatsapp-unificado (2026-05-22)

- **`enviar_mensaje` bloquea el event loop** (`agente_commons/whatsapp/meta.py:88`): usa `requests.post` (sync) dentro de handler async FastAPI. Migrar a `httpx` async o usar `asyncio.to_thread`. Pre-existente en meta.py.
- **Race condition en historial**: lectura-modificación-escritura del historial no es atómica. Si dos mensajes llegan simultáneamente al mismo `session_id`, el último `save_historial` gana y se pierde la otra vuelta. Requiere lock o estructura atómica a nivel Redis/storage.
- **multipart/form-data de Twilio routed al handler Meta**: Twilio usa `multipart/form-data` para mensajes con media (MMS/WhatsApp media). Esos requests caen al handler Meta, fallan el parse JSON y retornan "ok" silencioso. Agregar detección de `multipart/form-data`.
- **Sin validación de firma Twilio** (`router.py:_handle_twilio`): Twilio envía `X-Twilio-Signature` que debería validarse para prevenir spoofing. Hardening de seguridad, separado de esta story.
