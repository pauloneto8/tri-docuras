from datetime import datetime
from zoneinfo import ZoneInfo

from app.timezone import get_timezone, local_today, to_local_datetime


def test_default_timezone_is_recife():
    assert str(get_timezone()) == "America/Recife"


def test_local_today_matches_recife_offset():
    utc_now = datetime.now(ZoneInfo("UTC"))
    recife_now = utc_now.astimezone(ZoneInfo("America/Recife"))
    assert local_today() == recife_now.date()


def test_to_local_datetime_converts_utc():
    value = datetime(2026, 8, 30, 23, 30, tzinfo=ZoneInfo("UTC"))
    local = to_local_datetime(value)
    assert local.hour == 20
    assert local.tzinfo == ZoneInfo("America/Recife")
