from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore
from telegram_autopilot.v2.storage import now_iso


def _seed(store):
    stamp = now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,'TEST','@test',?,?)", (stamp, stamp))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(1,1,'rss','Feed','https://example.com/feed',1,50))


def _article(store, eid, stage, text="text"):
    stamp = now_iso()
    with store.connect() as con:
        return con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,
            discovered_at,stage,decision,final_text)
            VALUES(1,1,?,'Title',?, ?,?,'PUBLISH',?)""",
            (eid, f"https://example.com/{eid}", stamp, stage, text)
        ).lastrowid


def test_2010_reset_once_preserves_history_and_does_not_resurrect_approvals(tmp_path):
    store = ReadyBacklogStore(tmp_path / "db.sqlite3")
    _seed(store)
    published = _article(store, "published", "PUBLISHED")
    pending = _article(store, "pending", "READY")
    with store.connect() as con:
        con.execute("INSERT INTO editorial_actions(article_id,channel_id,action,created_at) VALUES(?,1,'approve',?)", (pending, now_iso()))
    first = store._reset_2010_queue_once()
    assert first["retired"] == 1
    assert store.get_article(published)["stage"] == "PUBLISHED"
    row = store.get_article(pending)
    assert row["stage"] == "ARCHIVED" and row["final_text"] == ""
    assert row["last_error_code"] == "QUEUE_RESET_2010"
    assert store.reconcile_human_approved_unpublished()["restored"] == 0
    assert store.human_approved_summary(1)["total_unpublished"] == 0
    assert store._reset_2010_queue_once()["skipped"] == 1


def test_2010_reset_keeps_uncertain_delivery_quarantined(tmp_path):
    store = ReadyBacklogStore(tmp_path / "db.sqlite3")
    _seed(store)
    aid = _article(store, "unknown", "READY")
    with store.connect() as con:
        con.execute("""INSERT INTO publication_delivery_journal
          (article_id,channel_id,state,mode,complete,expected_media_count,
          media_count,primary_message_id,message_ids_json,attempt_count,prepared_at,updated_at)
          VALUES (?,1,'UNKNOWN','media_final',0,1,0,'','[]',1,?,?)""",
          (aid, now_iso(), now_iso()))
    store._reset_2010_queue_once()
    assert store.get_article(aid)["last_error_code"] != "QUEUE_RESET_2010"
    assert store.delivery_journal(aid)["state"] == "UNKNOWN"
