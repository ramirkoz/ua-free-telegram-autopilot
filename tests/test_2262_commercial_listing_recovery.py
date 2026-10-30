"""2.2.62 commercial publisher listing, strict source date and delivery safety."""
import inspect
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from telegram_autopilot import collector
from telegram_autopilot.v2.page_publication_date_262 import published_date_from_article_html
from telegram_autopilot.v2.commercial_listing_recovery_262 import (
    recover_commercial_listings_262, RECOVERY, MARKER,
)
from telegram_autopilot.v2.freshness_fence_241 import source_freshness_rejection
from telegram_autopilot.v2.main import main


class Store:
    def __init__(self, path: Path):
        self.path=path
        with self.transaction() as con:
            con.executescript("""
            CREATE TABLE channels(id INTEGER PRIMARY KEY,editorial_runtime_profile TEXT);
            CREATE TABLE sources(
                id INTEGER PRIMARY KEY,channel_id INTEGER,name TEXT,url TEXT,kind TEXT,
                enabled INTEGER,initialized INTEGER,priority INTEGER,
                last_error TEXT,last_checked_at TEXT,legacy_config_json TEXT,
                UNIQUE(channel_id,url)
            );
            CREATE TABLE source_health(
                source_id INTEGER PRIMARY KEY,consecutive_failures INTEGER,cooldown_until TEXT,
                last_outcome TEXT,last_error TEXT,zero_result_streak INTEGER,slow_streak INTEGER,
                last_duration_ms INTEGER,last_items INTEGER,last_added INTEGER,updated_at TEXT,
                success_count INTEGER,failure_count INTEGER
            );
            CREATE TABLE articles(id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,stage TEXT);
            CREATE TABLE publication_delivery_journal(id INTEGER PRIMARY KEY,article_id INTEGER,result TEXT);
            INSERT INTO channels VALUES(1,'standard');
            INSERT INTO channels VALUES(2,'commercial_editorial');
            INSERT INTO sources VALUES(102,2,'Shots','https://shots.net/','page',1,1,20,'timeout','2026-10-30T17:10:00+02:00','{}');
            INSERT INTO sources VALUES(103,2,'Ad Age','https://adage.com/','page',1,1,140,'','2026-10-30T17:10:00+02:00','{}');
            INSERT INTO sources VALUES(126,2,'Famous Campaigns','https://www.famouscampaigns.com/','page',1,1,10,'','2026-10-30T17:10:00+02:00','{}');
            INSERT INTO sources VALUES(902,1,'Shots','https://shots.net/','page',1,1,20,'','2026-10-30T17:10:00+02:00','{}');
            INSERT INTO source_health VALUES(102,3,'2026-10-31T08:00:00+02:00','TIMEOUT','timeout',0,10,70125,20,0,'',1083,408);
            INSERT INTO source_health VALUES(103,0,'2026-10-30T20:00:00+02:00','SLOW_EMPTY','',9,11,67625,0,0,'',1202,18);
            INSERT INTO source_health VALUES(126,0,'2026-10-30T20:00:00+02:00','EMPTY','',44,0,1200,0,0,'',100,1);
            INSERT INTO source_health VALUES(902,1,'2026-10-31T08:00:00+02:00','TIMEOUT','',0,3,70125,0,0,'',50,12);
            INSERT INTO articles VALUES(501,2,102,'PUBLISHED');
            INSERT INTO publication_delivery_journal VALUES(7,501,'COMMITTED');
            """)
            con.commit()
    def transaction(self):
        con=sqlite3.connect(self.path)
        con.row_factory=sqlite3.Row
        return con


def test_exact_failing_operator_publishers_migrate_once_no_article_replay(tmp_path):
    store=Store(tmp_path/"s.db")
    out=recover_commercial_listings_262(store)
    assert out["changed"]==3
    expected={row[0]:row for row in RECOVERY}
    with store.transaction() as con:
        for sid,name in [(102,"Shots"),(103,"Ad Age"),(126,"Famous Campaigns")]:
            row=con.execute("SELECT * FROM sources WHERE id=?",(sid,)).fetchone()
            h=con.execute("SELECT * FROM source_health WHERE source_id=?",(sid,)).fetchone()
            assert row["url"]==expected[name][2]
            assert row["initialized"]==1 and row["priority"]>0 and row["last_checked_at"]==""
            assert json.loads(row["legacy_config_json"])[MARKER]["max_article_page_hydrations_per_cycle"]==expected[name][4]
            assert h["last_outcome"]=="LISTING_MIGRATED_262" and h["cooldown_until"]==""
        assert con.execute("SELECT source_id FROM articles WHERE id=501").fetchone()[0]==102
        assert con.execute("SELECT result FROM publication_delivery_journal WHERE id=7").fetchone()[0]=="COMMITTED"
        assert con.execute("SELECT url FROM sources WHERE id=902").fetchone()[0]=="https://shots.net/"
        assert con.execute("SELECT success_count,failure_count FROM source_health WHERE source_id=102").fetchone()==(1083,408)
    assert recover_commercial_listings_262(store)["changed"]==0


def test_custom_urls_healthy_source_and_collision_are_not_changed(tmp_path):
    store=Store(tmp_path/"s.db")
    with store.transaction() as con:
        con.execute("UPDATE sources SET url=? WHERE id=102",("https://shots.net/operator-custom",))
        con.execute("UPDATE source_health SET last_outcome='OK' WHERE source_id=103")
        con.execute("INSERT INTO sources VALUES(127,2,'Custom','https://www.famouscampaigns.com/2026/','page',1,1,30,'','','{}')")
        con.commit()
    out=recover_commercial_listings_262(store)
    assert out["changed"]==0
    assert any(x["outcome"]=="collision_preserved" for x in out["sources"])


def test_date_from_exact_article_meta_and_jsonld():
    url="https://shots.net/news/view/a-new-creative-campaign"
    assert published_date_from_article_html(
        '<link rel="canonical" href="'+url+'">'
        '<meta property="article:published_time" content="2026-10-30T16:34:00+02:00">',url
    ) == "2026-10-30T16:34:00+02:00"
    html='<script type="application/ld+json">'+json.dumps({
        "@graph":[{"@type":"WebSite","datePublished":"2026-10-30T17:12:00+02:00"},
         {"@type":"NewsArticle","mainEntityOfPage":{"@id":url},
          "datePublished":"2026-10-30T16:34:00+02:00"}]})+'</script>'
    assert published_date_from_article_html(html,url)=="2026-10-30T16:34:00+02:00"


@pytest.mark.parametrize("html",[
    '<meta property="article:modified_time" content="2026-10-30T16:34:00+02:00">',
    '<meta property="article:published_time" content="2026-10-30T16:34:00">',
    '<link rel="canonical" href="https://shots.net/news/view/different"><meta property="article:published_time" content="2026-10-30T16:34:00+02:00">',
    '<script type="application/ld+json">{"@type":"NewsArticle","url":"https://shots.net/news/view/other","datePublished":"2026-10-30T16:34:00+02:00"}</script>',
    '<meta property="article:published_time" content="2026-10-30T16:34:00+02:00"><meta name="datePublished" content="2026-10-29T16:34:00+02:00">',
])
def test_invalid_conflicting_or_unowned_date_fails_closed(html):
    assert published_date_from_article_html(html,"https://shots.net/news/view/real")==""


def test_real_source_date_still_obeys_restart_fence():
    date=published_date_from_article_html(
        '<meta property="article:published_time" content="2026-10-29T16:34:00+02:00">',
        "https://shots.net/news/view/real",
    )
    clock=datetime(2026,10,30,18,0,tzinfo=timezone(timedelta(hours=2)))
    assert source_freshness_rejection(date,"2026-10-30T17:00:00+02:00",now=clock)=="SOURCE_NOT_CURRENT_DAY"


def test_page_collector_only_two_hydrations_when_explicitly_bounded(monkeypatch):
    url="https://shots.net/the-work"
    links=''.join('<a href="/news/view/real-campaign-story-'+str(n)+'">An actual campaign story '+str(n)+'</a>' for n in range(8))
    calls=[]
    monkeypatch.setattr(collector,"_source_fetch",lambda *args,**kwargs:SimpleNamespace(body=links.encode()))
    def hydrate(item,**kwargs):
        calls.append(item.url)
        item.raw_text="Valid original article body " * 40
        return item
    monkeypatch.setattr(collector,"_enrich_article",hydrate)
    from telegram_autopilot.models import Source
    s=Source(id=102,channel_id=2,kind="page",name="Shots",url=url,enabled=True,initialized=True,last_checked_at=None,last_error=None)
    values=collector.collect_source(s,page_candidate_scan_limit=30,page_fetch_limit=2)
    assert len(calls)==2 and len(values)==2


def test_release_startup_scoped_before_workers_and_no_new_ai_calls():
    src=inspect.getsource(main)
    assert src.index("recover_commercial_feed_261(store)") < src.index("recover_commercial_listings_262(store)") < src.index("runtime = RuntimeEngine(store)")
    import telegram_autopilot.v2.commercial_listing_recovery_262 as module
    body=inspect.getsource(module)
    assert "DELETE FROM" not in body and "UPDATE channels" not in body
    assert "requests." not in body and "fetch_url(" not in body
