"""Commercial source freshness gate."""

from datetime import datetime, timedelta, timezone


def source_is_stale(value, hours=48):
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return False
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    return age > timedelta(hours=hours)
