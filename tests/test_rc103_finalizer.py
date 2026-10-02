from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_autopilot.v2.editorial_state import ensure_editorial_state_schema
from telegram_autopilot.v2.rc103_finalizer import _purge_expired_materials
from telegram_autopilot.v2.storage import V2Store, now_iso


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).astimezone().isoformat(timespec="seconds")


def _seed(store: V2Store) -> None:
    now = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,published_dedupe_window_hours,created_at,updated_at)
               VALUES(1,'Test','@test',720,?,?)""",
            (now, now),
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,?)", (now,))
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(1,1,'rss','Source','https://example.com/feed',1,10)"
        )
    ensure_editorial_state_schema(store)


def _article(store: V2Store, external_id: str, when: str, *, stage: str = 'WRITTEN') -> int:
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,canonical_source_url,
                   raw_text,source_published_at,discovered_at,stage,decision,final_text)
               VALUES(1,1,?,?,?,?,?,?,?,?,?,?)""",
            (
                external_id,
                external_id,
                f'https://example.com/{external_id}',
                f'https://example.com/{external_id}',
                'payload',
                when,
                when,
                stage,
                'PUBLISH' if stage == 'PUBLISHED' else 'PENDING',
                'final text',
            ),
        )
        article_id = int(cur.lastrowid)
        if stage == 'PUBLISHED':
            con.execute("UPDATE articles SET published_at=? WHERE id=?", (when, article_id))
        return article_id


def test_rc103_finalizer_deletes_materials_older_than_seven_days_with_children(tmp_path):
    store = V2Store(tmp_path / 'db.sqlite3')
    _seed(store)
    old_id = _article(store, 'old', _ago(8))
    recent_id = _article(store, 'recent', _ago(6))
    with store.connect() as con:
        con.execute(
            """INSERT INTO jobs(article_id,channel_id,job_type,state,available_at,created_at,updated_at)
               VALUES(?,1,'process','WAITING',?,?,?)""",
            (old_id, now_iso(), now_iso(), now_iso()),
        )
        con.execute(
            """INSERT INTO editorial_actions(article_id,channel_id,action,title,created_at)
               VALUES(?,1,'approve','old',?)""",
            (old_id, _ago(8)),
        )

    stats = _purge_expired_materials(store, retention_days=7)
    assert stats['articles_purged'] == 1
    assert store.get_article(old_id) is None
    assert store.get_article(recent_id) is not None
    with store.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM jobs WHERE article_id=?', (old_id,)).fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM editorial_actions WHERE article_id=?', (old_id,)).fetchone()[0] == 0
        assert con.execute('SELECT published_dedupe_window_hours FROM channels WHERE id=1').fetchone()[0] == 168


def test_rc103_finalizer_uses_published_time_for_recent_publication(tmp_path):
    store = V2Store(tmp_path / 'db.sqlite3')
    _seed(store)
    old_source_recent_publish = _article(store, 'published', _ago(12), stage='PUBLISHED')
    with store.connect() as con:
        con.execute('UPDATE articles SET published_at=? WHERE id=?', (_ago(2), old_source_recent_publish))
    _purge_expired_materials(store, retention_days=7)
    assert store.get_article(old_source_recent_publish) is not None


def test_rc103_visible_tab_refresh_does_not_rebuild_all_hidden_trees():
    source = (Path(__file__).resolve().parents[1] / 'telegram_autopilot' / 'v2' / 'rc103_finalizer.py').read_text(encoding='utf-8')
    assert 'self.refresh_home()' in source
    assert 'self._rc103_refresh_active_tab()' in source
    assert 'self.refresh_queue()\n            self.refresh_editorial_review()' not in source
    assert '<<NotebookTabChanged>>' in source
