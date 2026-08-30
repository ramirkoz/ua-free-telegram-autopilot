from __future__ import annotations

import asyncio
import queue
import sys
import types
from types import SimpleNamespace


def _row(**kwargs):
    base = {
        "title": "AI chip launch",
        "raw_text": "A new AI chip launches for datacenters",
        "event_summary": "AI chip launch",
        "teaser_text": "Новий AI-чип для датацентрів.",
        "published_at": "2026-08-30T12:00:00+00:00",
        "checked_at": "2026-08-30T12:00:00+00:00",
        "likes": 0,
        "dislikes": 0,
        "fires": 0,
        "views": 1000,
        "forwards": 0,
        "replies": 0,
        "audience_positive": 0,
        "audience_negative": 0,
        "audience_fires": 0,
        "audience_other": 0,
        "audience_total": 0,
        "source_id": 1,
    }
    base.update(kwargs)
    return base


def test_rc57_audience_can_soft_boost_but_never_hard_suppress(monkeypatch):
    import telegram_autopilot.rc51_feedback as rc51
    import telegram_autopilot.rc57_scoring as rc57

    monkeypatch.setattr(
        rc57,
        "_BASE_SCORE",
        lambda article, rows: rc51.FeedbackScore(0.0, 0.0, 0.0, False, 0, 0.0, 0.0, 0),
    )
    article = _row(source_id=9)
    strong = _row(
        views=1000,
        forwards=20,
        replies=10,
        audience_positive=80,
        audience_fires=20,
        audience_total=100,
        source_id=9,
    )
    weak = _row(
        title="Unrelated baseline",
        raw_text="Unrelated baseline story",
        views=1000,
        audience_positive=1,
        audience_total=1,
        source_id=2,
    )

    score = rc57.combined_score_against_feedback(article, [strong, weak])
    assert score.score > 0
    assert score.hard_suppress is False

    bad = _row(
        views=1000,
        audience_negative=100,
        audience_total=100,
        source_id=9,
    )
    score2 = rc57.combined_score_against_feedback(article, [bad, weak])
    assert score2.score < 0
    assert score2.hard_suppress is False


def test_rc57_editor_dislike_remains_only_hard_veto_path(monkeypatch):
    import telegram_autopilot.rc51_feedback as rc51
    import telegram_autopilot.rc52_feedback as rc52
    import telegram_autopilot.rc57_scoring as rc57

    old_signal = rc51._feedback_signal
    try:
        rc51._feedback_signal = rc52.topic_feedback_signal
        monkeypatch.setattr(rc57, "_BASE_SCORE", rc51.score_against_feedback)
        article = _row()
        disliked = _row(dislikes=1, fires=1, audience_positive=500, audience_total=500, views=1000)
        score = rc57.combined_score_against_feedback(article, [disliked])
        assert score.hard_suppress is True
    finally:
        rc51._feedback_signal = old_signal


def test_rc57_scan_admin_reactors_filters_readers_and_keeps_multi_reaction(monkeypatch):
    import telegram_autopilot.rc57_telegram_feedback as rc57

    telethon = types.ModuleType("telethon")
    functions = SimpleNamespace(messages=SimpleNamespace(GetMessageReactionsListRequest=lambda **kwargs: kwargs))
    utils = SimpleNamespace(get_peer_id=lambda peer: int(peer.id))
    telethon.functions = functions
    telethon.utils = utils
    monkeypatch.setitem(sys.modules, "telethon", telethon)

    class Client:
        async def __call__(self, request):
            return SimpleNamespace(
                reactions=[
                    SimpleNamespace(peer_id=SimpleNamespace(id=10), reaction=SimpleNamespace(emoticon="👍")),
                    SimpleNamespace(peer_id=SimpleNamespace(id=99), reaction=SimpleNamespace(emoticon="👎")),
                    SimpleNamespace(peer_id=SimpleNamespace(id=10), reaction=SimpleNamespace(emoticon="🔥")),
                ],
                next_offset=None,
            )

    found, scanned, complete = asyncio.run(
        rc57.scan_admin_reactors(
            Client(),
            input_peer=object(),
            message_id=123,
            admin_ids={10, 11},
            channel_peer_id=-10077,
        )
    )
    assert found == {10: {"👍", "🔥"}}
    assert scanned == 3
    assert complete is True


def test_rc57_fault_tolerant_queue_accepts_legacy_callback_and_keeps_pump_alive():
    import telegram_autopilot.rc57_ui as rc57
    from telegram_autopilot.ui import MainWindow

    rc57.install_fault_tolerant_ui_queue()
    events = []

    class Root:
        def after(self, delay, callback):
            events.append((delay, callback))
            return "after-id"

    fake = SimpleNamespace(_closing=False, _ui_queue=queue.Queue(), root=Root())
    fake._drain_ui_queue = lambda: None
    called = []
    fake._ui_queue.put(lambda: called.append("legacy"))
    fake._ui_queue.put((lambda value: called.append(value), ("tuple",), {}))

    MainWindow._drain_ui_queue(fake)

    assert called == ["legacy", "tuple"]
    assert events, "queue pump must always schedule its next drain"


def test_rc57_manual_refresh_posts_finish_through_mainwindow_post_ui(monkeypatch):
    import telegram_autopilot.rc57_ui as rc57

    channel = SimpleNamespace(id=2, name="ПРОДАНО!", telegram_chat_id="@prodano")

    class DB:
        def get_channel(self, channel_id):
            return channel

    class Status:
        def __init__(self):
            self.value = ""
        def set(self, value):
            self.value = value

    posted = []
    status = Status()
    main = SimpleNamespace(
        current_channel_id=2,
        db=DB(),
        root=object(),
        rc57_feedback_status=status,
        _post_ui=lambda callback, *args, **kwargs: posted.append((callback, args, kwargs)),
        _rc48_refresh_memory=lambda: None,
    )
    monkeypatch.setattr(
        rc57,
        "refresh_feedback_metrics_rc57",
        lambda *args, **kwargs: {
            "configured": True, "checked": 3, "saved": 3, "error": "", "elapsed": 0.1,
            "admin_count": 2, "editor_coverage": "all_admins", "warning": "",
        },
    )

    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()

    monkeypatch.setattr(rc57.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(rc57.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(rc57.messagebox, "showwarning", lambda *args, **kwargs: None)

    rc57.refresh_metrics_now_rc57(main)
    assert posted, "worker must return through MainWindow._post_ui"
    callback, args, kwargs = posted[-1]
    callback(*args, **kwargs)
    assert getattr(main, rc57._INFLIGHT_ATTR) is False


def test_rc57_database_feedback_rows_include_audience_only_and_source_id(tmp_path):
    import telegram_autopilot.rc51_feedback as rc51
    import telegram_autopilot.rc57_feedback_db as rc57db
    from telegram_autopilot.database import Database, now_iso

    rc57db._PATCHED = False
    rc57db.install_database_patch()
    db = Database(tmp_path / "feedback.db")
    channel_id = db.save_channel(
        channel_id=None, name="T", telegram_chat_id="@t", editorial_profile="", enabled=True,
        include_source_link=False, poll_interval_minutes=5, min_publish_interval_minutes=0,
        dedupe_window_hours=72, max_age_hours=24, max_posts_per_cycle=1,
    )
    source_id = db.save_source(source_id=None, channel_id=channel_id, kind="rss", name="S", url="https://x.test/feed", enabled=True)
    stamp = now_iso()
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,
                   source_published_at,discovered_at,status,published_at,telegram_message_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (channel_id, source_id, "x1", "Audience only", "https://x.test/a", "https://x.test/a",
             "Audience only story", "h1", stamp, stamp, "published", stamp, "101"),
        )
        article_id = int(cur.lastrowid)
        con.execute(
            """INSERT INTO telegram_feedback(article_id,channel_id,telegram_message_id,checked_at,published_at,
                   views,forwards,replies,likes,dislikes,fires,other_reactions,audience_total,audience_positive)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (article_id, channel_id, "101", stamp, stamp, 1000, 3, 0, 0, 0, 0, 0, 25, 25),
        )

    rows = db.rc51_feedback_rows(channel_id)
    assert len(rows) == 1
    assert rows[0]["source_id"] == source_id
    assert rows[0]["audience_total"] == 25
