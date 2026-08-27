from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.ai_router import AIRouterError
from telegram_autopilot.rc42_policy import serialize_editorial_weights
from telegram_autopilot import rc46_policy as rc46
from telegram_autopilot import rc46_transport as transport


def channel(weights, *, min_gap=10):
    return SimpleNamespace(
        id=1,
        name="CTRL+UA",
        editorial_profile="Current technology and science news. No evergreen filler.",
        editorial_weights_json=serialize_editorial_weights(weights),
        min_publish_interval_minutes=min_gap,
    )


def article(title="A current story", raw="Current factual source text without literal category labels.", article_id=501):
    return {
        "id": article_id,
        "title": title,
        "raw_text": raw,
        "editorial_category": "",
        "published_at": "",
    }


def test_rc46_category_parser_normalizes_ampersand_and_and():
    categories = [
        {"name": "AI Models & Agents", "weight": 60},
        {"name": "Science & Health", "weight": 40},
    ]
    assert rc46.extract_category_rc46("Science and Health", categories) == "Science & Health"
    assert rc46.extract_category_rc46('{"category":"AI Models and Agents"}', categories) == "AI Models & Agents"
    assert rc46.extract_category_rc46("Category: Science & Health", categories) == "Science & Health"


def test_rc46_category_parser_accepts_unambiguous_minor_variation():
    categories = [
        {"name": "Robotics & Physical AI", "weight": 60},
        {"name": "Cybersecurity & Privacy", "weight": 40},
    ]
    assert rc46.extract_category_rc46("Robotics and Physical A.I.", categories) == "Robotics & Physical AI"


def test_rc46_classifier_outage_is_degraded_pass_and_never_calls_local(monkeypatch):
    categories = [{"name": "AI Models & Agents", "weight": 100}]
    seen = {}

    def fail(*_args, **kwargs):
        seen.update(kwargs)
        raise AIRouterError("temporary provider outage")

    monkeypatch.setattr(rc46, "run_ai", fail)
    # Force semantic path rather than the lexical shortcut.
    from telegram_autopilot import rc45_policy
    monkeypatch.setattr(rc45_policy, "lexical_category", lambda *_args, **_kwargs: "")

    result = rc46.classify_category_rc46(channel(categories), article(), categories)
    assert result == rc46._UNCLASSIFIED
    assert "local" not in seen["allowed_providers"]
    assert "local" in seen["skip_providers"]
    assert seen["task_timeout_seconds"] <= 12

    reason, category = rc46.balance_reject_reason_rc46(
        channel(categories), article(), [], category=result
    )
    assert reason == ""
    assert category == ""


def test_rc46_explicit_other_still_rejects_editorially():
    weights = [{"name": "AI Models & Agents", "weight": 100}]
    reason, category = rc46.balance_reject_reason_rc46(
        channel(weights), article(), [], category=rc46._OTHER
    )
    assert reason.startswith("EDITORIAL_FIT_RC46_SKIP")
    assert category == rc46._OTHER


def _recent(category: str, minutes_ago: int, count: int = 8):
    base = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    rows = []
    for index in range(count):
        rows.append({
            "published_at": (base - timedelta(minutes=index)).isoformat(),
            "editorial_category": category,
        })
    return rows


def test_rc46_balance_rejects_overweight_category_when_feed_is_active():
    weights = [
        {"name": "Science & Health", "weight": 10},
        {"name": "AI Models & Agents", "weight": 90},
    ]
    reason, category = rc46.balance_reject_reason_rc46(
        channel(weights, min_gap=10),
        article(),
        _recent("Science & Health", minutes_ago=5),
        category="Science & Health",
    )
    assert reason.startswith("EDITORIAL_WEIGHT_RC46_SKIP")
    assert category == "Science & Health"


def test_rc46_balance_has_starvation_escape_after_long_silence():
    weights = [
        {"name": "Science & Health", "weight": 10},
        {"name": "AI Models & Agents", "weight": 90},
    ]
    reason, category = rc46.balance_reject_reason_rc46(
        channel(weights, min_gap=10),
        article(),
        _recent("Science & Health", minutes_ago=60),
        category="Science & Health",
    )
    assert reason == ""
    assert category == "Science & Health"


def test_rc46_zero_weight_remains_hard_disabled_even_when_starved():
    weights = [
        {"name": "Science & Health", "weight": 0},
        {"name": "AI Models & Agents", "weight": 100},
    ]
    reason, category = rc46.balance_reject_reason_rc46(
        channel(weights), article(), _recent("Science & Health", minutes_ago=120), category="Science & Health"
    )
    assert reason.startswith("EDITORIAL_WEIGHT_RC46_SKIP")
    assert category == "Science & Health"


def test_rc46_browser_cleanup_failure_is_best_effort(monkeypatch, tmp_path):
    calls = {"count": 0}

    def flaky(_path, ignore_errors=False):
        calls["count"] += 1
        if not ignore_errors:
            raise OSError(145, "directory not empty")

    monkeypatch.setattr(transport.shutil, "rmtree", flaky)
    monkeypatch.setattr(transport.time, "sleep", lambda _seconds: None)
    transport._cleanup_tree_best_effort(tmp_path / "profile")
    assert calls["count"] == 5
