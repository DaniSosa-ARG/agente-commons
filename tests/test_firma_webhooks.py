"""
test_firma_webhooks.py — US-EC-10: firma de webhooks obligatoria (default desde 0.5.0).

Meta: todo POST sin X-Hub-Signature-256 válida → 403, también sin header.
Twilio: todo POST sin X-Twilio-Signature válida → 403, validando contra la URL pública
(explícita o reconstruida con X-Forwarded-Proto/Host).
Un request rechazado no llama al resolver ni al agente.
"""

import hashlib
import hmac
import json
import logging
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from agente_commons.whatsapp import twilio_helper
from agente_commons.whatsapp.router import create_whatsapp_router

APP_SECRET   = "meta_secret_test"
AUTH_TOKEN   = "twilio_token_test"
URL_PUBLICA  = "https://agente.example.com/whatsapp"

META_PAYLOAD = json.dumps({
    "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PHONE_123"},
        "messages": [{"type": "text", "from": "5491100000001", "text": {"body": "hola"}}],
    }}]}]
}).encode()

TWILIO_FORM = {"From": "whatsapp:+5491100000001", "To": "whatsapp:+5491199999999", "Body": "hola"}


def _firma_meta(payload: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _firma_twilio(url: str, params: dict = TWILIO_FORM, token: str = AUTH_TOKEN) -> str:
    return RequestValidator(token).compute_signature(url, params)


def _client(meta_app_secret=APP_SECRET, twilio_auth_token=AUTH_TOKEN, twilio_webhook_url="", **extra):
    """Devuelve (client, mocks) con resolvers y agente espiados."""
    resolver_meta = MagicMock(return_value={"tenant_id": 1, "meta_access_token": "tok"})
    resolver_twilio = MagicMock(return_value={"tenant_id": 1})
    run_agent = MagicMock(return_value=("respuesta", []))

    async def get_historial(_):
        return []

    async def save_historial(_, __):
        pass

    app = FastAPI()
    app.include_router(create_whatsapp_router(
        app_id             = "test-app",
        resolver_meta      = resolver_meta,
        resolver_twilio    = resolver_twilio,
        run_agent          = run_agent,
        get_historial      = get_historial,
        save_historial     = save_historial,
        meta_app_secret    = meta_app_secret,
        twilio_auth_token  = twilio_auth_token,
        twilio_webhook_url = twilio_webhook_url,
        **extra,
    ))
    mocks = {"resolver_meta": resolver_meta, "resolver_twilio": resolver_twilio, "run_agent": run_agent}
    return TestClient(app), mocks


def _post_meta(client, payload=META_PAYLOAD, firma=None):
    headers = {"Content-Type": "application/json"}
    if firma is not None:
        headers["X-Hub-Signature-256"] = firma
    return client.post("/whatsapp", content=payload, headers=headers)


def _post_twilio(client, firma=None, headers=None, url="/whatsapp", form=TWILIO_FORM):
    h = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    if firma is not None:
        h["X-Twilio-Signature"] = firma
    return client.post(url, data=form, headers=h)


def _sin_efectos(mocks, proveedor):
    mocks[f"resolver_{proveedor}"].assert_not_called()
    mocks["run_agent"].assert_not_called()


# ── Meta ──────────────────────────────────────────────────────────────────────

def test_usEC10_meta_firma_valida_procesa():
    client, mocks = _client()
    resp = _post_meta(client, firma=_firma_meta(META_PAYLOAD))
    assert resp.status_code == 200
    mocks["resolver_meta"].assert_called_once_with("PHONE_123")
    mocks["run_agent"].assert_called_once()


def test_usEC10_meta_sin_header_403():
    client, mocks = _client()
    resp = _post_meta(client)
    assert resp.status_code == 403
    _sin_efectos(mocks, "meta")


def test_usEC10_meta_firma_invalida_403():
    client, mocks = _client()
    resp = _post_meta(client, firma=_firma_meta(META_PAYLOAD, secret="otro_secret"))
    assert resp.status_code == 403
    _sin_efectos(mocks, "meta")


def test_usEC10_meta_payload_alterado_403():
    client, mocks = _client()
    firma = _firma_meta(META_PAYLOAD)
    alterado = META_PAYLOAD.replace(b"5491100000001", b"5491100000002")
    resp = _post_meta(client, payload=alterado, firma=firma)
    assert resp.status_code == 403
    _sin_efectos(mocks, "meta")


def test_usEC10_meta_sin_secret_rechaza_todo():
    client, mocks = _client(meta_app_secret="")
    # Ni siquiera una "firma" calculada con secret vacío pasa.
    resp = _post_meta(client, firma=_firma_meta(META_PAYLOAD, secret=""))
    assert resp.status_code == 403
    _sin_efectos(mocks, "meta")


# ── Twilio ────────────────────────────────────────────────────────────────────

def test_usEC10_twilio_firma_valida_url_explicita():
    client, mocks = _client(twilio_webhook_url=URL_PUBLICA)
    resp = _post_twilio(client, firma=_firma_twilio(URL_PUBLICA))
    assert resp.status_code == 200
    mocks["resolver_twilio"].assert_called_once()
    mocks["run_agent"].assert_called_once()


def test_usEC10_twilio_sin_header_403():
    client, mocks = _client(twilio_webhook_url=URL_PUBLICA)
    resp = _post_twilio(client)
    assert resp.status_code == 403
    _sin_efectos(mocks, "twilio")


def test_usEC10_twilio_firma_invalida_403():
    client, mocks = _client(twilio_webhook_url=URL_PUBLICA)
    resp = _post_twilio(client, firma=_firma_twilio(URL_PUBLICA, token="otro_token"))
    assert resp.status_code == 403
    _sin_efectos(mocks, "twilio")


def test_usEC10_twilio_remitente_alterado_403():
    """La firma cubre los params: cambiar From invalida la firma."""
    client, mocks = _client(twilio_webhook_url=URL_PUBLICA)
    firma = _firma_twilio(URL_PUBLICA)
    falsificado = {**TWILIO_FORM, "From": "whatsapp:+5491100000002"}
    resp = _post_twilio(client, firma=firma, form=falsificado)
    assert resp.status_code == 403
    _sin_efectos(mocks, "twilio")


def test_usEC10_twilio_sin_token_rechaza_todo():
    client, mocks = _client(twilio_auth_token="", twilio_webhook_url=URL_PUBLICA)
    resp = _post_twilio(client, firma=_firma_twilio(URL_PUBLICA))
    assert resp.status_code == 403
    _sin_efectos(mocks, "twilio")


def test_usEC10_twilio_detras_de_proxy():
    """Railway termina TLS: el request llega http://<interno>, Twilio firmó https://<público>."""
    client, mocks = _client()
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "agente.example.com"}
    resp = _post_twilio(client, firma=_firma_twilio(URL_PUBLICA), headers=headers)
    assert resp.status_code == 200
    mocks["run_agent"].assert_called_once()


def test_usEC10_twilio_sin_forwarded_usa_url_del_request():
    client, mocks = _client()
    resp = _post_twilio(client, firma=_firma_twilio("http://testserver/whatsapp"))
    assert resp.status_code == 200


def test_usEC10_twilio_firma_cubre_query_string():
    client, mocks = _client()
    url = "/whatsapp?origen=twilio"
    resp = _post_twilio(client, url=url, firma=_firma_twilio("http://testserver" + url))
    assert resp.status_code == 200
    resp = _post_twilio(client, url=url, firma=_firma_twilio("http://testserver/whatsapp"))
    assert resp.status_code == 403


def test_usEC10_twilio_verificar_firma_sin_datos():
    assert twilio_helper.verificar_firma(URL_PUBLICA, TWILIO_FORM, "", AUTH_TOKEN) is False
    assert twilio_helper.verificar_firma(URL_PUBLICA, TWILIO_FORM, "x", "") is False


# ── Configuración ─────────────────────────────────────────────────────────────

def test_usEC10_log_error_sin_secretos(caplog):
    with caplog.at_level(logging.ERROR, logger="agente_commons.whatsapp.router"):
        _client(meta_app_secret="", twilio_auth_token="")
    mensajes = " ".join(r.getMessage() for r in caplog.records)
    assert "meta_app_secret no configurado" in mensajes
    assert "twilio_auth_token no configurado" in mensajes


def test_usEC10_exigir_firma_false_conserva_comportamiento_anterior():
    client, mocks = _client(exigir_firma=False)
    assert _post_meta(client).status_code == 200                       # sin header: pasa
    assert _post_meta(client, firma="sha256=mal").status_code == 403   # presente e inválida: 403
    assert _post_twilio(client).status_code == 200                     # Twilio sin validar
