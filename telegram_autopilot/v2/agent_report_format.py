from __future__ import annotations

from typing import Any


_STATUS_UA = {
    "OK": "OK",
    "WARNING": "ПОПЕРЕДЖЕННЯ",
    "CRITICAL": "КРИТИЧНО",
    "RECOVERY": "ВІДНОВЛЕННЯ",
    "DEGRADED": "ПОГІРШЕННЯ",
    "ERROR": "ПОМИЛКА",
}


def _text(value: Any, *, default: str = "—", limit: int = 700) -> str:
    if isinstance(value, (list, tuple, set)):
        text = "; ".join(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, dict):
        text = "; ".join(
            f"{str(key).strip()}: {str(item).strip()}"
            for key, item in value.items()
            if str(key).strip() and item not in (None, "")
        )
    else:
        text = str(value or "").strip()
    return (text or default)[:limit]


def _runtime_text(report: dict[str, Any]) -> str:
    direct = report.get("runtime_ua")
    if direct:
        return _text(direct, limit=450)
    value = report.get("runtime")
    if not isinstance(value, dict):
        return _text(value, limit=450)
    state = value.get("state") or value.get("lifecycle") or value.get("lifecycle_state") or "—"
    workers = value.get("workers")
    collectors = value.get("collectors")
    if workers is None:
        workers = value.get("live_workers")
    if collectors is None:
        collectors = value.get("live_collectors")
    expected_workers = value.get("expected_workers")
    expected_collectors = value.get("expected_collectors")
    parts = [str(state)]
    if workers is not None:
        parts.append(f"workers {workers}/{expected_workers}" if expected_workers is not None else f"workers {workers}")
    if collectors is not None:
        parts.append(
            f"collectors {collectors}/{expected_collectors}"
            if expected_collectors is not None else f"collectors {collectors}"
        )
    return " · ".join(parts)[:450]


def _channels_text(report: dict[str, Any]) -> str:
    direct = report.get("channels_ua")
    if direct:
        return _text(direct, limit=850)
    channels = report.get("channels")
    if not isinstance(channels, (dict, list)):
        return _text(channels, limit=850)
    parts: list[str] = []
    if isinstance(channels, dict):
        iterator = channels.items()
    else:
        iterator = enumerate(channels, start=1)
    for key, raw in iterator:
        if isinstance(raw, dict):
            name = raw.get("name") or raw.get("channel") or key
            state = raw.get("state") or raw.get("status") or "—"
            detail = raw.get("reason") or raw.get("detail") or ""
            item = f"{name}: {state}"
            if detail:
                item += f" ({detail})"
        else:
            item = f"{key}: {raw}"
        parts.append(item)
    return "; ".join(parts)[:850] or "—"


def _database_text(report: dict[str, Any]) -> str:
    direct = report.get("database_ua") or report.get("db_ua")
    if direct:
        return _text(direct, limit=350)
    db = report.get("database") or report.get("db")
    if isinstance(db, dict):
        ok = db.get("ok")
        detail = str(db.get("detail") or "").strip()
        if ok is True:
            return "OK" + (f" · {detail}" if detail and detail.casefold() != "ok" else "")
        if ok is False:
            return "ПОМИЛКА" + (f" · {detail}" if detail else "")
    return _text(db, limit=350)


def _ai_text(report: dict[str, Any]) -> str:
    direct = report.get("ai_ua")
    if direct:
        return _text(direct, limit=450)
    ai = report.get("ai")
    if not isinstance(ai, dict):
        return _text(ai, limit=450)
    healthy = ai.get("healthy")
    total = ai.get("total")
    state = ai.get("state")
    blocked = ai.get("blocked_jobs")
    parts: list[str] = []
    if healthy is not None and total is not None:
        parts.append(f"{healthy}/{total} healthy")
    if state:
        parts.append(str(state))
    if blocked not in (None, 0, "0"):
        parts.append(f"blocked {blocked}")
    return " · ".join(parts) or "—"


def _queue_text(report: dict[str, Any]) -> str:
    direct = report.get("queue_ua")
    if direct:
        return _text(direct, limit=550)
    queue = report.get("queue")
    if not isinstance(queue, dict):
        return _text(queue, limit=550)
    labels = (
        ("active", "active"),
        ("due", "due"),
        ("ready", "ready"),
        ("waiting", "waiting"),
        ("recent_errors_10m", "errors/10m"),
    )
    parts = [f"{label} {queue[key]}" for key, label in labels if key in queue and queue[key] not in (None, "")]
    blockers = queue.get("blockers")
    if isinstance(blockers, dict) and blockers:
        blocked = ", ".join(f"{key}={value}" for key, value in blockers.items() if value)
        if blocked:
            parts.append(f"blockers {blocked}")
    return " · ".join(parts) or "—"


def _publications_text(report: dict[str, Any]) -> str:
    direct = report.get("publications_ua")
    if direct:
        return _text(direct, limit=400)
    pubs = report.get("publications")
    if isinstance(pubs, dict):
        parts: list[str] = []
        mapping = (("today", "сьогодні"), ("hour", "за годину"), ("total", "всього"), ("last", "остання"))
        for key, label in mapping:
            if key in pubs and pubs[key] not in (None, ""):
                parts.append(f"{label}: {pubs[key]}")
        return "; ".join(parts) or "—"
    return _text(pubs, limit=400)


def format_agent_report(report: dict[str, Any]) -> str:
    """Format a structured remote-agent payload into one compact Telegram report.

    A legacy preformatted ``message`` is intentionally handled by the caller.  This
    function is the stable structured contract for remote control from RC37 onward.
    Unknown extra fields are ignored, allowing the remote agent to evolve without
    requiring a local update for every diagnostic addition.
    """
    status_raw = str(report.get("status") or report.get("severity") or "OK").strip().upper()
    status = _STATUS_UA.get(status_raw, status_raw or "OK")
    version = _text(report.get("version"), default="невідомо", limit=64)
    generated = _text(report.get("generated_at") or report.get("timestamp"), default="—", limit=80)

    lines = [
        "Autopilot · Перевірка агента",
        f"Статус: {status}",
        f"Версія: {version}",
        f"Час: {generated}",
        f"Runtime: {_runtime_text(report)}",
        f"Канали: {_channels_text(report)}",
        f"База: {_database_text(report)}",
        f"AI: {_ai_text(report)}",
        f"Черга: {_queue_text(report)}",
        f"Публікації: {_publications_text(report)}",
        f"Виявлено: {_text(report.get('detected'), default='змін не потрібно', limit=700)}",
        f"Виправлено: {_text(report.get('fixed'), default='змін не потрібно', limit=700)}",
        f"Оновлення: {_text(report.get('update'), default='не потрібне', limit=500)}",
        f"Наступна дія: {_text(report.get('next_action'), default='наступна штатна перевірка', limit=500)}",
    ]
    return "\n".join(lines)[:3900]
