from __future__ import annotations

from types import SimpleNamespace


def _reaction(emoji: str, chosen: bool = True):
    return SimpleNamespace(
        reaction=SimpleNamespace(emoticon=emoji),
        chosen=chosen,
        chosen_order=0 if chosen else None,
    )


def _message(message_id: int, *emoji: str):
    return SimpleNamespace(
        id=message_id,
        views=10,
        forwards=1,
        replies=SimpleNamespace(replies=0),
        reactions=SimpleNamespace(results=[_reaction(value) for value in emoji]),
    )


class FakeDB:
    def __init__(self):
        self.saved = []

    def rc51_feedback_candidates(self, channel_id: int, *, limit: int):
        return [
            {
                "article_id": channel_id * 100 + 1,
                "telegram_message_id": str(channel_id * 10 + 1),
                "published_at": "2026-08-30T12:00:00+00:00",
            }
        ]

    def rc51_save_feedback(self, **kwargs):
        self.saved.append(kwargs)


def _secrets():
    return SimpleNamespace(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_user_session="session",
    )


def test_rc56_two_sequential_channels_use_same_bounded_transport(monkeypatch):
    import telegram_autopilot.rc56_reaction_runtime as rc56

    monkeypatch.setattr(rc56, "load_secrets", _secrets)
    calls = []

    def fake_run_fetch(**kwargs):
        calls.append((kwargs["target"], list(kwargs["ids"])))
        message_id = kwargs["ids"][0]
        return [_message(message_id, "👍", "🔥")]

    monkeypatch.setattr(rc56, "_run_fetch", fake_run_fetch)
    db = FakeDB()
    ch1 = SimpleNamespace(id=1, name="CTRL+UA", telegram_chat_id="@ctrlua")
    ch2 = SimpleNamespace(id=2, name="ПРОДАНО!", telegram_chat_id="@prodano")

    first = rc56.refresh_feedback_metrics_rc56(db, ch1, force=True)
    second = rc56.refresh_feedback_metrics_rc56(db, ch2, force=True)

    assert first["error"] == ""
    assert second["error"] == ""
    assert first["saved"] == 1
    assert second["saved"] == 1
    assert calls == [("ctrlua", [11]), ("prodano", [21])]
    assert [row["channel_id"] for row in db.saved] == [1, 2]
    assert all(row["likes"] == 1 and row["fires"] == 1 for row in db.saved)


def test_rc56_timeout_is_visible_and_bounded(monkeypatch):
    import telegram_autopilot.rc56_reaction_runtime as rc56

    monkeypatch.setattr(rc56, "load_secrets", _secrets)
    monkeypatch.setattr(rc56, "_run_fetch", lambda **kwargs: (_ for _ in ()).throw(TimeoutError()))
    db = FakeDB()
    channel = SimpleNamespace(id=1, name="CTRL+UA", telegram_chat_id="@ctrlua")

    result = rc56.refresh_feedback_metrics_rc56(db, channel, force=True)

    assert result["saved"] == 0
    assert "30 с" in result["error"]
    assert "розблоковано" in result["error"]


def test_rc56_installer_rebinds_all_stale_refresh_symbols(monkeypatch):
    import telegram_autopilot.rc48_learning as rc48_learning
    import telegram_autopilot.rc48_ui as rc48_ui
    import telegram_autopilot.rc51_feedback as rc51_feedback
    import telegram_autopilot.rc51_ui as rc51_ui
    import telegram_autopilot.rc54_mtproto as rc54
    import telegram_autopilot.rc56_reaction_runtime as rc56
    from telegram_autopilot.ui import MainWindow

    monkeypatch.setattr(rc56, "_INSTALLED", False)
    rc56.install_rc56_reaction_runtime()

    assert rc48_learning.refresh_channel_metrics is rc56.refresh_feedback_metrics_rc56
    assert rc48_ui.refresh_channel_metrics is rc56.refresh_feedback_metrics_rc56
    assert rc51_feedback.refresh_feedback_metrics is rc56.refresh_feedback_metrics_rc56
    assert rc51_ui.refresh_feedback_metrics is rc56.refresh_feedback_metrics_rc56
    assert rc54.refresh_feedback_metrics_rc54 is rc56.refresh_feedback_metrics_rc56
    assert MainWindow._rc48_refresh_metrics_now is rc56.refresh_metrics_now_rc56


def test_rc56_refresh_does_not_call_reaction_policy_writer(monkeypatch):
    import telegram_autopilot.rc51_feedback as rc51
    import telegram_autopilot.rc56_reaction_runtime as rc56

    monkeypatch.setattr(rc56, "load_secrets", _secrets)
    monkeypatch.setattr(
        rc51,
        "_try_limit_channel_reactions",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must stay read-only")),
    )
    monkeypatch.setattr(
        rc56,
        "_run_fetch",
        lambda **kwargs: [_message(kwargs["ids"][0], "👎")],
    )
    db = FakeDB()
    channel = SimpleNamespace(id=3, name="ПРОДАНО!", telegram_chat_id="@prodano")

    result = rc56.refresh_feedback_metrics_rc56(db, channel, force=True)

    assert result["error"] == ""
    assert db.saved[0]["dislikes"] == 1
