"""US-EC-11: run_agent puede devolver None como respuesta para no enviar nada."""

import json
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agente_commons.whatsapp.router import create_whatsapp_router

META_PAYLOAD = {
    "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PHONE_123"},
        "messages": [{"type": "text", "from": "5491100000001", "text": {"body": "hola"}}],
    }}]}]
}
TWILIO_FORM = {"From": "whatsapp:+5491158530263", "To": "whatsapp:+5491199999999", "Body": "hola"}
HISTORIAL = [{"role": "user", "content": "previo"}]


def _resolver_meta(phone_number_id):
    if phone_number_id == "PHONE_123":
        return {"tenant_id": 1, "meta_access_token": "token123"}
    return None


def _resolver_twilio(numero):
    if numero == "5491199999999":
        return {"tenant_id": 1}
    return None


def _client(respuesta, guardados):
    async def get_historial(session_id):
        return []

    async def save_historial(session_id, historial):
        guardados.append((session_id, historial))

    def run_agent(**kwargs):
        return respuesta, HISTORIAL

    app = FastAPI()
    app.include_router(create_whatsapp_router(
        app_id               = "test-app",
        resolver_meta        = _resolver_meta,
        resolver_twilio      = _resolver_twilio,
        run_agent            = run_agent,
        get_historial        = get_historial,
        save_historial       = save_historial,
        twilio_account_sid   = "ACtest123",
        twilio_auth_token    = "auth_token_test",
        twilio_whatsapp_from = "whatsapp:+14155238886",
        exigir_firma         = False,
    ))
    return TestClient(app)


def _post_meta(client):
    return client.post("/whatsapp", content=json.dumps(META_PAYLOAD).encode(),
                       headers={"Content-Type": "application/json"})


def _post_twilio(client):
    return client.post("/whatsapp", data=TWILIO_FORM,
                       headers={"Content-Type": "application/x-www-form-urlencoded"})


def test_ec11_meta_none_no_envia_y_guarda_historial():
    guardados = []
    with patch("agente_commons.whatsapp.meta.enviar_mensaje") as send:
        resp = _post_meta(_client(None, guardados))
    assert resp.status_code == 200
    send.assert_not_called()
    assert guardados == [("PHONE_123:5491100000001", HISTORIAL)]


def test_ec11_twilio_none_no_envia_y_guarda_historial():
    guardados = []
    with patch("agente_commons.whatsapp.twilio_helper.Client") as client_cls:
        resp = _post_twilio(_client(None, guardados))
    assert resp.status_code == 200
    client_cls.assert_not_called()
    assert len(guardados) == 1 and guardados[0][1] == HISTORIAL


def test_ec11_meta_string_vacio_se_sigue_enviando():
    guardados = []
    with patch("agente_commons.whatsapp.meta.enviar_mensaje", return_value=True) as send:
        _post_meta(_client("", guardados))
    send.assert_called_once()
    assert send.call_args.kwargs["texto"] == ""


def test_ec11_twilio_string_vacio_se_sigue_enviando():
    guardados = []
    with patch("agente_commons.whatsapp.twilio_helper.Client") as client_cls:
        client_cls.return_value = MagicMock()
        _post_twilio(_client("", guardados))
    client_cls.return_value.messages.create.assert_called_once()


def test_ec11_none_loguea_respuesta_omitida(caplog):
    caplog.set_level("INFO")
    with patch("agente_commons.whatsapp.meta.enviar_mensaje"):
        _post_meta(_client(None, []))
    assert any("respuesta_omitida" in r.getMessage() for r in caplog.records)
