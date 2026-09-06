from pathlib import Path

from telegram_autopilot import rc75_channel_settings_ui as rc75
from telegram_autopilot.rc59_universal_policy import ChannelPolicy


def test_rc75_weights_signature_is_stable_and_numeric():
    items = [
        {"name": " Technology ", "weight": 22},
        {"name": "Science", "weight": "20.0"},
        {"name": "", "weight": 99},
        {"name": "Broken", "weight": "nope"},
    ]
    assert rc75._weights_signature(items) == (("Technology", 22.0), ("Science", 20.0))


def test_rc75_policy_signature_tracks_every_operator_owned_field():
    policy = ChannelPolicy(
        channel_id=7,
        enabled=True,
        purpose="Mission",
        audience="Audience",
        selection_rules="Include",
        rejection_rules="Reject",
        writing_rules="Write",
        style_rules="Style",
        positive_examples="Good",
        negative_examples="Bad",
        extra_instructions="Extra",
        selector_extra_prompt="Selector",
        writer_extra_prompt="Writer",
        media_policy="preferred",
        target_min_chars=300,
        target_max_chars=800,
    )
    first = rc75._policy_signature(policy)
    policy.writer_extra_prompt = "Changed"
    second = rc75._policy_signature(policy)
    assert first != second


def test_rc75_ui_layer_is_channel_neutral():
    source = Path("telegram_autopilot/rc75_channel_settings_ui.py").read_text(encoding="utf-8")
    assert "CTRL+UA" not in source
    assert "ПРОДАНО" not in source
    assert "@ctrlua" not in source
    assert "marketing" not in source.casefold()


def test_rc75_install_is_after_rc74_runtime():
    source = Path("telegram_autopilot/main.py").read_text(encoding="utf-8")
    assert source.index("install_rc74_universal_runtime()") < source.index("install_rc75_channel_settings_ui()")
