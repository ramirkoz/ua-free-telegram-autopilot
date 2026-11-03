"""The official rebuild must preserve the exact 2.3.5 commercial source roster.

No live API or Telegram send. The synthetic Data includes original article and
delivery FKs, a disabled Trend Hunter, and Design Milk through FeedBurner.
"""
import sqlite3

from telegram_autopilot.v2.commercial_sources_236 import (
    apply_commercial_sources_236, NEW_SOURCES, MARKER,
)


class Store:
    def __init__(self, file):
        self.file = file
        with self.transaction() as con:
            con.executescript("""
              CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
              CREATE TABLE channels(id INTEGER PRIMARY KEY,channel_mode TEXT,
                     editorial_runtime_profile TEXT);
              CREATE TABLE sources(
                id INTEGER PRIMARY KEY,channel_id INTEGER,kind TEXT,
                name TEXT,url TEXT,enabled INTEGER,initialized INTEGER,
                priority INTEGER,last_checked_at TEXT,last_error TEXT,
                legacy_config_json TEXT,UNIQUE(channel_id,url)
              );
              CREATE TABLE source_health(
                source_id INTEGER PRIMARY KEY,consecutive_failures INTEGER,
                cooldown_until TEXT,last_outcome TEXT,last_error TEXT,
                zero_result_streak INTEGER,slow_streak INTEGER,last_duration_ms INTEGER,
                last_items INTEGER,last_added INTEGER,updated_at TEXT,
                success_count INTEGER,failure_count INTEGER
              );
              CREATE TABLE articles(id INTEGER PRIMARY KEY,source_id INTEGER,stage TEXT);
              CREATE TABLE publication_delivery_journal(
                id INTEGER PRIMARY KEY,article_id INTEGER,result TEXT
              );
              INSERT INTO channels VALUES(1,'editorial','standard');
              INSERT INTO channels VALUES(2,'editorial','commercial_editorial');
              INSERT INTO channels VALUES(3,'monitoring','standard');
              INSERT INTO sources VALUES
                (127,2,'page','The Dieline','https://thedieline.com/',
                    0,1,11,'2026-10-01','', '{}'),
                (131,2,'page','Trend Hunter','https://www.trendhunter.com/',
                    0,1,55,'2026-10-01','', '{}'),
                (199,2,'rss','Yanko Design','https://www.yankodesign.com/feed/',
                    1,1,18,'2026-11-01','', '{}'),
                (200,2,'rss','Creative Bloq','https://www.creativebloq.com/feeds.xml',
                    1,1,22,'2026-11-01','', '{}'),
                (201,2,'rss','Design Milk','https://feeds.feedburner.com/design-milk',
                    1,1,25,'2026-11-01','', '{}'),
                (202,2,'rss','Muse by Clio','https://musebyclios.com/feed/',
                    1,1,14,'2026-11-01','', '{}'),
                (900,1,'rss','CTRL custom','https://ctrl.example/feed',
                    1,1,1,'2026-11-01','', '{}'),
                (901,3,'rss','GROMADY custom','https://gromady.example/feed',
                    1,1,1,'2026-11-01','', '{}'),
                (902,2,'rss','My custom','https://design.example/feed',
                    0,1,99,'2026-11-01','', '{}');
              INSERT INTO source_health VALUES
                (127,7,'2026-11-10','HTTP_403','403',3,0,0,0,0,'',10,7),
                (131,4,'2026-11-10','TIMEOUT','timeout',3,0,0,0,0,'',12,4),
                (201,0,'','OK','',0,0,0,0,0,'',90,1);
              INSERT INTO articles VALUES(700,201,'PUBLISHED');
              INSERT INTO publication_delivery_journal VALUES(10,700,'COMMITTED');
            """)
            con.commit()
    def transaction(self):
        con = sqlite3.connect(self.file)
        con.row_factory = sqlite3.Row
        return con


def test_rebuild_from_official_2264_preserves_feedburner_and_article_history(tmp_path):
    db = Store(tmp_path / "data.sqlite3")
    first = apply_commercial_sources_236(db)
    assert first["channels"][0]["status"] == "applied"
    assert set(first["channels"][0]["restored"]) == {"The Dieline", "Trend Hunter"}
    assert set(first["channels"][0]["added"]) == {v[0] for v in NEW_SOURCES}
    with db.transaction() as con:
        all_sources = {r["name"]:r for r in con.execute(
            "SELECT * FROM sources WHERE channel_id=2"
        )}
        assert all_sources["Trend Hunter"]["url"].endswith("TrendHunter/Top10")
        assert all_sources["Trend Hunter"]["enabled"] == 1
        assert all_sources["The Dieline"]["enabled"] == 1
        assert all_sources["Design Milk"]["url"] == "https://feeds.feedburner.com/design-milk"
        assert all_sources["Design Milk"]["enabled"] == 1
        assert all_sources["My custom"]["enabled"] == 0
        assert con.execute("SELECT source_id FROM articles WHERE id=700").fetchone()[0] == 201
        assert con.execute("SELECT result FROM publication_delivery_journal").fetchone()[0] == "COMMITTED"
        assert con.execute("SELECT success_count,failure_count FROM source_health WHERE source_id=131").fetchone()[:] == (12, 4)
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id<>2").fetchone()[0] == 2
    assert apply_commercial_sources_236(db)["channels"][0]["status"] == "already_applied"


def test_no_additional_feeds_after_imported_235_roster(tmp_path):
    db = Store(tmp_path / "existing.sqlite3")
    with db.transaction() as con:
        con.execute("UPDATE sources SET url=?,kind='rss',enabled=1 WHERE id=127",
                    ("https://thedieline.com/feed/",))
        for i,(name,url,priority) in enumerate(NEW_SOURCES, 203):
            con.execute(
                "INSERT INTO sources VALUES(?,2,'rss',?,?,1,1,?,'2026-11-03','','{}')",
                (i,name,url,priority),
            )
        con.commit()
    report = apply_commercial_sources_236(db)["channels"][0]
    assert report["added"] == []
    assert report["restored"] == ["Trend Hunter"]
    with db.transaction() as con:
        assert con.execute("SELECT count(*) FROM sources WHERE channel_id=2").fetchone()[0] == 11
        assert con.execute("SELECT count(*) FROM meta WHERE key=?", (MARKER+"2",)).fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM sources WHERE name='Trend Hunter'").fetchone()[0] == 1


def test_custom_channel_and_syndicated_feed_are_not_hijacked(tmp_path):
    db = Store(tmp_path / "custom.sqlite3")
    with db.transaction() as con:
        con.execute("UPDATE sources SET url='https://user.example/modified',enabled=1 WHERE id=199")
        con.execute("UPDATE sources SET url='https://custom.example/hunter',enabled=1 WHERE id=131")
        con.execute("DELETE FROM sources WHERE id IN (200,202)")
        con.commit()
    report=apply_commercial_sources_236(db)["channels"][0]
    assert report["status"] == "custom_roster_preserved"
    with db.transaction() as con:
        assert con.execute("SELECT url FROM sources WHERE id=131").fetchone()[0] == "https://custom.example/hunter"
        assert con.execute("SELECT count(*) FROM sources WHERE name='Colossal'").fetchone()[0] == 0
