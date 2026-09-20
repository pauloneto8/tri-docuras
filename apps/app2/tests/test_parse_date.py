from datetime import date, timedelta

from app.services.tools import (
    WEEKDAYS_PT,
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


def test_parse_date_anteontem():
    assert parse_date("anteontem") == local_today() - timedelta(days=2)


def test_parse_date_depois_de_amanha():
    assert parse_date("depois de amanhã") == local_today() + timedelta(days=2)
    assert parse_date("depois de amanha") == local_today() + timedelta(days=2)


def test_parse_date_daqui_a_n_dias():
    assert parse_date("daqui a 5 dias") == local_today() + timedelta(days=5)
    assert parse_date("em 3 dias") == local_today() + timedelta(days=3)


def test_parse_date_semana_que_vem():
    assert parse_date("semana que vem") == local_today() + timedelta(days=7)
    assert parse_date("semana seguinte") == local_today() + timedelta(days=7)
    assert parse_date("próxima semana") == local_today() + timedelta(days=7)


def test_parse_date_semana_passada():
    assert parse_date("semana passada") == local_today() - timedelta(days=7)


def test_parse_date_weekday_bare():
    today = local_today()
    expected_delta = (0 - today.weekday()) % 7  # segunda
    assert parse_date("segunda") == today + timedelta(days=expected_delta)
    expected_delta_sabado = (5 - today.weekday()) % 7
    assert parse_date("sábado") == today + timedelta(days=expected_delta_sabado)


def test_parse_date_weekday_proxima():
    today = local_today()
    weekday_today_name = [name for name, idx in WEEKDAYS_PT.items() if idx == today.weekday()][0]
    assert parse_date(f"próxima {weekday_today_name}") == today + timedelta(days=7)
    assert parse_date(f"{weekday_today_name} que vem") == today + timedelta(days=7)


def test_parse_user_date_no_year_current():
    today = local_today()
    future = today + timedelta(days=10)
    if future.year != today.year:
        future = today + timedelta(days=1)
    assert parse_user_date(f"{future.day:02d}/{future.month:02d}") == future.isoformat()


def test_parse_user_date_no_year_rolls_to_next_year():
    today = local_today()
    past = today - timedelta(days=10)
    if past.year != today.year or past == today:
        past = today - timedelta(days=1)
    if past == today:
        return
    expected = date(today.year + 1, past.month, past.day)
    assert parse_user_date(f"{past.day:02d}/{past.month:02d}") == expected.isoformat()
