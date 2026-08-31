from datetime import timedelta

from app.services.tools import (
    is_relative_date_message,
    parse_date,
    parse_user_date,
    strip_relative_date_tokens,
)
from app.timezone import local_today


def test_is_relative_date_message():
    assert is_relative_date_message("ontem")
    assert is_relative_date_message("foi ontem")
    assert is_relative_date_message("a despesa foi ontem")
    assert is_relative_date_message("amanhã")
    assert not is_relative_date_message("mercado ontem")
    assert not is_relative_date_message("gastei 50 no mercado")


def test_strip_relative_date_tokens():
    assert strip_relative_date_tokens("mercado ontem") == "mercado"
    assert strip_relative_date_tokens("foi ontem") == ""
    assert strip_relative_date_tokens("a despesa foi ontem") == ""


def test_parse_date_ontem():
    assert parse_date("ontem") == local_today() - timedelta(days=1)


def test_parse_date_amanha():
    assert parse_date("amanhã") == local_today() + timedelta(days=1)


def test_parse_user_date_formats():
    assert parse_user_date("hoje") == local_today().isoformat()
    assert parse_user_date("31/08/2026") == "2026-08-31"
    assert parse_user_date("agosto") == f"{local_today().year}-08-01"
    assert parse_user_date("1 de agosto de 2026") == "2026-08-01"
