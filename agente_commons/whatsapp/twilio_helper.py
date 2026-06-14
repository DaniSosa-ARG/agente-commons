import logging
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from fastapi.responses import PlainTextResponse

from agente_commons.telefono import normalizar_telefono_bd, telefono_para_twilio

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
    numero_destino puede venir como dígitos locales o ya normalizado por Twilio (whatsapp:+...).
    """
    try:
        client = Client(account_sid, auth_token)
        client.messages.create(
            from_ = from_,
            to    = telefono_para_twilio(normalizar_telefono_bd(numero_destino)),
            body  = texto,
        )
        return True
    except Exception as e:
        logger.error("twilio_enviar_mensaje_error | error=%s", str(e))
        return False
