from __future__ import annotations

import json
from datetime import datetime, timedelta

from telegram_autopilot import ai_router as legacy_ai
from telegram_autopilot.v2.ai_gateway import (
    _codex_retry_after_seconds,
    _compact_local_prompt,
    _failure_meta,
)
from telegram_autopilot.v2.domain import ProviderState
from telegram_autopilot.v2.update_protocol import UpdateProtocol


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def test_codex_usage_limit_uses_advertised_reset_time() -> None:
    target = (datetime.now().astimezone() + timedelta(hours=3)).replace(second=0, microsecond=0)
    rendered = f"{target.strftime('%b')} {_ordinal(target.day)}, {target.year} {target.strftime('%I:%M %p').lstrip('0')}"
    seconds = _codex_retry_after_seconds(f"You've hit your usage limit. Try again at {rendered}.")
    assert 2 * 3600 < seconds < 4 * 3600


def test_account_usage_limit_can_cool_down_longer_than_one_day() -> None:
    exc = legacy_ai.AIModelError("You've hit your usage limit", kind="quota", retry_after=3 * 24 * 3600)
    state, seconds, scope = _failure_meta(exc)
    assert state == ProviderState.QUOTA
    assert scope == "model"
    assert seconds == 3 * 24 * 3600


def test_local_cpu_prompt_is_bounded_but_keeps_front_and_tail() -> None:
    prompt = "INSTRUCTIONS:" + ("A" * 5000) + "\nSOURCE:" + ("B" * 5000) + "\nOUTPUT_RULES:END"
    compact = _compact_local_prompt(prompt, limit=5200)
    assert len(compact) <= 5200
    assert compact.startswith("INSTRUCTIONS:")
    assert compact.endswith("OUTPUT_RULES:END")
    assert "локальний CPU-контекст скорочено" in compact


def test_drive_duplicate_request_cannot_hide_newer_release(tmp_path) -> None:
    root = tmp_path / "local"
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    old = {
        "request_id": "release-rc40-old",
        "target_version": "2.0.0-rc40",
        "sha256": "1" * 64,
        "created_at": "2026-09-15T10:00:00+03:00",
        "source": "test",
    }
    new = {
        "request_id": "release-rc42-new",
        "target_version": "2.0.0-rc42",
        "sha256": "2" * 64,
        "created_at": "2026-09-15T11:00:00+03:00",
        "source": "test",
    }
    (mirror / "update_request.json").write_text(json.dumps(old), encoding="utf-8")
    (mirror / "update_request (1).json").write_text(json.dumps(new), encoding="utf-8")

    protocol = UpdateProtocol(root)
    request = protocol.accept_mirror_request(str(mirror))

    assert request is not None
    assert request.target_version == "2.0.0-rc42"
    assert request.request_id == "release-rc42-new"
    saved = protocol.load_request()
    assert saved is not None and saved.target_version == "2.0.0-rc42"
