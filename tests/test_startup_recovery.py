from pathlib import Path

from telegram_autopilot.database import Database
from telegram_autopilot.startup_recovery import recover_interrupted_work


def _seed(db: Database) -> None:
    with db.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,editorial_profile,enabled,include_source_link,poll_interval_minutes,min_publish_interval_minutes,dedupe_window_hours,max_age_hours,max_posts_per_cycle,created_at,updated_at) VALUES(1,'Recovery','@recovery','tech',1,0,5,0,72,24,3,'x','x')")
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized) VALUES(1,1,'rss','Feed','https://example.com/feed',1,1)")
        for article_id, status in ((1,'processing'), (2,'telegraph_writing'), (3,'telegram_writing')):
            con.execute("INSERT INTO articles(id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,discovered_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (article_id,1,1,f'x{article_id}',f'Article {article_id}',f'https://example.com/{article_id}',f'https://example.com/{article_id}','text',f'h{article_id}','2026-08-17T10:00:00+00:00',status))


def test_startup_recovery_requeues_safe_processing_and_quarantines_external_writes(tmp_path: Path):
    db = Database(tmp_path / 'recovery.sqlite3')
    _seed(db)
    result = recover_interrupted_work(db)
    assert result == {'processing_to_retry': 1, 'external_to_unknown': 2}
    assert db.get_article(1)['status'] == 'retry'
    assert db.get_article(1)['next_retry_at'] is None
    assert db.get_article(2)['status'] == 'unknown'
    assert db.get_article(3)['status'] == 'unknown'
    assert [row['id'] for row in db.pending_articles(1, limit=10)] == [1]
