from __future__ import annotations

from contextlib import contextmanager
import sqlite3

from telegram_autopilot import rc59_universal_policy as rc59
from telegram_autopilot import rc72_channel_policy_ui as ui72
from telegram_autopilot import rc72_monitoring_policy as mon72


def test_monitoring_labels_are_channel_specific_and_no_editorial_value_gate():
    labels = ui72._mode_labels("monitoring")
    assert "включати" in labels["selection"].casefold()
    assert "виключати" in labels["rejection"].casefold()
    assert "не використовує" in labels["rejection_hint"].casefold()


def test_rc72_save_persists_manual_policy_and_replaces_hidden_profile(monkeypatch):
    captured = {}

    class FakeDB:
        def __init__(self):
            self._rc72_pending_policy = rc59.ChannelPolicy(
                purpose="Моніторинг конкретної громади",
                selection_rules="Брати лише згадки громади та її населених пунктів.",
                rejection_rules="Не брати випадкові однойменні сутності.",
            )
            self.saved = None

        def rc59_save_channel_policy(self, policy):
            self.saved = policy

    def previous(db, **kwargs):
        captured.update(kwargs)
        return 17

    monkeypatch.setattr(ui72, "_PREV_SAVE_CHANNEL", previous)
    db = FakeDB()
    channel_id = ui72._save_channel_rc72(db, name="X", editorial_profile="hidden generic default")

    assert channel_id == 17
    assert captured["editorial_profile"] == "Моніторинг конкретної громади"
    assert db.saved is not None
    assert db.saved.channel_id == 17
    assert db.saved.selection_rules.startswith("Брати лише")
    assert not hasattr(db, "_rc72_pending_policy")


def test_monitoring_rules_are_used_only_after_explicit_policy_save(monkeypatch):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE channel_policies(channel_id INTEGER PRIMARY KEY, selection_rules TEXT, rejection_rules TEXT)")

    class FakeDB:
        @contextmanager
        def connect(self):
            yield con

    from telegram_autopilot import rc51_feedback as rc51

    old = rc51._ACTIVE_DB
    rc51._ACTIVE_DB = FakeDB()
    try:
        assert mon72._saved_rules(5) is None
        con.execute(
            "INSERT INTO channel_policies(channel_id,selection_rules,rejection_rules) VALUES(?,?,?)",
            (5, "Лише Запоріжжя", "Без спорту"),
        )
        con.commit()
        assert mon72._saved_rules(5) == ("Лише Запоріжжя", "Без спорту")
    finally:
        rc51._ACTIVE_DB = old
        con.close()


def test_generic_policy_defaults_do_not_turn_into_monitoring_filters():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE channel_policies(channel_id INTEGER PRIMARY KEY, selection_rules TEXT, rejection_rules TEXT)")
    generic = rc59.ChannelPolicy()
    con.execute(
        "INSERT INTO channel_policies(channel_id,selection_rules,rejection_rules) VALUES(?,?,?)",
        (8, generic.selection_rules, generic.rejection_rules),
    )
    con.commit()

    class FakeDB:
        @contextmanager
        def connect(self):
            yield con

    from telegram_autopilot import rc51_feedback as rc51

    old = rc51._ACTIVE_DB
    rc51._ACTIVE_DB = FakeDB()
    try:
        assert mon72._saved_rules(8) == ("", "")
    finally:
        rc51._ACTIVE_DB = old
        con.close()
