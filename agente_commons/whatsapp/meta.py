import hmac
import hashlib
import logging
import requests as http_requests

logger = logging.getLogger(__name__)


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

    if message.get("type") != "text":
        logger.info(f"meta_ignored_type | type={message.get('type')}")
        return None

    phone_number_id = metadata.get("phone_number_id")
    numero_usuario  = message.get("from")
    texto           = message.get("text", {}).get("body", "")

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
