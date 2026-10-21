"""2.2.11 operator LIVE regressions: actionable READY, local relevance, safe site identity."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.municipal_event_identity import municipal_same_event
from telegram_autopilot.v2.ready_backlog import ReadyBacklogStore, ReadyBacklogSupervisor
from telegram_autopilot.v2.runtime import _ready_buffer_counts
from telegram_autopilot.v2.storage import now_iso


def _monitoring():
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1003",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]"),
    )


def _article(text):
    return {"title": text, "raw_text": text, "source_id": 190}


def test_live_nabu_nbu_national_story_rejected():
    text="Обшуки НАБУ в Національному банку України: слідчі вивчають документи НБУ."
    assert "MONITORING_OFF_TOPIC" in civic_relevance_exclusion(_monitoring(), _article(text))
    assert "MONITORING_OFF_TOPIC" in live_now_exclusion(_monitoring(), _article(text))


def test_live_eu_sanctions_national_story_rejected():
    text="ЄС готує новий пакет санкцій проти Росії, його планують ухвалити у листопаді."
    assert "MONITORING_OFF_TOPIC" in civic_relevance_exclusion(_monitoring(), _article(text))


def test_regional_delivery_is_not_blocked_by_national_theme():
    # National decisions matter if there is a verifiable local outcome.
    text="ЄС ухвалив пакет санкцій проти Росії. Запоріжжя отримає обладнання у межах місцевої програми."
    assert not civic_relevance_exclusion(_monitoring(), _article(text))


def test_local_nabu_case_is_not_blocked_as_general_national_news():
    text="НАБУ проводить розслідування. Запорізька громада отримає повернуте обладнання."
    assert not civic_relevance_exclusion(_monitoring(), _article(text))


def test_unopted_channel_does_not_receive_local_filter():
    ch=_monitoring()
    ch.policy.rejection_rules=""
    text="ЄС готує новий пакет санкцій проти Росії."
    assert not civic_relevance_exclusion(ch, _article(text))


def _shelter(title, source_id, when="2026-10-21T11:00:00+03:00"):
    return {"title":title,"raw_text":title,"source_id":source_id,"source_published_at":when}


def test_same_district_is_not_sufficient_for_duplicate():
    a=_shelter("У Запоріжжі в Олександрівському районі встановлюють модульне укриття",190)
    b=_shelter("Олександрівський район Запоріжжя: почали монтаж іншого модульного укриття",191)
    assert municipal_same_event(a,b)[0] is False


def test_explicit_shared_park_and_phase_is_duplicate():
    a=_shelter("У Запоріжжі в парку Дубовий Гай встановлюють модульне укриття",190)
    b=_shelter("Біля парку Дубовий Гай у Запоріжжі триває монтаж модульного укриття",191)
    same,reason=municipal_same_event(a,b)
    assert same,reason
    assert "park:" in reason


def test_different_park_is_not_duplicate():
    a=_shelter("У Запоріжжі в парку Дубовий Гай встановлюють модульне укриття",190)
    b=_shelter("У Запоріжжі в парку Перемоги встановлюють модульне укриття",191)
    assert not municipal_same_event(a,b)[0]


def test_different_stage_is_not_duplicate():
    a=_shelter("У Запоріжжі в парку Дубовий Гай встановлюють модульне укриття",190)
    b=_shelter("У Запоріжжі в парку Дубовий Гай відкрили модульне укриття",191)
    assert not municipal_same_event(a,b)[0]


def _seed_ready(store):
    stamp=now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,enabled,max_age_hours,created_at,updated_at) VALUES(1,'ctrl','',1,24,?,?)",(stamp,stamp))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority) VALUES(1,1,'rss','test','https://example.org/feed',1,1,100)")
        for i,blocked in ((1,"MEDIA"),(2,"NONE")):
            con.execute(
                """INSERT INTO articles(
                id,channel_id,source_id,external_id,title,source_url,canonical_source_url,
                raw_text,source_published_at,discovered_at,stage,decision,blocked_by,ready_at,next_retry_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (i,1,1,str(i),str(i),f"https://example.org/{i}",f"https://example.org/{i}",
                 str(i),stamp,stamp,"READY","PUBLISH",blocked,stamp,stamp),
            )


def test_media_blocked_ready_does_not_use_ai_ready_slot(tmp_path):
    store=ReadyBacklogStore(tmp_path/"v2.sqlite3")
    _seed_ready(store)
    assert _ready_buffer_counts(store,1)==(2,1)
    with store.connect() as con:
        con.execute("UPDATE articles SET blocked_by='NONE' WHERE id=1")
    assert _ready_buffer_counts(store,1)==(2,2)


def test_ready_telemetry_has_usable_count_and_interval():
    import inspect
    source=inspect.getsource(ReadyBacklogSupervisor.build_snapshot)
    assert "ready_buffer_usable" in source
    assert "min_publish_interval_minutes" in source
    assert "next_allowed_publish_at" in source
