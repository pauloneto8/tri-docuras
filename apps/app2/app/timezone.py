from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings


def get_timezone() -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def local_today() -> date:
    return datetime.now(get_timezone()).date()


def local_now() -> datetime:
    return datetime.now(get_timezone())


def to_local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(get_timezone())
