from agente_commons.whatsapp import meta


def test_verificar_firma_valida():
    import hmac, hashlib
    secret = "test_secret"
    payload = b'{"test": "data"}'
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert meta.verificar_firma(payload, sig, secret) is True


def test_verificar_firma_invalida():
    assert meta.verificar_firma(b"data", "sha256=invalida", "secret") is False


def test_verificar_firma_sin_secret():
    assert meta.verificar_firma(b"data", "sha256=algo", "") is False


def test_parsear_mensaje_texto():
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{"type": "text", "from": "5491100000001",
                          "text": {"body": "hola"}}]
        }}]}]
    }
    result = meta.parsear_mensaje(payload)
    assert result is not None
    assert result["texto"] == "hola"
    assert result["phone_number_id"] == "123"
    assert result["numero_usuario"] == "5491100000001"


def test_parsear_mensaje_status_update():
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "statuses": [{"status": "delivered"}]
        }}]}]
    }
    assert meta.parsear_mensaje(payload) is None


def test_parsear_mensaje_tipo_imagen():
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{"type": "image", "from": "5491100000001"}]
        }}]}]
    }
    assert meta.parsear_mensaje(payload) is None


def test_session_key():
    key = meta.session_key("PHONE_ID_123", "5491100000001")
    assert key == "PHONE_ID_123:5491100000001"
