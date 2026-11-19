# agente-commons

Paquete privado con infraestructura compartida para agentes WhatsApp.

## Instalación

```bash
pip install git+https://github.com/DaniSosa-ARG/agente-commons.git@main
```

## Contenido

- `agente_commons.whatsapp.meta` — Meta Cloud API
- `agente_commons.whatsapp.twilio` — Twilio WhatsApp

## Firma de webhooks (desde 0.5.0)

`create_whatsapp_router` exige firma válida en todo POST `/whatsapp`
(`exigir_firma=True` por defecto):

| Proveedor | Header | Secreto |
|---|---|---|
| Meta | `X-Hub-Signature-256` | `meta_app_secret` |
| Twilio | `X-Twilio-Signature` | `twilio_auth_token` |

Sin firma válida → 403. Sin el secreto configurado, todos los POST de ese proveedor se
rechazan. Detrás de un proxy que termina TLS, pasar `twilio_webhook_url` con la URL pública
exacta configurada en Twilio (o asegurar que el proxy envíe `X-Forwarded-Proto`/`X-Forwarded-Host`).

## Respuesta omitida (desde 0.6.0)

`run_agent` devuelve `(respuesta, historial_nuevo)`. Si `respuesta` es `None`, el router guarda
el historial y no envía ningún mensaje. Sirve para que la app decida no contestar (por ejemplo,
un remitente que superó un límite). Un string vacío se sigue enviando.
