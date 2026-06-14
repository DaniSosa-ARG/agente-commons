# Fragmentos para agregar manualmente

---

## 1. STORIES.md de agente-commons — agregar como nueva historia

---

### US-EC-08 · Envío activo de respuesta en canal Twilio

**Prioridad:** Alta
**Módulo:** agente-commons · whatsapp
**Dependencias:** US-EC-05

**Como** paciente que escribe por WhatsApp vía Twilio
**Quiero** recibir la respuesta del agente en mi WhatsApp
**Para** poder continuar la conversación normalmente

**Contexto:** Con background tasks, `_procesar_twilio` procesa el agente pero nunca envía
la respuesta. A diferencia de Meta que llama a `wh_meta.enviar_mensaje`, el canal Twilio
no tenía equivalente. Esta historia lo implementa simétricamente.

**Decisiones de diseño:**

| Decisión | Detalle |
|----------|---------|
| Simétrico a Meta | `_procesar_twilio` llama a `wh_twilio.enviar_mensaje` al final |
| Credenciales como parámetros | `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_from` en `create_whatsapp_router` |
| Opcional/backward compat | Sin credenciales → no envía, no rompe |
| Bump versión | `0.3.0` |

**Criterios de aceptación:**

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
  GIVEN numero_jugador="5491158530263"
  WHEN enviar_mensaje construye el "to"
  THEN usa telefono_para_twilio → "whatsapp:+5491158530263"

Scenario: Backward compat — router sin credenciales Twilio funciona igual
  GIVEN create_whatsapp_router sin parámetros twilio_*
  WHEN llega un mensaje Twilio
  THEN procesa normalmente sin envío activo
  AND no rompe
```
Estado: 🔲 pendiente

---

## 2. sprint-status.yaml de agente-commons — agregar en sprint 6

  - id: US-EC-08
    title: Envío activo de respuesta en canal Twilio
    status: backlog
    repo: agente-commons
    depends_on: [US-EC-05]
    notes: "Simétrico a Meta. Parámetros twilio_* en create_whatsapp_router. Bump 0.3.0."
