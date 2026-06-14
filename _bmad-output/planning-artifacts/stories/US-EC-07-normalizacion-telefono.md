# US-EC-07 · Normalización de teléfono centralizada en agente-commons

**Repo:** agente-commons  
**Sprint:** 6  
**Prioridad:** Alta  
**Estado:** 🔁 review  
**Dependencias:** US-06, US-20, US-27  

---

## Historia

**Como** desarrollador del sistema  
**Quiero** que la lógica de normalización de teléfono esté centralizada en agente-commons  
**Para** que todos los repos usen el mismo formato sin duplicar código ni introducir bugs por inconsistencias

---

## Contexto

Durante el testing del consultorio 1 (Twilio sandbox) se detectó que:

- El teléfono se guardaba en BD con código de país y prefijo celular incluidos (`5491158530263`)
- `notifications.py` agregaba `+549` → construía `whatsapp:+5495491158530263` (duplicado)
- El mensaje salía con 201 pero no llegaba al destinatario

La causa raíz es que no existe una convención única de formato de teléfono. Cada punto de entrada
(alta manual, autoregistro WhatsApp, edición) puede guardar el número en formato distinto, y cada
canal de salida (Twilio, Meta) tiene sus propios requisitos de formato.

**Formato definido:**

| Contexto | Formato | Ejemplo |
|----------|---------|---------|
| BD (almacenamiento) | Solo número local — sin código de país ni prefijo 9 | `1158530263` |
| Twilio | `whatsapp:+549` + número local | `whatsapp:+5491158530263` |
| Meta Graph API | `549` + número local (sin `+`) | `5491158530263` |

---

## Decisiones de diseño

| Decisión | Detalle |
|----------|---------|
| Módulo nuevo | `agente_commons/telefono.py` — mismo nivel que `whatsapp/` |
| Formato BD | Solo dígitos locales sin código de país ni prefijo 9: `1158530263` |
| Formato Twilio | `whatsapp:+549` + número local |
| Formato Meta | `549` + número local (sin `+`) |
| Normalización entrada | Elimina `+`, espacios, guiones; saca `549` o `54`; saca el `9` de prefijo celular si corresponde |
| Detección prefijo 9 | Solo se saca si el número resultante tiene 11 dígitos (9 + 10 dígitos locales) |
| País | Argentina (`+54`) hardcodeado por ahora — extensible a futuro |
| Autoregistro US-27 | `register_patient_service` ya normaliza eliminando `+` y espacios — reemplazar por `normalizar_telefono_bd` |
| Alta manual panel | `routers/admin/pacientes.py` debe aplicar `normalizar_telefono_bd` al guardar |
| Edición de paciente | Idem alta manual |

---

## Archivos a crear/modificar

### agente-commons
```
agente_commons/telefono.py          ← módulo nuevo con las 3 funciones
agente_commons/__init__.py          ← exportar módulo telefono
tests/test_telefono.py              ← tests unitarios (sin BD, sin mocks)
pyproject.toml                      ← bump versión a 0.2.0
CHANGELOG.md                        ← entrada v0.2.0
```

### agente-turnos
```
tools/notifications.py              ← send_confirmation_meta: usar telefono_para_meta
                                       send_confirmation (Twilio): usar telefono_para_twilio
services/patient_service.py         ← register_patient_service: usar normalizar_telefono_bd
routers/admin/pacientes.py          ← POST y PUT /admin/pacientes: usar normalizar_telefono_bd
routers/admin/turnos.py             ← eliminar print [DEBUG] con PII (línea 165)
tests/test_us39_normalizacion_telefono.py  ← tests de integración en agente-turnos
```

---

## Implementación

### agente_commons/telefono.py

```python
"""
US-EC-07: Normalización centralizada de números de teléfono.
País: Argentina (+54). Extensible a futuro.

Formato BD: solo dígitos locales sin código de país ni prefijo 9.
  Ejemplo: "1158530263" (10 dígitos)

Twilio necesita el prefijo 9 de celular → se agrega al formatear.
Meta necesita el número completo sin '+' → se agrega al formatear.
"""


def normalizar_telefono_bd(telefono: str) -> str:
    """
    Convierte cualquier formato de entrada al formato de almacenamiento en BD:
    dígitos locales sin código de país ni prefijo 9 de celular.

    Ejemplos:
      "+5491158530263"     → "1158530263"
      "5491158530263"      → "1158530263"
      "541158530263"       → "1158530263"
      "91158530263"        → "1158530263"  (solo prefijo 9, sin código país)
      "1158530263"         → "1158530263"  (ya normalizado)
      "+54 9 11-5853-0263" → "1158530263"
    """
    t = telefono.replace("+", "").replace(" ", "").replace("-", "")
    if t.startswith("549"):
        t = t[3:]       # saca 549
    elif t.startswith("54"):
        t = t[2:]       # saca 54
    # Saca el 9 de prefijo celular si el número resultante tiene 11 dígitos
    if t.startswith("9") and len(t) == 11:
        t = t[1:]
    return t


def telefono_para_twilio(telefono: str) -> str:
    """
    Convierte número normalizado (BD) al formato requerido por Twilio WhatsApp.
    Twilio necesita el prefijo 9 de celular argentino.
    "1158530263" → "whatsapp:+5491158530263"
    """
    return f"whatsapp:+549{telefono}"


def telefono_para_meta(telefono: str) -> str:
    """
    Convierte número normalizado (BD) al formato requerido por Meta Graph API.
    Meta espera el número completo sin '+'.
    "1158530263" → "5491158530263"
    """
    return f"549{telefono}"
```

### agente_commons/__init__.py — agregar

```python
from . import telefono
```

### Cambios en notifications.py

```python
from agente_commons.telefono import telefono_para_twilio, telefono_para_meta

# En send_confirmation_meta — reemplazar:
"to": telefono
# Por:
"to": telefono_para_meta(telefono)

# En send_confirmation (Twilio) — reemplazar:
to=f"whatsapp:+54{telefono.replace('-', '').replace(' ', '')}"
# Por:
to=telefono_para_twilio(telefono)
```

### Cambios en patient_service.py

```python
from agente_commons.telefono import normalizar_telefono_bd

# En register_patient_service — reemplazar:
telefono_normalizado = telefono.replace("+", "").replace(" ", "")
# Por:
telefono_normalizado = normalizar_telefono_bd(telefono)
```

### Cambios en routers/admin/pacientes.py

```python
from agente_commons.telefono import normalizar_telefono_bd

# En POST /admin/pacientes y PUT /admin/pacientes/{id}
# Al guardar el teléfono:
telefono = normalizar_telefono_bd(body.telefono) if body.telefono else None
```

---

## Criterios de aceptación

```gherkin
Scenario: Normalizar número completo con +549
  GIVEN telefono="+5491158530263"
  WHEN normalizar_telefono_bd(telefono)
  THEN devuelve "1158530263"

Scenario: Normalizar número con 549 sin +
  GIVEN telefono="5491158530263"
  WHEN normalizar_telefono_bd(telefono)
  THEN devuelve "1158530263"

Scenario: Normalizar número con 54 sin prefijo 9
  GIVEN telefono="541158530263"
  WHEN normalizar_telefono_bd(telefono)
  THEN devuelve "1158530263"

Scenario: Normalizar número con solo prefijo 9 (sin código país)
  GIVEN telefono="91158530263"
  WHEN normalizar_telefono_bd(telefono)
  THEN devuelve "1158530263"

Scenario: Número ya normalizado — no modifica
  GIVEN telefono="1158530263"
  WHEN normalizar_telefono_bd(telefono)
  THEN devuelve "1158530263"

Scenario: Número con espacios y guiones
  GIVEN telefono="+54 9 11-5853-0263"
  WHEN normalizar_telefono_bd(telefono)
  THEN devuelve "1158530263"

Scenario: Formato Twilio agrega +549
  GIVEN telefono="1158530263"
  WHEN telefono_para_twilio(telefono)
  THEN devuelve "whatsapp:+5491158530263"

Scenario: Formato Meta agrega 549
  GIVEN telefono="1158530263"
  WHEN telefono_para_meta(telefono)
  THEN devuelve "5491158530263"

Scenario: Autoregistro WhatsApp normaliza teléfono
  GIVEN número entrante de WhatsApp "+5491158530263"
  WHEN register_patient_service guarda el paciente
  THEN telefono en BD = "1158530263"

Scenario: Alta manual desde panel normaliza teléfono
  GIVEN secretaria ingresa telefono="5491158530263" en el formulario
  WHEN POST /admin/pacientes
  THEN telefono en BD = "1158530263"

Scenario: send_confirmation Twilio usa formato correcto
  GIVEN telefono en BD = "1158530263"
  WHEN se envía confirmación por Twilio
  THEN to = "whatsapp:+5491158530263"

Scenario: send_confirmation Meta usa formato correcto
  GIVEN telefono en BD = "1158530263"
  WHEN se envía confirmación por Meta
  THEN to = "5491158530263"

Scenario: Eliminar [DEBUG] con PII
  GIVEN POST /admin/turnos crea un turno
  WHEN el turno se confirma y se envía WhatsApp
  THEN los logs NO contienen telefono_paciente ni nombre del paciente
```

---

## Tests — agente-commons

### tests/test_telefono.py

```python
from agente_commons.telefono import (
    normalizar_telefono_bd,
    telefono_para_twilio,
    telefono_para_meta,
)

def test_normalizar_con_mas_549():
    assert normalizar_telefono_bd("+5491158530263") == "1158530263"

def test_normalizar_con_549_sin_mas():
    assert normalizar_telefono_bd("5491158530263") == "1158530263"

def test_normalizar_con_54_sin_9():
    assert normalizar_telefono_bd("541158530263") == "1158530263"

def test_normalizar_solo_prefijo_9():
    assert normalizar_telefono_bd("91158530263") == "1158530263"

def test_normalizar_ya_normalizado():
    assert normalizar_telefono_bd("1158530263") == "1158530263"

def test_normalizar_con_espacios_y_guiones():
    assert normalizar_telefono_bd("+54 9 11-5853-0263") == "1158530263"

def test_telefono_para_twilio():
    assert telefono_para_twilio("1158530263") == "whatsapp:+5491158530263"

def test_telefono_para_meta():
    assert telefono_para_meta("1158530263") == "5491158530263"
```

---

## Orden de implementación

| Paso | Repo | Qué hacer |
|------|------|-----------|
| 1 | agente-commons | Crear `agente_commons/telefono.py` |
| 2 | agente-commons | Actualizar `__init__.py` |
| 3 | agente-commons | Crear `tests/test_telefono.py` — pytest verde |
| 4 | agente-commons | Bump versión a `0.2.0` en `pyproject.toml` + CHANGELOG |
| 5 | agente-commons | `git push` |
| 6 | agente-turnos | `pip install` agente-commons actualizado |
| 7 | agente-turnos | Actualizar `notifications.py` |
| 8 | agente-turnos | Actualizar `patient_service.py` |
| 9 | agente-turnos | Actualizar `routers/admin/pacientes.py` |
| 10 | agente-turnos | Eliminar `print [DEBUG]` en `routers/admin/turnos.py` |
| 11 | agente-turnos | Crear `tests/test_us39_normalizacion_telefono.py` |
| 12 | agente-turnos | `pytest tests/ -v` — 420+ tests en verde |
| 13 | agente-turnos | `git push` → Railway rebuild |

---

## Nota para CONTEXT.md

Agregar en la tabla de decisiones clave:

| `normalizar_telefono_bd` en commons (US-EC-07/US-39) | Formato BD = dígitos locales sin `+54` ni prefijo `9`; Twilio agrega `whatsapp:+549`; Meta agrega `549` — lógica en `agente_commons/telefono.py` |

---

## Dev Agent Record

### Notas de implementación (agente-commons)

**Implementado el 2026-06-14:**

- Creado `agente_commons/telefono.py` con las 3 funciones: `normalizar_telefono_bd`, `telefono_para_twilio`, `telefono_para_meta`
- Actualizado `agente_commons/__init__.py`: bump versión `0.1.0 → 0.2.0`, exportación `from . import telefono`
- Creado `tests/test_telefono.py` con 8 tests unitarios — todos verdes
- Bump versión en `pyproject.toml` a `0.2.0`
- Actualizado `CHANGELOG.md` con entrada v0.2.0
- Suite completa: **26/26 tests pasan**, sin regresiones

**Pendiente (agente-turnos — repo separado):**
- `tools/notifications.py`: usar `telefono_para_twilio` / `telefono_para_meta`
- `services/patient_service.py`: reemplazar normalización manual por `normalizar_telefono_bd`
- `routers/admin/pacientes.py`: aplicar `normalizar_telefono_bd` en POST y PUT
- `routers/admin/turnos.py`: eliminar `print [DEBUG]` con PII (línea 165)
- `tests/test_us39_normalizacion_telefono.py`: tests de integración

### File List

```
agente_commons/telefono.py          ← NUEVO
agente_commons/__init__.py          ← MODIFICADO (versión + import)
tests/test_telefono.py              ← NUEVO
pyproject.toml                      ← MODIFICADO (versión 0.2.0)
CHANGELOG.md                        ← MODIFICADO (entrada v0.2.0)
```

### Change Log

- 2026-06-14: US-EC-07 — módulo `telefono.py` implementado en agente-commons; versión bumpeada a 0.2.0
