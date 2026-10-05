from __future__ import annotations

from pathlib import Path

from telegram_autopilot.v2.event_dedupe_guard import EventFingerprintDedupeEngine
from telegram_autopilot.v2.publisher import Publisher
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_store(path: Path) -> tuple[V2Store, int, int]:
    store = V2Store(path)
    stamp = now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,'T','@t',?,?)",(stamp,stamp))
        s1 = int(con.execute("INSERT INTO sources(channel_id,kind,name,url) VALUES(1,'page','A','https://a.example')").lastrowid)
        s2 = int(con.execute("INSERT INTO sources(channel_id,kind,name,url) VALUES(1,'page','B','https://b.example')").lastrowid)
    a1 = store.insert_collected(
        channel_id=1, source_id=s1, external_id='1',
        title='City bridge closed after drone strike damages power line',
        source_url='https://a.example/1',
        raw_text='Officials said a drone strike damaged a power line near the central bridge. Repair crews closed the bridge for emergency work.',
        source_published_at=stamp,
    )
    a2 = store.insert_collected(
        channel_id=1, source_id=s2, external_id='2',
        title='Power line damage shuts central bridge following drone attack',
        source_url='https://b.example/2',
        raw_text='After a drone attack, the central bridge was closed while crews repair damaged electrical infrastructure and the power line.',
        source_published_at=stamp,
    )
    return store, a1, a2


def test_rc106_shadow_candidate_never_changes_decision(tmp_path: Path) -> None:
    store, a1, a2 = _seed_store(tmp_path / 'shadow.sqlite3')
    engine = EventFingerprintDedupeEngine(store)
    current = store.get_article(a2)
    candidate = store.get_article(a1)
    assert current is not None and candidate is not None
    assert engine._record_shadow_candidates(current, [candidate], context='pre_ai') == 1
    with store.connect() as con:
        row = con.execute("SELECT * FROM dedupe_shadow_candidates WHERE article_id=?", (a2,)).fetchone()
    assert row is not None
    assert float(row['score']) >= 45
    assert store.get_article(a2)['decision'] == 'PENDING'


def test_rc106_ai_usage_summary(tmp_path: Path) -> None:
    store = V2Store(tmp_path / 'usage.sqlite3')
    store.record_ai_usage(
        provider='nvidia', model='nvidia/nemotron-3-super-120b-a12b', purpose='writer',
        input_tokens=4000, output_tokens=500, total_tokens=4500, estimated_openrouter_usd=0.000545,
    )
    summary = store.ai_usage_summary(24)
    assert summary['calls'] == 1
    assert summary['total_tokens'] == 4500
    assert summary['estimated_openrouter_usd'] > 0


def test_rc106_required_media_gets_bounded_recovery(tmp_path: Path) -> None:
    store, _a1, a2 = _seed_store(tmp_path / 'media.sqlite3')
    article = store.get_article(a2)
    assert article is not None

    class Bundle:
        source_kind = 'page'
        source_media_count = 0
        declared_media_count = 0

    classification, retry_seconds, attempt = Publisher(store)._media_recovery_plan(article, Bundle(), video_expected=True)
    assert classification == 'recoverable'
    assert retry_seconds == 600
    assert attempt == 1
