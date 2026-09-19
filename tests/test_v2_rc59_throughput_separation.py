from __future__ import annotations

from unittest.mock import patch

from telegram_autopilot.v2.domain import ChannelMode, DedupeProfile, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2.event_dedupe_guard import _entity_tokens, _scientific_names, event_fingerprint_same_event
from telegram_autopilot.v2.storage import V2Store


def test_scientific_names_require_local_taxonomy_context() -> None:
    false_text = "Researchers published a study about AI. Astra Model improves forecasting for cloud systems."
    assert "astra model" not in _scientific_names(false_text)
    true_text = "Researchers described a new species Homo sapiens in a taxonomy review."
    assert "homo sapiens" in _scientific_names(true_text)


def test_entity_tokens_ignore_single_title_case_prose() -> None:
    values = _entity_tokens("While Review These Every What September OpenAI OpenAI")
    assert not ({"while", "review", "these", "every", "what", "september"} & values)
    assert "openai" in values


def test_compound_event_needs_independent_anchor_at_rc58_false_positive_strength() -> None:
    stats = {
        "left_raw": "", "right_raw": "", "left": "", "right": "",
        "shared": {f"concept{i}" for i in range(24)},
        "containment": 0.28,
        "long_shared": {f"concept{i}" for i in range(12)},
        "numeric_pairs": [], "quantity_pairs": [], "duration_pairs": [],
        "shared_entities": set(), "shared_scientific": set(),
        "shared_actions": {"discover"},
        "shared_rare": {f"rareterm{i}" for i in range(12)},
    }
    with patch("telegram_autopilot.v2.event_dedupe_guard.semantic_same_event", return_value=(False, "topic only")), patch(
        "telegram_autopilot.v2.event_dedupe_guard._fingerprint_stats", return_value=stats
    ):
        same, reason = event_fingerprint_same_event({}, {}, compound_events=True, rare_terms=True)
    assert same is False
    assert "event fingerprint" in reason


def test_commercial_gate_thresholds_are_channel_tunable() -> None:
    value = {
        "commercial_mechanism": 50,
        "consumer_behavior": 50,
        "creative_execution": 50,
        "measurable_result": 50,
        "strategic_transferability": 50,
        "why_now": 50,
    }
    assert EditorialEngine._sold_value_allowed(value, 58)[0] is False
    tuning = {"case_fit_min":55,"case_score_min":46,"case_transfer_min":40,"case_anchor_min":48}
    allowed, lane, score = EditorialEngine._sold_value_allowed(value, 58, tuning)
    assert allowed is True
    assert lane == "commercial_case"
    assert score == 50


def test_rc59_migration_uses_profiles_not_channel_names(tmp_path) -> None:
    store = V2Store(tmp_path / "db.sqlite3")
    now = "2026-09-19T00:00:00+00:00"
    with store.connect() as con:
        con.execute("DELETE FROM meta WHERE key='rc59_channel_throughput_policy_v1'")
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,channel_mode,dedupe_profile,editorial_runtime_profile,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (91, "Будь-яка назва A", "", str(ChannelMode.EDITORIAL), str(DedupeProfile.SCIENTIFIC_NEWS), str(EditorialRuntimeProfile.STANDARD), now, now),
        )
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,channel_mode,dedupe_profile,editorial_runtime_profile,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (92, "Будь-яка назва B", "", str(ChannelMode.EDITORIAL), str(DedupeProfile.COMMERCIAL_EDITORIAL), str(EditorialRuntimeProfile.COMMERCIAL_EDITORIAL), now, now),
        )
        store._ensure_channel_throughput_settings(con)
        a = con.execute("SELECT * FROM channels WHERE id=91").fetchone()
        b = con.execute("SELECT * FROM channels WHERE id=92").fetchone()
    assert int(a["output_starvation_enabled"]) == 1
    assert int(a["output_starvation_hours"]) == 4
    assert int(a["output_starvation_min_processed"]) == 8
    assert int(b["output_starvation_enabled"]) == 1
    assert int(b["output_starvation_min_processed"]) == 6
    assert "commercial_gate" in str(b["editorial_weights_json"])
