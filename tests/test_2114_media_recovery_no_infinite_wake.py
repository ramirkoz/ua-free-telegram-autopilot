"""Regression: stale source refresh must not re-activate a media-blocked READY story."""
import json
from telegram_autopilot.v2.storage import V2Store


def test_identical_media_snapshot_does_not_wake_permanent_ready(tmp_path):
    store = V2Store(tmp_path / "autopilot.sqlite3")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(2,'Editor','@target','editorial','now','now')")
        con.execute("INSERT INTO sources(id,channel_id,name,url,created_at,updated_at) VALUES(131,2,'Test Source','https://example.test/feed','now','now')")
    kw = dict(channel_id=2, source_id=131, external_id="item-7", title="Test",
              source_url="https://example.test/story-7", raw_text="Text", media_json=json.dumps(["https://example.test/img7.jpg"]),
              article_layout_json="{}")
    aid = store.insert_collected(**kw)
    store.update_article(aid, stage="READY", decision="PUBLISH",
                         blocked_by="MEDIA", last_error_code="MEDIA_REQUIRED", next_retry_at="")
    assert store.insert_collected(**kw) == aid
    row = store.get_article(aid)
    assert row["blocked_by"] == "MEDIA"
    assert row["last_error_code"] == "MEDIA_REQUIRED"


def test_new_media_snapshot_wakes_permanent_ready(tmp_path):
    store = V2Store(tmp_path / "autopilot.sqlite3")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(2,'Editor','@target','editorial','now','now')")
        con.execute("INSERT INTO sources(id,channel_id,name,url,created_at,updated_at) VALUES(131,2,'Test Source','https://example.test/feed','now','now')")
    kw = dict(channel_id=2, source_id=131, external_id="item-7", title="Test",
              source_url="https://example.test/story-7", raw_text="Text",
              media_json=json.dumps(["https://example.test/img7.jpg"]), article_layout_json="{}")
    aid = store.insert_collected(**kw)
    store.update_article(aid, stage="READY", decision="PUBLISH",
                         blocked_by="MEDIA", last_error_code="MEDIA_REQUIRED", next_retry_at="")
    kw["media_json"] = json.dumps(["https://example.test/img7.jpg", "https://example.test/new.jpg"])
    store.insert_collected(**kw)
    row = store.get_article(aid)
    assert row["blocked_by"] == "NONE"
