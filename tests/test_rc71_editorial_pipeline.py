from __future__ import annotations

from types import SimpleNamespace

from telegram_autopilot import rc71_editorial_pipeline as rc71


def test_high_fit_reject_is_normalized_to_publish(monkeypatch) -> None:
    monkeypatch.setitem(
        rc71._PREV,
        "run_channel_fit",
        lambda _policy, _article, *, channel_id: (
            object(),
            {"decision": "reject", "fit_score": 82, "reason": "суперечливий старий вердикт", "angle": "", "topic_tags": []},
        ),
    )
    _result, data = rc71._run_channel_fit_rc71(object(), {"id": 9}, channel_id=3)
    assert data["decision"] == "publish"
    assert "CHANNEL_FIT_NORMALIZED" in data["reason"]


def test_low_fit_reject_stays_rejected(monkeypatch) -> None:
    monkeypatch.setitem(
        rc71._PREV,
        "run_channel_fit",
        lambda _policy, _article, *, channel_id: (
            object(),
            {"decision": "reject", "fit_score": 38, "reason": "wrong story type", "angle": "", "topic_tags": []},
        ),
    )
    _result, data = rc71._run_channel_fit_rc71(object(), {"id": 10}, channel_id=3)
    assert data["decision"] == "reject"


def test_freshness_is_not_a_hard_gate() -> None:
    assert rc71._never_hard_stale("2020-01-01T00:00:00+00:00", 24) is False
    assert rc71._never_hard_stale(None, 24) is False


def test_value_prompt_treats_age_as_soft_context(monkeypatch) -> None:
    monkeypatch.setitem(rc71._PREV, "value_prompt", lambda _article: "BASE")
    from telegram_autopilot import rc68_editorial_value as rc68
    monkeypatch.setattr(rc68, "_channel", lambda _cid: SimpleNamespace(max_age_hours=24))
    prompt = rc71._value_prompt_rc71({"channel_id": 5, "source_published_at": "2026-09-01T12:00:00+00:00"})
    assert "М'ЯКИЙ редакційний сигнал" in prompt
    assert "НЕ є причиною reject" in prompt
    assert "breaking/news" in prompt
    assert "кампанія, кейс, дослідження" in prompt


def test_deferred_media_exists_only_during_editorial_preparation(monkeypatch) -> None:
    from telegram_autopilot.media_pipeline import PreparedArticleMedia
    from telegram_autopilot import rc66_editorial_queue as rc66

    empty = PreparedArticleMedia(featured=None, body=[])
    monkeypatch.setitem(rc71._PREV, "prepare_media", lambda *a, **k: empty)
    channel = SimpleNamespace(channel_mode="editorial", id=7)
    rc71._CTX.service = None
    rc71._CTX.channel = channel
    rc71._CTX.article_id = None
    monkeypatch.setattr(rc66._CONTEXT, "preparing", True, raising=False)
    prepared = rc71._prepare_media_rc71("", [], title="story", article_text="text")
    assert prepared.telegram_hero is not None
    assert prepared.telegram_hero.url.startswith("https://rc71.invalid/")

    monkeypatch.setattr(rc66._CONTEXT, "preparing", False, raising=False)
    final = rc71._prepare_media_rc71("", [], title="story", article_text="text")
    assert final.telegram_hero is None
    assert final.telegram_direct_video is None


def test_monitoring_never_gets_deferred_editorial_media(monkeypatch) -> None:
    from telegram_autopilot.media_pipeline import PreparedArticleMedia
    from telegram_autopilot import rc66_editorial_queue as rc66

    empty = PreparedArticleMedia(featured=None, body=[])
    monkeypatch.setitem(rc71._PREV, "prepare_media", lambda *a, **k: empty)
    rc71._CTX.service = None
    rc71._CTX.channel = SimpleNamespace(channel_mode="monitoring", id=8)
    rc71._CTX.article_id = None
    monkeypatch.setattr(rc66._CONTEXT, "preparing", True, raising=False)
    prepared = rc71._prepare_media_rc71("", [], title="monitor", article_text="text")
    assert prepared.telegram_hero is None
