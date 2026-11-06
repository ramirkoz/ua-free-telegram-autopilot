"""2.3.16: same-feature dedupe for the duplicated app-notification story.

This is intentionally MUCH narrower than topic similarity. An unrelated app
update or an actual new electricity schedule must remain eligible.
"""
from __future__ import annotations

import re
from typing import Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def _field(row: Any, key: str) -> str:
    try:
        return str(row[key] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, key, "") or "")


_APP = re.compile(r"(?iu)(?:цифрове\s+запоріжжя|digital\s+zaporizhzhia)")
_NOTIFICATION = re.compile(r"(?iu)(?:сповіщен\w*|повідомлен\w*\s+про\s+(?:зміни|оновлення))")
_GRID = re.compile(r"(?iu)(?:графік\w*|відключен\w*|знеструмлен\w*)")
_HOURS = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")
_NEW_EVENT = re.compile(r"(?iu)(?:нова\s+версія\s+\d|оновленн\w*\s+версії|"
                        r"нов\w*\s+(?:розділ|можливість|сервіс|функці\w*)\s+"
                        r"(?:доставк\w*|електрон\w*|оплат\w*|реєстраці\w*))")


def _time(value: str) -> datetime | None:
    try:
        value = str(value or "").strip()
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def app_notification_same_event_2316(a: Any, b: Any) -> tuple[bool, str]:
    if _field(a, "source_id") == _field(b, "source_id"):
        return False, "same publisher must use the existing identity rules"
    source_a = _field(a, "raw_text")[:3500]
    source_b = _field(b, "raw_text")[:3500]
    if not all(pattern.search(x) for pattern in (_APP, _NOTIFICATION, _GRID)
               for x in (source_a, source_b)):
        return False, "not two independently reported app notification features"
    # Actual updated electricity group hours are distinct news, not a duplicate
    # of a service-feature announcement.
    if _HOURS.search(source_a) or _HOURS.search(source_b):
        return False, "specific schedule hours are a new time-sensitive event"
    if _NEW_EVENT.search(source_a) or _NEW_EVENT.search(source_b):
        return False, "possibly a separate new app function"
    t1, t2 = _time(_field(a, "source_published_at")), _time(_field(b, "source_published_at"))
    if t1 is not None and t2 is not None and abs((t1-t2).total_seconds()) > 48*3600:
        return False, "outside same announcement window"
    return True, "same Zaporizhzhia app outage-notification feature, no distinct update"
