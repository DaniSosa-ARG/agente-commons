import logging
from twilio.twiml.messaging_response import MessagingResponse
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)


def twiml_response(texto: str) -> PlainTextResponse:
    """Construye una respuesta TwiML con el texto dado."""
    twiml = MessagingResponse()
    twiml.message(texto)
    return PlainTextResponse(str(twiml), media_type="text/xml")


def normalizar_numero(numero: str) -> str:
    """Elimina el prefijo 'whatsapp:' y '+' que agrega Twilio."""
    return numero.replace("whatsapp:", "").replace("+", "")


def session_key(numero_club: str, numero_usuario: str) -> str:
    """
    Genera la clave de sesión Redis para Twilio.
    Paralelo a meta.session_key() para consistencia.
    """
    return f"{numero_club}:{numero_usuario}"
