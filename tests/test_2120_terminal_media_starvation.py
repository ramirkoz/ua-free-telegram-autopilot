"""Regression for LIVE 2.1.19 channel-2 perpetual MEDIA_REQUIRED loop."""
import json
from telegram_autopilot.v2.storage import V2Store


def _insert(store, url):
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(2,'ПРОДАНО!','@ads','editorial','now','now')")
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url) VALUES(131,2,'rss','TrendHunter','https://example.test/feed')")
    return store.insert_collected(channel_id=2,source_id=131,external_id="trend-57655",
        title="Chocolate squares",source_url=url,raw_text="Chocolate squares, pistachio and crisps",
        media_json=json.dumps(["https://example.test/one.jpg"]),article_layout_json="{}")


def test_permanent_media_failure_archives_instead_of_infinite_retry(tmp_path):
    store = V2Store(tmp_path / "db.sqlite")
    aid = _insert(store, "https://example.test/story")
    store.update_article(aid, stage="READY", decision="PUBLISH")
    store.archive_permanent_missing_media(aid, detail="no verified article media")
    row = store.get_article(aid)
    assert row["stage"] == "ARCHIVED"
    assert row["decision"] == "REJECT"
    assert row["last_error_code"] == "MEDIA_REQUIRED_PERMANENT"
    assert not store.ready_articles(2)
    assert store.insert_collected(channel_id=2,source_id=131,external_id="trend-57655",
        title="Chocolate squares",source_url="https://example.test/story",
        raw_text="Chocolate squares, pistachio and crisps",
        media_json=json.dumps(["https://example.test/one.jpg", "https://example.test/two.jpg"]),
        article_layout_json="{}") == aid
    assert not store.ready_articles(2)


def test_migration_of_legacy_permanent_ready_entries(tmp_path):
    path = tmp_path / "db.sqlite"
    store = V2Store(path)
    aid = _insert(store,"https://example.test/story")
    store.update_article(aid, stage="READY", decision="PUBLISH",
        blocked_by="MEDIA",last_error_code="MEDIA_REQUIRED",
        article_layout_json=json.dumps({"media_recovery":{"classification":"permanent","attempts":160}}))
    with store.connect() as con:
        con.execute("DELETE FROM meta WHERE key='v2120_archive_permanent_media_v1'")
    store2 = V2Store(path)
    row=store2.get_article(aid)
    assert row["stage"] == "ARCHIVED"
    assert row["last_error_code"] == "MEDIA_REQUIRED_PERMANENT"
    assert store2.ready_articles(2) == []
