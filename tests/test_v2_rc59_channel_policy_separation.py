from pathlib import Path

from telegram_autopilot.v2.domain import ChannelConfig
from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2.event_dedupe_guard import _scientific_names


def test_scientific_name_validator_rejects_ordinary_english_pairs() -> None:
    text = (
        "Researchers discuss American hope and Astra model in a science podcast. "
        "Great science coverage says Subscriptions keep growing."
    )
    assert _scientific_names(text, require_local_context=True) == set()


def test_scientific_name_validator_accepts_real_local_binomial() -> None:
    text = "Researchers described a new species Panthera leo in a taxonomic study."
    assert "panthera leo" in _scientific_names(text, require_local_context=True)


def test_commercial_value_thresholds_are_channel_configurable() -> None:
    data = {
        "commercial_mechanism": 57,
        "consumer_behavior": 55,
        "creative_execution": 50,
        "measurable_result": 55,
        "strategic_transferability": 42,
        "why_now": 45,
    }
    allowed_default, _, _ = EditorialEngine._sold_value_allowed(data, 62, {})
    allowed_channel, lane, _ = EditorialEngine._sold_value_allowed(
        data,
        62,
        {
            "commercial_case_min_score": 45,
            "commercial_case_min_transferability": 40,
            "commercial_case_anchor_min": 55,
        },
    )
    assert not allowed_default
    assert allowed_channel
    assert lane == "commercial_case"


def test_channel_config_owns_runtime_behavior_settings() -> None:
    cfg = ChannelConfig(id=1, name="Any channel", telegram_chat_id="@any")
    assert cfg.dedupe_settings_json == "{}"
    assert cfg.editorial_value_settings_json == "{}"
    assert cfg.output_starvation_enabled is False
    assert cfg.output_starvation_hours == 6
    assert cfg.output_starvation_min_processed == 20


def test_runtime_has_no_named_channel_branches() -> None:
    for path in (
        "telegram_autopilot/v2/event_dedupe_guard.py",
        "telegram_autopilot/v2/editorial.py",
        "telegram_autopilot/v2/supervisor.py",
    ):
        text = Path(path).read_text(encoding="utf-8").casefold()
        assert "ctrl+ua" not in text
        assert "ctrlua" not in text
        assert "продано" not in text
