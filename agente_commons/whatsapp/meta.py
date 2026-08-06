import hmac
import hashlib
import logging
import requests as http_requests

logger = logging.getLogger(__name__)

# US-EC-09: separador de un mensaje interactive.list_reply codificado en el campo
# "texto" que ya devuelve parsear_mensaje() para mensajes de texto. NUL — no aparece
# en texto real de WhatsApp. Formato: MARKER + id + "\x00" + title.
LIST_REPLY_MARKER = "\x00LIST_REPLY\x00"


def verificar_firma(payload_bytes: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Valida X-Hub-Signature-256 enviado por Meta en cada POST webhook.
    Retorna False si falta app_secret o signature_header.
    """
    if not app_secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def parsear_mensaje(data: dict) -> dict | None:
    """
    Extrae los campos relevantes del payload JSON de Meta.
    Retorna None si el payload es un status update o tipo no soportado.

    Estructura Meta:
    data.entry[0].changes[0].value.messages[0]
    data.entry[0].changes[0].value.metadata.phone_number_id
    """
    try:
        entry    = data.get("entry", [])[0]
        change   = entry.get("changes", [])[0]
        value    = change.get("value", {})
        metadata = value.get("metadata", {})
        messages = value.get("messages", [])
    except (IndexError, KeyError, AttributeError):
        return None

    if not messages:
        return None

    message = messages[0]
    phone_number_id = metadata.get("phone_number_id")
    numero_usuario  = message.get("from")

    # US-EC-09: mensaje interactive.list_reply (paciente tocó una fila de una lista).
    # Aditivo — no modifica el branch de texto de abajo.
    if message.get("type") == "interactive":
        interactive = message.get("interactive", {})
        if interactive.get("type") != "list_reply":
            logger.info(f"meta_ignored_interactive_type | type={interactive.get('type')}")
            return None

        list_reply  = interactive.get("list_reply", {})
        reply_id    = list_reply.get("id", "")
        reply_title = list_reply.get("title", "")

        if not phone_number_id or not numero_usuario or not reply_id:
            return None

        return {
            "phone_number_id": phone_number_id,
            "numero_usuario":  numero_usuario,
            "texto":           f"{LIST_REPLY_MARKER}{reply_id}\x00{reply_title}",
        }

    if message.get("type") != "text":
        logger.info(f"meta_ignored_type | type={message.get('type')}")
        return None

    texto = message.get("text", {}).get("body", "")

    if not phone_number_id or not numero_usuario or not texto:
        return None

    return {
        "phone_number_id": phone_number_id,
        "numero_usuario":  numero_usuario,
        "texto":           texto,
    }


def enviar_mensaje(
    phone_number_id: str,
    numero_usuario: str,
    texto: str,
    access_token: str,
) -> bool:
    """
    Envía un mensaje de texto via Meta Graph API v19.0.
    Retorna True si el envío fue exitoso, False si hubo error.
    """
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                numero_usuario,
        "type":              "text",
        "text":              {"body": texto},
    }
    try:
        response = http_requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"meta_send_error | status={response.status_code} | resp={response.text}")
            return False
        return True
    except Exception as e:
        logger.error(f"meta_send_exception | error={str(e)}")
        return False


def session_key(phone_number_id: str, numero_usuario: str) -> str:
    """
    Genera la clave de sesión Redis para Meta.
    Incluye phone_number_id para aislar por tenant.
    """
    return f"{phone_number_id}:{numero_usuario}"
