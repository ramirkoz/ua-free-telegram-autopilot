"""2.3.36 source retirement test: preserves rows and manual user re-enable."""
from contextlib import contextmanager
import sqlite3

from telegram_autopilot.v2.editorial_source_retirement_236 import disable_bored_panda_236


class Store:
    def __init__(self):
        self.conn=sqlite3.connect(":memory:")
        self.conn.row_factory=sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE channels(id INTEGER PRIMARY KEY,channel_mode TEXT,editorial_runtime_profile TEXT);
            CREATE TABLE sources(id INTEGER PRIMARY KEY,channel_id INTEGER,kind TEXT,name TEXT,url TEXT,enabled INTEGER);
            CREATE TABLE articles(id INTEGER PRIMARY KEY,source_id INTEGER,title TEXT);
            INSERT INTO channels VALUES(2,'editorial','commercial_editorial');
            INSERT INTO channels VALUES(3,'monitoring','monitoring');
            INSERT INTO sources VALUES(241,2,'rss','Bored Panda','https://www.boredpanda.com/feed/',1);
            INSERT INTO sources VALUES(242,2,'rss','PsyPost','https://www.psypost.org/feed/',1);
            INSERT INTO sources VALUES(243,3,'rss','Bored Panda','https://www.boredpanda.com/feed/',1);
            INSERT INTO sources VALUES(244,2,'rss','Bored Panda','https://www.boredpanda.com/custom-feed',1);
            INSERT INTO articles VALUES(103482,241,'55 People Who Signed NDAs');
        """)
    @contextmanager
    def transaction(self):
        yield self.conn


def test_disable_exact_source_without_deleting_history_and_preserve_manual_reenable():
    st=Store()
    assert disable_bored_panda_236(st)["disabled"]==1
    assert [(r["id"],r["enabled"]) for r in st.conn.execute("SELECT id,enabled FROM sources ORDER BY id")]==[(241,0),(242,1),(243,1),(244,1)]
    assert st.conn.execute("SELECT title FROM articles WHERE id=103482").fetchone()[0]
    st.conn.execute("UPDATE sources SET enabled=1 WHERE id=241")
    st.conn.commit()
    assert disable_bored_panda_236(st)["status"]=="already_applied"
    assert st.conn.execute("SELECT enabled FROM sources WHERE id=241").fetchone()[0]==1
