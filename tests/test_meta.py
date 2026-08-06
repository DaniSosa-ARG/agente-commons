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


# ── US-EC-09: interactive.list_reply ─────────────────────────────────────────

def test_parsear_mensaje_interactive_list_reply():
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{
                "type": "interactive",
                "from": "5491100000001",
                "interactive": {
                    "type": "list_reply",
                    "list_reply": {"id": "motivo_16", "title": "Consulta general"},
                },
            }]
        }}]}]
    }
    result = meta.parsear_mensaje(payload)
    assert result is not None
    assert result["phone_number_id"] == "123"
    assert result["numero_usuario"] == "5491100000001"
    assert result["texto"] == meta.LIST_REPLY_MARKER + "motivo_16" + "\x00" + "Consulta general"


def test_parsear_mensaje_interactive_list_reply_sin_title():
    """title es opcional en el payload real de Meta — no debe romper el parseo."""
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{
                "type": "interactive",
                "from": "5491100000001",
                "interactive": {
                    "type": "list_reply",
                    "list_reply": {"id": "motivo_16"},
                },
            }]
        }}]}]
    }
    result = meta.parsear_mensaje(payload)
    assert result is not None
    assert result["texto"] == meta.LIST_REPLY_MARKER + "motivo_16" + "\x00"


def test_parsear_mensaje_interactive_button_reply_ignorado():
    """Solo list_reply está soportado — button_reply se ignora, no se inventa un texto."""
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{
                "type": "interactive",
                "from": "5491100000001",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "btn_1", "title": "Sí"},
                },
            }]
        }}]}]
    }
    assert meta.parsear_mensaje(payload) is None


def test_parsear_mensaje_interactive_sin_id_ignorado():
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{
                "type": "interactive",
                "from": "5491100000001",
                "interactive": {"type": "list_reply", "list_reply": {"id": "", "title": "x"}},
            }]
        }}]}]
    }
    assert meta.parsear_mensaje(payload) is None


def test_parsear_mensaje_texto_sigue_igual_no_regresion():
    """Mismo caso que test_parsear_mensaje_texto — el branch interactive no debe afectarlo."""
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{"type": "text", "from": "5491100000001",
                          "text": {"body": "hola"}}]
        }}]}]
    }
    result = meta.parsear_mensaje(payload)
    assert result == {
        "phone_number_id": "123",
        "numero_usuario":  "5491100000001",
        "texto":           "hola",
    }
