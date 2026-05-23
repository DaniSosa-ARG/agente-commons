import hmac
import hashlib
import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agente_commons.whatsapp.router import create_whatsapp_router


# ── fixtures de payload ───────────────────────────────────────────────────────

META_PAYLOAD = {
    "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PHONE_123"},
        "messages": [{"type": "text", "from": "5491100000001", "text": {"body": "hola"}}],
    }}]}]
}

META_STATUS_UPDATE = {
    "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PHONE_123"},
        "statuses": [{"status": "delivered"}],
    }}]}]
}

APP_SECRET   = "test_secret"
VERIFY_TOKEN = "test_verify_token"


# ── callbacks mock ────────────────────────────────────────────────────────────

def resolver_meta(phone_number_id):
    if phone_number_id == "PHONE_123":
        return {"app_id": "test-app", "tenant_id": 1, "meta_access_token": "token123"}
    return None


def resolver_twilio(numero_club):
    if numero_club == "5491199999999":
        return {"app_id": "test-app", "tenant_id": 1}
    return None


def run_agent(historial, mensaje_usuario, tenant_id, tenant_params, numero_usuario):
    return "respuesta del agente", historial + [{"role": "user", "content": mensaje_usuario}]


async def get_historial(session_id):
    return []


async def save_historial(session_id, historial):
    pass


# ── helper para construir clients ─────────────────────────────────────────────

def make_client(meta_app_secret: str = "", meta_verify_token: str = VERIFY_TOKEN) -> TestClient:
    app = FastAPI()
    router = create_whatsapp_router(
        app_id            = "test-app",
        resolver_meta     = resolver_meta,
        resolver_twilio   = resolver_twilio,
        run_agent         = run_agent,
        get_historial     = get_historial,
        save_historial    = save_historial,
        meta_verify_token = meta_verify_token,
        meta_app_secret   = meta_app_secret,
    )
    app.include_router(router)
    return TestClient(app)


def _firma_valida_header(payload_bytes: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()


# ── tests ACs del story ───────────────────────────────────────────────────────

def test_twilio_request_procesado():
    """POST form-data → detecta Twilio, ejecuta agente, responde TwiML."""
    client = make_client()
    response = client.post(
        "/whatsapp",
        data={"From": "whatsapp:+5491100000001", "To": "whatsapp:+5491199999999", "Body": "reserva"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert "<?xml" in response.text or "<Response>" in response.text


def test_meta_request_procesado():
    """POST JSON → detecta Meta, ejecuta agente, responde ok 200."""
    client = make_client()
    payload = json.dumps(META_PAYLOAD).encode()
    with patch("agente_commons.whatsapp.meta.enviar_mensaje") as mock_send:
        mock_send.return_value = True
        response = client.post(
            "/whatsapp",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 200
    assert response.text == "ok"
    mock_send.assert_called_once()


def test_meta_status_update_ignorado():
    """POST JSON sin messages → responde ok 200 sin ejecutar agente."""
    client = make_client()
    payload = json.dumps(META_STATUS_UPDATE).encode()
    response = client.post(
        "/whatsapp",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.text == "ok"


def test_meta_firma_invalida():
    """POST con firma incorrecta y secret configurado → 403."""
    client = make_client(meta_app_secret=APP_SECRET)
    payload = json.dumps(META_PAYLOAD).encode()
    response = client.post(
        "/whatsapp",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=firma_incorrecta",
        },
    )
    assert response.status_code == 403


def test_meta_verificacion_webhook():
    """GET con hub.verify_token correcto → responde hub.challenge y 200."""
    client = make_client()
    response = client.get(
        "/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge_abc",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge_abc"


# ── tests de patches del code review ─────────────────────────────────────────

def test_twilio_club_desconocido():
    """Twilio con número de club no registrado → responde TwiML de error."""
    client = make_client()
    response = client.post(
        "/whatsapp",
        data={"From": "whatsapp:+5491100000001", "To": "whatsapp:+9999999999", "Body": "hola"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert "<?xml" in response.text or "<Response>" in response.text
    assert "no está disponible" in response.text


def test_meta_firma_ausente_con_secret():
    """POST sin header de firma aunque haya secret → acepta (ping de consola Meta)."""
    client = make_client(meta_app_secret=APP_SECRET)
    payload = json.dumps(META_STATUS_UPDATE).encode()
    response = client.post(
        "/whatsapp",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.text == "ok"


def test_meta_webhook_sin_challenge():
    """GET sin hub.challenge → responde 200 con body vacío."""
    client = make_client()
    response = client.get(
        "/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
        },
    )
    assert response.status_code == 200
    assert response.text == ""
