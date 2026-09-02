from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

LOG = logging.getLogger("telegram_autopilot.rc63")
_INSTALLED = False
QUIET_HOURS = (0, 7)
CTRL_MIN_GAP_MINUTES = 60
MARKETING_MIN_GAP_MINUTES = 90
_LOG_EVERY_SECONDS = 300
_LAST_HOLD_LOG: dict[tuple[int, str], float] = {}


def _parse_dt(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def publication_hold_reason(service: Any, channel: Any, *, now: datetime | None = None) -> tuple[str, datetime | None]:
    """Return only time-based publication holds used while editorial learning is active.

    RC63 deliberately has NO daily cap, rolling-N-post cap or other total-publication
    quota. Editorial/source/topic saturation remains a candidate-ranking concern,
    not a channel-wide publication-count stop.
    """
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    start, end = QUIET_HOURS
    if start <= current.hour < end:
        wake = current.replace(hour=end, minute=0, second=0, microsecond=0)
        return "quiet_hours", wake

    from .rc62_editorial_control import _is_marketing_channel

    marketing = _is_marketing_channel(service.db, int(channel.id), channel)
    configured = max(0, int(getattr(channel, "min_publish_interval_minutes", 0) or 0))
    minimum = MARKETING_MIN_GAP_MINUTES if marketing else CTRL_MIN_GAP_MINUTES
    gap = max(configured, minimum)

    try:
        raw_last = service.db.last_published_at(int(channel.id))
    except Exception:
        raw_last = ""
    last = _parse_dt(raw_last)
    if last is None:
        return "", None

    last_local = last.astimezone(current.tzinfo)
    next_allowed = last_local + timedelta(minutes=gap)
    if current < next_allowed:
        return "spacing", next_allowed
    return "", None


def training_gap_ok(service: Any, channel: Any) -> bool:
    reason, until = publication_hold_reason(service, channel)
    if not reason:
        return True

    cid = int(getattr(channel, "id", 0) or 0)
    key = (cid, reason)
    stamp = time.monotonic()
    if stamp - _LAST_HOLD_LOG.get(key, 0.0) >= _LOG_EVERY_SECONDS:
        _LAST_HOLD_LOG[key] = stamp
        until_text = until.isoformat(timespec="minutes") if until is not None else "unknown"
        LOG.info(
            "RC63 HOLD channel_id=%s channel=%s reason=%s until=%s; publication-count caps are disabled",
            cid,
            str(getattr(channel, "name", "") or cid),
            reason,
            until_text,
        )
    return False


def install_rc63_training_mode() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import service as service_module

    service_module.AutopilotService._gap_ok = training_gap_ok
    LOG.info(
        "RC63 installed: training mode has no daily or rolling publication-count caps; "
        "only quiet hours and minimum spacing remain at channel level"
    )
    _INSTALLED = True
