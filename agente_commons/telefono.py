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
        t = t[3:]
    elif t.startswith("54"):
        t = t[2:]
    # Saca el 9 de prefijo celular solo si el número resultante tiene 11 dígitos
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
