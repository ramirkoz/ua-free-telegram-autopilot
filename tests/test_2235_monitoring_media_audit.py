"""Release 2.2.35 monitoring source-media evidence and video-probe efficiency."""
import json
from types import SimpleNamespace

from telegram_autopilot.v2 import strict_ingest as strict
from telegram_autopilot.v2.ingest import TelegramEntry
from telegram_autopilot.v2.monitoring_media_audit_235 import summarize_monitoring_media_provenance


def _row(article_id, source, *, unresolved=(), records=(), stitched=False):
    return {
        "id": article_id,
        "source_url": source,
        "article_layout_json": json.dumps({"telegram": {
            "unresolved_nearby_media_v1": list(unresolved),
            "source_message_records_v1": list(records),
            "stitched": stitched,
        }}),
    }


def test_unverified_media_is_diagnostic_only_and_bounded():
    rows = [
        _row(5, "https://t.me/official/105", unresolved=[
            {"post": "official/104", "media_count": 3, "seconds_apart": 12, "video_seen": False},
            {"post": "official/104", "media_count": 3},  # duplicate candidate
            {"post": "official/106", "media_count": 1, "seconds_apart": 30},
        ]),
        _row(6, "https://t.me/official/106", unresolved=[
            {"post": "official/104", "media_count": 2, "seconds_apart": 40},
        ]),
        _row(7, "https://t.me/official/107", stitched=True, records=[
            {"post": "official/107"}, {"post": "official/102"},
        ]),
        {"id": 8, "source_url": "https://t.me/official/108", "article_layout_json": "BROKEN"},
    ]
    out = summarize_monitoring_media_provenance(rows, sample_limit=1)
    assert out["unverified_articles_60m"] == 2
    assert out["unverified_candidates_60m"] == 3
    assert out["verified_split_articles_60m"] == 1
    assert out["ownership_inferred_from_proximity"] is False
    assert len(out["sample"]) == 1
    assert out["sample"][0]["nearby_post"] == "official/104"
    assert out["sample"][0]["reason"] == "UNVERIFIED_NEARBY_MEDIA_NOT_ATTACHED"


def test_nearby_posts_do_not_become_publishable_by_telemetry():
    out = summarize_monitoring_media_provenance([_row(
        99, "https://t.me/source/99",
        unresolved=[{"post": "source/98", "media_count": 4, "seconds_apart": 1}],
    )])
    assert out["verified_split_articles_60m"] == 0
    assert out["unverified_articles_60m"] == 1


def _video_post():
    return TelegramEntry(
        post="cache_fixture_2235/55",
        text="Місцева подія сталася в громаді.",
        published="2026-10-25T10:00:00+00:00",
        media=[], video_attachment_seen=True,
        video_poster_url="https://cdn.example.org/still.jpg",
    )


def test_negative_video_probe_deduplicates_exact_fetch_and_expires(monkeypatch):
    strict._EXACT_VIDEO_NEGATIVE_UNTIL.clear()
    now = [10.0]
    calls = []
    monkeypatch.setattr(strict.time, "monotonic", lambda: now[0])

    def fake_fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(body=b"<html>same exact post</html>")

    class Parser:
        def __init__(self, username):
            self.entries = [SimpleNamespace(post="cache_fixture_2235/55", media=[])]
        def feed(self, body): pass
        def close(self): pass

    monkeypatch.setattr(strict.collector, "_source_fetch", fake_fetch)
    monkeypatch.setattr(strict, "StrictTelegramParser", Parser)
    try:
        assert strict._hydrate_exact_video_post("cache_fixture_2235", _video_post()).video_recovery == "poster_fallback"
        assert strict._hydrate_exact_video_post("cache_fixture_2235", _video_post()).video_recovery == "poster_fallback"
        assert len(calls) == 1
        now[0] += strict._EXACT_VIDEO_NEGATIVE_TTL_S + 1
        strict._hydrate_exact_video_post("cache_fixture_2235", _video_post())
        assert len(calls) == 2
    finally:
        strict._EXACT_VIDEO_NEGATIVE_UNTIL.clear()


def test_network_failures_never_enter_video_negative_cache(monkeypatch):
    strict._EXACT_VIDEO_NEGATIVE_UNTIL.clear()
    calls = []

    def unavailable(url, **kwargs):
        calls.append(url)
        raise RuntimeError("temporary TLS error")

    monkeypatch.setattr(strict.collector, "_source_fetch", unavailable)
    strict._hydrate_exact_video_post("cache_fixture_2235", _video_post())
    strict._hydrate_exact_video_post("cache_fixture_2235", _video_post())
    assert len(calls) == 2
    assert strict._EXACT_VIDEO_NEGATIVE_UNTIL == {}
