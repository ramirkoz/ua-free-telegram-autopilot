from __future__ import annotations

from telegram_autopilot import rc73_channel_weights_ui as rc73


def test_copy_weights_normalizes_and_keeps_operator_categories():
    items = rc73._copy_weights([
        {"name": " Дослідження ", "weight": 60},
        {"name": "Кейси", "weight": "40"},
        {"name": "", "weight": 10},
        {"name": "Заборонене", "weight": -5},
    ])
    assert items == [
        {"name": "Дослідження", "weight": 60.0},
        {"name": "Кейси", "weight": 40.0},
        {"name": "Заборонене", "weight": 0.0},
    ]


def test_rc73_save_persists_weights_on_the_same_channel(monkeypatch):
    calls = {}

    class FakeDB:
        def __init__(self):
            self._rc73_pending_weights = [
                {"name": "Глобальні кейси", "weight": 70},
                {"name": "Дослідження", "weight": 30},
            ]

        def set_channel_editorial_weights(self, channel_id, items):
            calls["saved"] = (channel_id, items)

    def previous(db, **kwargs):
        calls["kwargs"] = kwargs
        return 91

    monkeypatch.setattr(rc73, "_PREV_SAVE_CHANNEL", previous)
    db = FakeDB()
    channel_id = rc73._save_channel_rc73(db, name="manual-channel")

    assert channel_id == 91
    assert calls["saved"] == (
        91,
        [
            {"name": "Глобальні кейси", "weight": 70.0},
            {"name": "Дослідження", "weight": 30.0},
        ],
    )
    assert not hasattr(db, "_rc73_pending_weights")


def test_empty_weights_are_explicitly_saved_as_disabled_balance(monkeypatch):
    calls = {}

    class FakeDB:
        def __init__(self):
            self._rc73_pending_weights = []

        def set_channel_editorial_weights(self, channel_id, items):
            calls["saved"] = (channel_id, items)

    monkeypatch.setattr(rc73, "_PREV_SAVE_CHANNEL", lambda db, **kwargs: 12)
    db = FakeDB()
    assert rc73._save_channel_rc73(db, name="x") == 12
    assert calls["saved"] == (12, [])
