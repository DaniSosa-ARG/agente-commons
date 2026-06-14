"""Tests US-EC-08: envío activo de respuesta en canal Twilio."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agente_commons.whatsapp import twilio_helper as wh_twilio
from agente_commons.whatsapp.router import create_whatsapp_router


# ── helpers de router ────────────────────────────────────────────────────────

def resolver_twilio(numero_club):
    if numero_club == "5491199999999":
        return {"app_id": "test-app", "tenant_id": 1}
    return None


def resolver_meta(phone_number_id):
    return None


def run_agent(**kwargs):
    return "respuesta del agente EC-08", []


async def get_historial(session_id):
    return []


async def save_historial(session_id, historial):
    pass


def make_client_con_credenciales() -> TestClient:
    app = FastAPI()
    router = create_whatsapp_router(
        app_id               = "test-app",
        resolver_meta        = resolver_meta,
        resolver_twilio      = resolver_twilio,
        run_agent            = run_agent,
        get_historial        = get_historial,
        save_historial       = save_historial,
        twilio_account_sid   = "ACtest123",
        twilio_auth_token    = "auth_token_test",
        twilio_whatsapp_from = "whatsapp:+14155238886",
    )
    app.include_router(router)
    return TestClient(app)


def make_client_sin_credenciales() -> TestClient:
    app = FastAPI()
    router = create_whatsapp_router(
        app_id          = "test-app",
        resolver_meta   = resolver_meta,
        resolver_twilio = resolver_twilio,
        run_agent       = run_agent,
        get_historial   = get_historial,
        save_historial  = save_historial,
    )
    app.include_router(router)
    return TestClient(app)


# ── tests enviar_mensaje en twilio_helper ─────────────────────────────────────

def test_ec08_enviar_mensaje_twilio_exitoso():
    """enviar_mensaje llama a Twilio Client.messages.create con parámetros correctos."""
    mock_client = MagicMock()
    with patch("agente_commons.whatsapp.twilio_helper.Client", return_value=mock_client):
        resultado = wh_twilio.enviar_mensaje(
            numero_destino = "1158530263",
            texto          = "Tu turno está confirmado",
            account_sid    = "ACtest",
            auth_token     = "token123",
            from_          = "whatsapp:+14155238886",
        )
    assert resultado is True
    mock_client.messages.create.assert_called_once_with(
        from_ = "whatsapp:+14155238886",
        to    = "whatsapp:+5491158530263",
        body  = "Tu turno está confirmado",
    )


def test_ec08_enviar_mensaje_twilio_formato_numero():
    """enviar_mensaje usa telefono_para_twilio → 'whatsapp:+549...'."""
    mock_client = MagicMock()
    with patch("agente_commons.whatsapp.twilio_helper.Client", return_value=mock_client):
        wh_twilio.enviar_mensaje(
            numero_destino = "1158530263",
            texto          = "hola",
            account_sid    = "ACtest",
            auth_token     = "token",
            from_          = "whatsapp:+14155238886",
        )
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["to"] == "whatsapp:+5491158530263"


def test_ec08_enviar_mensaje_twilio_error_no_relanza():
    """Si Twilio lanza excepción, enviar_mensaje devuelve False sin propagar."""
    with patch("agente_commons.whatsapp.twilio_helper.Client", side_effect=Exception("API error")):
        resultado = wh_twilio.enviar_mensaje(
            numero_destino = "1158530263",
            texto          = "hola",
            account_sid    = "ACtest",
            auth_token     = "token",
            from_          = "whatsapp:+14155238886",
        )
    assert resultado is False


# ── tests integración router ──────────────────────────────────────────────────

def test_ec08_procesar_twilio_llama_enviar_mensaje():
    """Con credenciales configuradas, _procesar_twilio llama a enviar_mensaje."""
    client = make_client_con_credenciales()
    with patch("agente_commons.whatsapp.twilio_helper.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        response = client.post(
            "/whatsapp",
            data={"From": "whatsapp:+5491158530263", "To": "whatsapp:+5491199999999", "Body": "hola"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert response.status_code == 200
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["to"] == "whatsapp:+5491158530263"
    assert call_kwargs["body"] == "respuesta del agente EC-08"


def test_ec08_procesar_twilio_sin_credenciales_no_envia():
    """Sin twilio_account_sid, _procesar_twilio no llama a enviar_mensaje."""
    client = make_client_sin_credenciales()
    with patch("agente_commons.whatsapp.twilio_helper.Client") as mock_client_cls:
        response = client.post(
            "/whatsapp",
            data={"From": "whatsapp:+5491158530263", "To": "whatsapp:+5491199999999", "Body": "hola"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert response.status_code == 200
    mock_client_cls.assert_not_called()
