from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from telegram_autopilot.v2.ai_gateway import AIGateway, GatewayExhausted
from telegram_autopilot.v2.dedupe import DedupeEngine
from telegram_autopilot.v2.domain import BlockedBy, ChannelConfig, ChannelMode, ChannelPolicy, Decision, ProviderHealth, ProviderState, Stage
from telegram_autopilot.v2.editorial import EditorialEngine
from telegram_autopilot.v2.migration import build_export_bundle, import_legacy_data, open_legacy_readonly
from telegram_autopilot.v2.runtime import RuntimeEngine
from telegram_autopilot.v2.storage import V2Store, now_iso


def seed_channel(store: V2Store, channel_id: int, *, mode: str = "editorial", name: str | None = None, policy: ChannelPolicy | None = None) -> None:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(?,?,?,1,?,?,?)",
            (channel_id, name or f"Channel {channel_id}", f"@c{channel_id}", mode, stamp, stamp),
        )
        p = policy or ChannelPolicy(channel_id=channel_id, selection_rules="tech", rejection_rules="exclude promo")
        con.execute(
            """INSERT INTO channel_policies(channel_id,enabled,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,
               positive_examples,negative_examples,extra_instructions,selector_extra_prompt,writer_extra_prompt,media_policy,target_min_chars,target_max_chars,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (channel_id,1,p.purpose,p.audience,p.selection_rules,p.rejection_rules,p.writing_rules,p.style_rules,p.positive_examples,p.negative_examples,p.extra_instructions,p.selector_extra_prompt,p.writer_extra_prompt,p.media_policy,p.target_min_chars,p.target_max_chars,stamp),
        )


def seed_source(store: V2Store, channel_id: int, source_id: int, *, url: str | None = None) -> None:
    with store.connect() as con:
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(?,?, 'rss', ?, ?, 1, 100)", (source_id, channel_id, f"S{source_id}", url or f"https://source{source_id}.example/feed"))


def add_article(store: V2Store, channel_id: int, source_id: int, external_id: str, *, title: str, url: str, body: str = "body", content_hash: str = "") -> int:
    return store.insert_collected(channel_id=channel_id, source_id=source_id, external_id=external_id, title=title, source_url=url, raw_text=body, content_hash=content_hash)


def test_v2_source_has_no_rc_imports():
    root = Path(__file__).resolve().parents[1] / "telegram_autopilot" / "v2"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from .. import rc" not in text, path
        assert "from . import rc" not in text, path
        assert "install_rc" not in text, path
        assert "_PREV[" not in text, path


def test_source_is_hard_publication_gate(tmp_path: Path):
    store = V2Store(tmp_path / "v2.sqlite3")
    seed_channel(store, 1); seed_source(store, 1, 1)
    aid = add_article(store, 1, 1, "x", title="Title", url="", body="Текст джерела")
    store.update_article(aid, final_text="Готовий український текст новини")
    with pytest.raises(ValueError, match="SOURCE_MISSING"):
        store.mark_ready(aid)
    row = store.get_article(aid)
    assert row["blocked_by"] == "SOURCE"
    ok, reason = store.publication_guard(aid)
    assert not ok and reason in {"NOT_READY", "SOURCE_MISSING"}


def test_fresh_first_and_per_channel_claim(tmp_path: Path):
    store = V2Store(tmp_path / "v2.sqlite3")
    for cid in (1, 2): seed_channel(store, cid); seed_source(store, cid, cid)
    old = add_article(store,1,1,"old",title="old",url="https://a/old")
    fresh = add_article(store,1,1,"fresh",title="fresh",url="https://a/fresh")
    other = add_article(store,2,2,"other",title="other",url="https://b/other")
    with store.connect() as con:
        con.execute("UPDATE articles SET source_published_at='2026-09-08T01:00:00+00:00' WHERE id=?",(old,))
        con.execute("UPDATE articles SET source_published_at='2026-09-09T07:00:00+00:00' WHERE id=?",(fresh,))
    j1=store.claim_job(channel_id=1,worker_id="c1")
    assert int(j1["article_id"]) == fresh
    j2=store.claim_job(channel_id=2,worker_id="c2")
    assert int(j2["article_id"]) == other


def test_provider_success_wakes_waiting_ai(tmp_path: Path):
    store=V2Store(tmp_path/"v2.sqlite3"); seed_channel(store,1); seed_source(store,1,1)
    aid=add_article(store,1,1,"a",title="a",url="https://a/1")
    job=store.claim_job(channel_id=1,worker_id="w"); store.defer_job(int(job["id"]),blocked_by=BlockedBy.AI,error_code="WAITING_AI",detail="provider outage",retry_seconds=3600,count_attempt=False)
    gateway=AIGateway(store)
    gateway._mark_success("codex","account-default")
    with store.connect() as con:
        row=con.execute("SELECT j.state,a.blocked_by,a.retry_count FROM jobs j JOIN articles a ON a.id=j.article_id WHERE a.id=?",(aid,)).fetchone()
    assert row["state"] == "QUEUED"
    assert row["blocked_by"] == "NONE"
    assert row["retry_count"] == 0


def test_strict_dedupe_same_source_different_rows_do_not_merge(tmp_path: Path):
    store=V2Store(tmp_path/"v2.sqlite3"); seed_channel(store,1); seed_source(store,1,1)
    a=add_article(store,1,1,"1",title="NVIDIA releases DLSS 4.0 update",url="https://s/1",body="NVIDIA DLSS 4.0 new game update A")
    b=add_article(store,1,1,"2",title="NVIDIA releases DLSS 4.1 update",url="https://s/2",body="NVIDIA DLSS 4.1 another game update B")
    result=DedupeEngine(store).evaluate(b)
    assert result.relation == "SINGLE"
    assert store.get_article(b)["decision"] == "PENDING"


def test_strict_dedupe_exact_url_is_duplicate_and_media_is_donated(tmp_path: Path):
    store=V2Store(tmp_path/"v2.sqlite3"); seed_channel(store,1); seed_source(store,1,1); seed_source(store,1,2)
    a=add_article(store,1,1,"1",title="Same event",url="https://news/event",body="facts")
    b=add_article(store,1,2,"2",title="Same event elsewhere",url="https://news/event",body="facts")
    store.update_article(b,media_json=json.dumps(["https://img.example/a.jpg"]))
    result=DedupeEngine(store).evaluate(b)
    assert result.relation == "DUPLICATE" and result.duplicate_of == a
    assert store.get_article(b)["decision"] == "DUPLICATE"
    assert "https://img.example/a.jpg" in store.get_article(a)["media_json"]


def test_monitoring_never_fail_opens_on_ai_outage(tmp_path: Path):
    store=V2Store(tmp_path/"v2.sqlite3")
    p=ChannelPolicy(channel_id=3,selection_rules="лише офіційні рішення громад",rejection_rules="не брати привітання")
    seed_channel(store,3,mode="monitoring",policy=p); seed_source(store,3,3)
    aid=add_article(store,3,3,"1",title="Рішення громади",url="https://t.me/source/1",body="Офіційне рішення")
    class DeadGateway:
        def run(self,*a,**kw): raise GatewayExhausted("AI down",retry_seconds=300,provider_outage=True)
    engine=EditorialEngine(store,DeadGateway())
    with pytest.raises(GatewayExhausted): engine.select(store.get_channel(3),store.get_article(aid))
    assert store.get_article(aid)["decision"] == "PENDING"


def make_legacy_db(path: Path) -> None:
    con=sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE channels(id INTEGER PRIMARY KEY,name TEXT,telegram_chat_id TEXT,editorial_profile TEXT,enabled INTEGER,include_source_link INTEGER,poll_interval_minutes INTEGER,min_publish_interval_minutes INTEGER,dedupe_window_hours INTEGER,max_age_hours INTEGER,max_posts_per_cycle INTEGER,editorial_weights_json TEXT,content_direction TEXT,poll_immediate INTEGER,publish_24h INTEGER,publish_start TEXT,publish_end TEXT,publish_immediately INTEGER,topic_balance_enabled INTEGER,topic_daily_limit INTEGER,related_spacing_posts INTEGER,channel_mode TEXT,media_enrichment_mode TEXT,media_first_allowed INTEGER,media_min_text_chars INTEGER,custom_future_setting TEXT,created_at TEXT,updated_at TEXT);
    CREATE TABLE channel_policies(channel_id INTEGER PRIMARY KEY,enabled INTEGER,purpose TEXT,audience TEXT,selection_rules TEXT,rejection_rules TEXT,writing_rules TEXT,style_rules TEXT,positive_examples TEXT,negative_examples TEXT,extra_instructions TEXT,selector_extra_prompt TEXT,writer_extra_prompt TEXT,media_policy TEXT,target_min_chars INTEGER,target_max_chars INTEGER,updated_at TEXT);
    CREATE TABLE sources(id INTEGER PRIMARY KEY,channel_id INTEGER,kind TEXT,name TEXT,url TEXT,enabled INTEGER,initialized INTEGER,last_checked_at TEXT,last_error TEXT,priority INTEGER,unknown_source_setting TEXT);
    CREATE TABLE articles(id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,external_id TEXT,title TEXT,url TEXT,normalized_url TEXT,raw_text TEXT,content_hash TEXT,source_published_at TEXT,discovered_at TEXT,status TEXT,reject_reason TEXT,duplicate_of INTEGER,event_key TEXT,event_summary TEXT,rewrite_text TEXT,ai_provider TEXT,ai_model TEXT,published_at TEXT,telegram_message_id TEXT,media_json TEXT,article_layout_json TEXT,editorial_category TEXT,editorial_value_score INTEGER,tags_json TEXT,topic_major TEXT,topic_minor TEXT,ready_at TEXT,teaser_text TEXT,telegram_media_count INTEGER,last_error TEXT,retry_count INTEGER,next_retry_at TEXT);
    CREATE TABLE article_feedback(article_id INTEGER PRIMARY KEY,channel_id INTEGER,telegram_message_id TEXT,checked_at TEXT,published_at TEXT,views INTEGER,forwards INTEGER,replies INTEGER,likes INTEGER,dislikes INTEGER,fires INTEGER,other_reactions INTEGER);
    CREATE TABLE provider_cooldowns(provider TEXT,until TEXT,reason TEXT);
    """)
    con.execute("INSERT INTO channels VALUES(1,'CTRL+UA','@ctrl','tech',1,1,5,11,72,48,3,'[{\"name\":\"AI\",\"weight\":70}]','en_to_uk',1,1,'00:00','23:59',1,1,4,6,'editorial','auto',1,450,'preserve-me','2026-09-01T00:00:00+00:00','2026-09-09T00:00:00+00:00')")
    con.execute("INSERT INTO channel_policies VALUES(1,1,'tech purpose','UA','include research','exclude promo','write concise','human','good','bad','extra','selector extra','writer extra','preferred',280,780,'2026-09-09T00:00:00+00:00')")
    con.execute("INSERT INTO sources VALUES(1,1,'rss','Src','https://src/feed',1,1,'','','50','keep-source')")
    con.execute("INSERT INTO articles(id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,source_published_at,discovered_at,status,published_at,telegram_message_id,teaser_text,media_json,article_layout_json) VALUES(10,1,1,'p','Published','https://src/p','https://src/p','facts','h1','2026-09-08T12:00:00+00:00','2026-09-08T12:00:00+00:00','published','2026-09-08T13:00:00+00:00','555','published text','[]','{}')")
    con.execute("INSERT INTO articles(id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,source_published_at,discovered_at,status,last_error,retry_count,next_retry_at) VALUES(11,1,1,'r','Recent','https://src/r','https://src/r','facts','h2','2026-09-09T06:00:00+00:00','2026-09-09T06:00:00+00:00','error','temporary',9,'2099-01-01T00:00:00+00:00')")
    con.execute("INSERT INTO articles(id,channel_id,source_id,external_id,title,url,normalized_url,raw_text,content_hash,source_published_at,discovered_at,status) VALUES(12,1,1,'o','Old','https://src/o','https://src/o','facts','h3','2026-08-01T06:00:00+00:00','2026-08-01T06:00:00+00:00','new')")
    con.execute("INSERT INTO article_feedback VALUES(10,1,'555','2026-09-09T06:00:00+00:00','2026-09-08T13:00:00+00:00',100,4,1,5,0,2,0)")
    con.execute("INSERT INTO provider_cooldowns VALUES('codex','2099-01-01','bad state')")
    con.commit(); con.close()


def test_legacy_migration_preserves_editorial_settings_not_runtime_state(tmp_path: Path):
    legacy=tmp_path/"legacy.sqlite3"; make_legacy_db(legacy); target=V2Store(tmp_path/"v2.sqlite3")
    report=import_legacy_data(legacy,target,reevaluate_hours=48)
    assert report.channels_imported==1 and report.sources_imported==1 and report.published_imported==1
    cfg=target.get_channel(1)
    assert cfg is not None
    assert cfg.min_publish_interval_minutes==11 and cfg.publish_24h is True and cfg.topic_daily_limit==4
    assert cfg.editorial_weights_json.startswith("[") and cfg.language_mode=="en_to_uk"
    assert cfg.policy.selection_rules=="include research" and cfg.policy.media_policy=="preferred"
    with target.connect() as con:
        extras=json.loads(con.execute("SELECT legacy_config_json FROM channels WHERE id=1").fetchone()[0])
        source_extras=json.loads(con.execute("SELECT legacy_config_json FROM sources WHERE id=1").fetchone()[0])
        published=con.execute("SELECT stage FROM articles WHERE legacy_article_id=10").fetchone()[0]
        recent=con.execute("SELECT stage,decision,retry_count,next_retry_at FROM articles WHERE legacy_article_id=11").fetchone()
        old=con.execute("SELECT stage FROM articles WHERE legacy_article_id=12").fetchone()[0]
        jobs=con.execute("SELECT a.legacy_article_id,j.state FROM jobs j JOIN articles a ON a.id=j.article_id").fetchall()
        health=con.execute("SELECT COUNT(*) FROM provider_health").fetchone()[0]
    assert extras["custom_future_setting"]=="preserve-me" and source_extras["unknown_source_setting"]=="keep-source"
    assert published=="PUBLISHED" and recent["stage"]=="COLLECTED" and recent["decision"]=="PENDING"
    assert recent["retry_count"]==0 and recent["next_retry_at"]==""
    assert old=="ARCHIVED" and [tuple(r) for r in jobs]==[(11,"QUEUED")]
    assert health==0


def test_legacy_readonly_and_export_bundle(tmp_path: Path):
    legacy=tmp_path/"legacy.sqlite3"; make_legacy_db(legacy)
    with open_legacy_readonly(legacy) as con:
        with pytest.raises(sqlite3.OperationalError): con.execute("DELETE FROM channels")
    bundle=build_export_bundle(legacy,tmp_path/"export.zip")
    assert bundle.exists() and bundle.stat().st_size>100


def test_runtime_channel_isolation_on_ai_outage(tmp_path: Path):
    store=V2Store(tmp_path/"v2.sqlite3")
    for cid in (1,2,3): seed_channel(store,cid); seed_source(store,cid,cid); add_article(store,cid,cid,f"a{cid}",title=f"Article {cid}",url=f"https://s{cid}/a")
    runtime=RuntimeEngine(store)
    class FakeEditorial:
        def process_article(self,aid):
            row=store.get_article(aid)
            if int(row["channel_id"])==1: raise GatewayExhausted("provider down",retry_seconds=300,provider_outage=True)
            store.update_article(aid,decision="REJECT",stage="SELECTED",reject_reason="test")
            class O: decision=Decision.REJECT
            return O()
    class FakePublisher:
        def publish_ready(self,cid): return 0
    runtime.editorial=FakeEditorial(); runtime.publisher=FakePublisher(); runtime.ingest.collect_channel=lambda cid:{"seen":0,"added":0,"errors":0}
    runtime.start(); deadline=time.time()+4
    try:
        c1 = None
        c2 = c3 = None
        while time.time()<deadline:
            with store.connect() as con:
                c1=con.execute("SELECT a.blocked_by,j.state,a.retry_count FROM articles a JOIN jobs j ON j.article_id=a.id WHERE a.channel_id=1").fetchone()
                c2=con.execute("SELECT decision FROM articles WHERE channel_id=2").fetchone()[0]
                c3=con.execute("SELECT decision FROM articles WHERE channel_id=3").fetchone()[0]
            if c1 is not None and c1["blocked_by"]=="AI" and c1["state"]=="WAITING" and c2=="REJECT" and c3=="REJECT":
                break
            time.sleep(.05)
        assert c1 is not None
        assert c1["blocked_by"]=="AI" and c1["state"]=="WAITING" and c1["retry_count"]==0
        assert c2=="REJECT" and c3=="REJECT"
    finally: runtime.stop()
