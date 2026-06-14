from agente_commons.telefono import (
    normalizar_telefono_bd,
    telefono_para_twilio,
    telefono_para_meta,
)


def test_normalizar_con_mas_549():
    assert normalizar_telefono_bd("+5491158530263") == "1158530263"


def test_normalizar_con_549_sin_mas():
    assert normalizar_telefono_bd("5491158530263") == "1158530263"


def test_normalizar_con_54_sin_9():
    assert normalizar_telefono_bd("541158530263") == "1158530263"


def test_normalizar_solo_prefijo_9():
    assert normalizar_telefono_bd("91158530263") == "1158530263"


def test_normalizar_ya_normalizado():
    assert normalizar_telefono_bd("1158530263") == "1158530263"


def test_normalizar_con_espacios_y_guiones():
    assert normalizar_telefono_bd("+54 9 11-5853-0263") == "1158530263"


def test_telefono_para_twilio():
    assert telefono_para_twilio("1158530263") == "whatsapp:+5491158530263"


def test_telefono_para_meta():
    assert telefono_para_meta("1158530263") == "5491158530263"
