"""2.3.49: conservative, source-only editorial admission decisions.

These are profile-selected checks, not blanket topic, publisher or word bans.
Time-critical services are evaluated at selection AND before Telegram delivery.
"""
from __future__ import annotations

from datetime import datetime, date, time
from functools import lru_cache
import re
from typing import Any
from zoneinfo import ZoneInfo

@lru_cache(maxsize=1)
def _kyiv_tz() -> ZoneInfo:
    """Resolve time-zone data only for time-sensitive service notices.

    The commercial and general newsroom gates must never depend on a platform
    timezone database merely to import their own editorial rules.
    """
    return ZoneInfo("Europe/Kyiv")
_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4,
    "травня": 5, "червня": 6, "липня": 7, "серпня": 8,
    "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}


def _get(row: Any, field: str) -> str:
    try:
        value = row[field]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, field, "")
    return str(value or "")


def _source(row: Any) -> str:
    return (_get(row, "title") + "\n" + _get(row, "raw_text")[:6500]).strip()


_SERVICE = re.compile(r"(?iu)\b(?:графік\w*|відключен\w*|електропостачанн\w*|погодинн\w*|маршрут\w*|розклад\w*)")
_ACTIVE_CHANGE = re.compile(r"(?iu)\b(?:продовжил\w*|подовжил\w*|змінил\w*|діятим\w*|діють|діє|триватим\w*|обмежен\w*|зупинен\w*|тимчасов\w*)")
_END = re.compile(r"(?iu)\bдо\s+(?:о\s*)?([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_DATE = re.compile(
    r"(?iu)(?<!\d)(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\b"
)
_HISTORICAL = re.compile(r"(?iu)\b(?:підсумк\w*|вчора|минулого\s+тижня|ретроспектив\w*)")
_TOMORROW = re.compile(r"(?iu)\b(?:завтра|наступного\s+дня)\b")


def _effective_day(row: Any, source: str, now: datetime) -> date | None:
    explicit = {(int(day), _MONTHS[month.casefold()])
                for day, month in _DATE.findall(source)
                if 1 <= int(day) <= 31}
    if len(explicit) > 1:
        return None  # Multiple service dates: never treat one end as the whole notice.
    if explicit:
        day, month = next(iter(explicit))
        try:
            return date(now.year, month, day)
        except ValueError:
            return None
    if _TOMORROW.search(source):
        return None
    published = _get(row, "source_published_at")
    try:
        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(_kyiv_tz()).date() if dt.tzinfo else None


def expired_service_reason_2349(row: Any, now: datetime | None = None) -> str:
    """Block a provably expired short-lived operational *change*, not reports.

    Unknown dates, mixed-day schedules and future notices stay eligible for
    ordinary editorial review. Never infer an end-time from discovery time.
    """
    source = _source(row)
    if not _SERVICE.search(source) or not _ACTIVE_CHANGE.search(source):
        return ""
    if _HISTORICAL.search(_get(row, "title")):
        return ""
    ends = [time(int(h), int(m)) for h, m in _END.findall(source)]
    if not ends:
        return ""
    kyiv = _kyiv_tz()
    instant = now or datetime.now(kyiv)
    if instant.tzinfo is None:
        raise ValueError("now must have a timezone")
    local = instant.astimezone(kyiv)
    valid_day = _effective_day(row, source, local)
    if valid_day is None:
        return ""
    # Multiple intervals are valid until their final confirmed end.
    if datetime.combine(valid_day, max(ends), tzinfo=kyiv) >= local:
        return ""
    return "MONITORING_SERVICE_EXPIRED_AT_PUBLISH_2349"


_ROUTINE = re.compile(
    r"(?iu)\b(?:перевірил\w*|проінспектувал\w*|оглянул\w*|"
    r"здійснил\w*\s+(?:об'їзд|огляд|візит)|"
    r"провел\w*\s+(?:щотижнев\w*\s+)?(?:моніторинг|огляд))\b"
)
_PUBLIC_RESULT = re.compile(
    r"(?iu)\b(?:виявил\w*\s+(?:порушенн\w*|недолік\w*|пошкоджен\w*)|"
    r"усунул\w*|відновил\w*|відремонтувал\w*|завершил\w*|"
    r"затвердил\w*|ухвалил\w*|виділ\w*\s+(?:кошт\w*|\d)|"
    r"відкрили|запустил\w*|передал\w*\s+(?:допомог\w*|\d)|"
    r"поранен\w*|загинул\w*|пошкоджен\w*|"
    r"перекрил\w*|обмежил\w*\s+(?:рух|доступ))\b"
)
_CIVIC_OUTCOME = re.compile(
    r"(?iu)\b(?:розклад\w*|графік\w*|маршрут\w*|евакуац\w*|"
    r"подат\w*\s+заяв\w*|адрес\w*|звертайтеся|"
    r"телефон\w*|часи?\s+роботи)\b"
)
_FIREWORK = re.compile(r"(?iu)\b(?:феєрверк\w*|салют\w*|піротехнік\w*)")
_UNCONFIRMED = re.compile(r"(?iu)\b(?:пишуть|кажуть|повідомляють|чули|нібито|очевидці)\b")
_VERIFIED_RESPONSE = re.compile(
    r"(?iu)\b(?:поліці\w*|затримал\w*|встановил\w*|виявил\w*|"
    r"постраждал\w*|поранен\w*|офіційн\w*\s+підтверджен\w*)"
)


def regional_no_result_reason_2349(row: Any) -> str:
    source = _source(row)
    if not source:
        return ""
    if (_ROUTINE.search(source) and not _PUBLIC_RESULT.search(source)
            and not _CIVIC_OUTCOME.search(source)):
        return "MONITORING_ROUTINE_INSPECTION_NO_OUTCOME_2349"
    # Short unverified neighborhood signals are not established incidents.
    if (len(source) < 350 and _FIREWORK.search(source)
            and _UNCONFIRMED.search(source) and not _VERIFIED_RESPONSE.search(source)):
        return "MONITORING_UNVERIFIED_SHORT_SIGNAL_2349"
    return ""


_CATALOG = re.compile(
    r"(?iu)^\s*(?:(?:\d{1,2}|five|ten)\s+(?:of\s+the\s+)?(?:best|top)|"
    r"top\s+\d{1,2})\b[^.!?\n]{0,110}\b"
    r"(?:accessor\w*|gadget\w*|product\w*|item\w*|"
    r"аксесуар\w*|гаджет\w*|товар\w*|реч\w*)\b"
)


def commercial_catalog_reason_2349(row: Any) -> str:
    """Only a bare best-N shopping/accessory selection, not all listicles."""
    if _CATALOG.search(_get(row, "title")):
        return "CREATIVE_ROUTINE_BEST_N_CATALOG_2349"
    return ""


__all__ = [
    "expired_service_reason_2349",
    "regional_no_result_reason_2349",
    "commercial_catalog_reason_2349",
]
