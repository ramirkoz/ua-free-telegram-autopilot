from __future__ import annotations

from pathlib import Path

from telegram_autopilot.v2.ai_gateway import _rc111_qa_signature
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.editorial import _rc111_prepare_candidate
from telegram_autopilot.v2.runtime import _rc111_quality_retry_limit
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_channel_source(store: V2Store) -> int:
    stamp=now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at)
               VALUES(1,'T','@t',1,'editorial',?,?)""",(stamp,stamp)
        )
        con.execute(
            """INSERT INTO channel_policies(channel_id,source_body_attribution_mode,updated_at)
               VALUES(1,'footer_only',?)""",(stamp,)
        )
        return int(con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(1,'page','Example News','https://example.com',1,100)"
        ).lastrowid)


def test_rc111_deterministic_candidate_trims_before_ai_retry(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store)
    channel=store.get_channel(1)
    article={
        "id":1,"source_id":source_id,"source_name":"Example News",
        "title":"Title","raw_text":"Факт один. Факт два. Факт три."
    }
    raw=("Перше речення містить корисний факт. "*20).strip()
    out=_rc111_prepare_candidate(channel,article,raw,hard_max_chars=240,min_chars=120)
    assert len(out)<=240
    assert out.endswith(".")


def test_rc111_footer_only_attribution_is_removed_locally(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store)
    channel=store.get_channel(1)
    article={
        "id":1,"source_id":source_id,"source_name":"Example News",
        "title":"Title","raw_text":"Компанія відкрила новий сервіс."
    }
    out=_rc111_prepare_candidate(
        channel,article,
        "Example News повідомляє, що компанія відкрила новий сервіс.",
        hard_max_chars=500,min_chars=80,
    )
    assert "Example News" not in out
    assert "компанія відкрила новий сервіс" in out.casefold()


def test_rc111_qa_signatures_and_retry_limits() -> None:
    assert _rc111_qa_signature(ValueError("Непридатна довжина Telegram-тексту: понад жорсткий ліміт 750"))=="length"
    assert _rc111_qa_signature(ValueError("AI додав число, якого немає у джерелі: 23:00"))=="invented_number"
    assert _rc111_quality_retry_limit("AI додав число, якого немає у джерелі: 23:00")==1
    assert _rc111_quality_retry_limit("Readability QA: issue")==2


def test_rc111_no_add_source_cools_after_six_cycles(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store)
    for _ in range(6):
        store.record_source_success(source_id,1000,items=20,added=0)
    row=store.source_health(source_id)
    assert row is not None
    assert int(row["zero_result_streak"])==6
    assert row["last_outcome"]=="EMPTY"
    assert row["cooldown_until"]


def test_slow_known_only_source_does_not_fake_empty_cooldown(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store)
    store.record_source_success(source_id,47000,items=20,added=0)
    row=store.source_health(source_id)
    assert row is not None
    assert row["last_outcome"]=="KNOWN_ONLY"
    assert row["cooldown_until"]==""


def test_rc111_quality_exhaustion_rejects_only_when_no_final_text(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"db.sqlite3")
    source_id=_seed_channel_source(store)
    stamp=now_iso()
    with store.connect() as con:
        aid=int(con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                      discovered_at,stage,decision)
               VALUES(1,?,'a','A','https://example.com/a','https://example.com/a','body',?,'COLLECTED','PENDING')""",
            (source_id,stamp)
        ).lastrowid)
        jid=int(con.execute(
            """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at)
               VALUES(?,1,'process','LEASED',100,?,?,?)""",(aid,stamp,stamp,stamp)
        ).lastrowid)
    assert store.exhaust_quality_job(jid,detail="bad qa")=="REJECTED"
    row=store.get_article(aid)
    assert row["decision"]=="REJECT"
    assert row["last_error_code"]=="QUALITY_RETRY_EXHAUSTED"
