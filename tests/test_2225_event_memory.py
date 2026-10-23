"""2.2.25 source-owned event memory: real COMMITTED, updates, non-merges and restart."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from telegram_autopilot.v2.event_memory import (
    _facts, _relation, find_published_event, record_committed_event,
)

BASE = ("Ворог атакував Запоріжжя. Удар прийшовся по приватному будинку. "
        "Загинули двоє людей.")
REPEAT = ("Росіяни завдали удару по приватному сектору у Запоріжжі. "
          "Загинули двоє людей. Про наслідки повідомила місцева влада.")
UPDATE = ("Після удару по приватному будинку у Запоріжжі загинули троє людей. "
          "Кількість загиблих зросла після уточнення даних.")


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE articles (
                  id INTEGER PRIMARY KEY,channel_id INTEGER,stage TEXT,
                  title TEXT,raw_text TEXT,source_published_at TEXT,
                  published_at TEXT,event_key TEXT DEFAULT ''
                );
                CREATE TABLE publication_delivery_journal(
                  article_id INTEGER,channel_id INTEGER,state TEXT
                );
                CREATE TABLE delivery_receipt_archive(
                  article_id INTEGER,channel_id INTEGER,state TEXT
                );
            """)

    def connect(self):
        con = sqlite3.connect(self.path, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con

    def add(self, article_id, text, *, offset=0, channel=3, receipt="COMMITTED", archived=False):
        when = (datetime.now(timezone.utc)-timedelta(minutes=offset)).isoformat()
        with self.connect() as con:
            con.execute("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)",
                        (article_id,channel,"PUBLISHED",text,text,when,when,""))
            if archived:
                con.execute("INSERT INTO delivery_receipt_archive VALUES (?,?,?)",
                            (article_id,channel,receipt))
            else:
                con.execute("INSERT INTO publication_delivery_journal VALUES (?,?,?)",
                            (article_id,channel,receipt))

    def get_channel(self, channel_id):
        return None

    def get_article(self, article_id):
        with self.connect() as con:
            return con.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()

    def update_article(self, article_id, **fields):
        with self.connect() as con:
            con.execute("UPDATE articles SET event_key=? WHERE id=?",
                        (fields["event_key"],article_id))


def incoming(article_id, text, *, channel=3, offset=0):
    when = (datetime.now(timezone.utc)-timedelta(minutes=offset)).isoformat()
    return {"id":article_id,"channel_id":channel,"title":text,
            "raw_text":text,"source_published_at":when,"published_at":""}


def test_cross_source_same_event_and_material_death_update(tmp_path):
    store = Store(tmp_path/"events.sqlite3")
    store.add(75211,BASE,offset=195)
    same = find_published_event(store,incoming(75338,REPEAT,offset=185))
    assert same.relation=="DUPLICATE" and same.prior_article_id==75211
    changed = find_published_event(store,incoming(75930,UPDATE))
    assert changed.relation=="UPDATE" and changed.event_id==same.event_id
    store.add(75930,UPDATE)
    assert record_committed_event(store,75930)==same.event_id
    assert find_published_event(store,incoming(75931,UPDATE)).relation=="DUPLICATE"
    with store.connect() as con:
        assert con.execute("SELECT count(*) FROM event_registry").fetchone()[0]==1
    assert record_committed_event(store,75930)==same.event_id  # idempotent


def test_unknown_failed_ready_unconfirmed_not_authoritative(tmp_path):
    store = Store(tmp_path/"unknown.sqlite3")
    store.add(10,BASE,receipt="UNKNOWN")
    assert find_published_event(store,incoming(11,REPEAT)).relation=="NEW"
    assert record_committed_event(store,10)==""
    with store.connect() as con:
        con.execute("UPDATE publication_delivery_journal SET state='COMMITTED'")
    assert find_published_event(store,incoming(11,REPEAT)).relation=="DUPLICATE"


def test_archived_receipt_and_independent_channel(tmp_path):
    store = Store(tmp_path/"archive.sqlite3")
    store.add(10,BASE,archived=True)
    assert find_published_event(store,incoming(11,REPEAT)).relation=="DUPLICATE"
    assert find_published_event(store,incoming(12,REPEAT,channel=2)).relation=="NEW"


def test_separate_strikes_sites_and_second_event_not_merged(tmp_path):
    original = BASE + " Будинок стоїть на вул. Весняній."
    wrong_street = REPEAT + " Удар прийшовся на вул. Літній."
    new_strike = REPEAT.replace("завдали удару", "завдали ще один удар")
    apartment = REPEAT.replace("приватному сектору", "багатоповерхівці")
    assert _relation(incoming(2,wrong_street),incoming(1,original))==""
    assert _relation(incoming(2,new_strike),incoming(1,BASE))==""
    assert _relation(incoming(2,apartment),incoming(1,BASE))==""
    assert _relation(incoming(2,REPEAT,offset=300),incoming(1,BASE))==""
    assert _relation(incoming(2,REPEAT,offset=60*49),incoming(1,BASE))==""


def test_48h_requires_named_site_and_rejected_claims_not_fact_evidence():
    explicit_a = BASE + " Адреса: вул. Весняна."
    explicit_b = REPEAT + " Адреса: вул. Весняній."
    assert _relation(incoming(2,explicit_b,offset=22*60),
                     incoming(1,explicit_a))=="DUPLICATE"
    source = incoming(2,REPEAT)
    source["final_text"]="Загинули десятеро, всі були однією родиною."
    assert _facts(source)["fatalities"]==2


def test_event_snapshot_survives_article_retention(tmp_path):
    store = Store(tmp_path/"retained.sqlite3")
    store.add(10,BASE)
    key = record_committed_event(store,10)
    assert key.startswith("ev25:")
    with store.connect() as con:
        con.execute("DELETE FROM publication_delivery_journal")
        con.execute("DELETE FROM articles WHERE id=10")
    assert find_published_event(store,incoming(11,REPEAT)).event_id==key


def test_actual_production_dedupe_route_blocks_and_preserves_update(tmp_path):
    from telegram_autopilot.v2.event_dedupe_guard import EventFingerprintDedupeEngine

    store=Store(tmp_path/"runtime.sqlite3")
    store.add(75211,BASE,offset=90,receipt="COMMITTED")
    store.add(75338,REPEAT,offset=80,receipt="FAILED")
    store.add(75930,UPDATE,offset=2,receipt="FAILED")
    with store.connect() as con:
        con.execute("UPDATE articles SET stage='READY',published_at='' WHERE id IN (75338,75930)")
    engine=EventFingerprintDedupeEngine(store)
    repeat=engine._find_duplicate(75338,published_only=True)
    assert repeat.relation=="DUPLICATE" and repeat.duplicate_of==75211
    update=engine._find_duplicate(75930,published_only=True)
    assert update.relation=="SINGLE"
    assert store.get_article(75930)["event_key"]=="ev25:3:75211"


def test_different_city_and_uncorroborated_change_not_merged():
    different=REPEAT.replace("Запоріжжі","Дніпрі")
    assert _relation(incoming(2,different),incoming(1,BASE))==""
    ungrounded=incoming(2,REPEAT)
    ungrounded["final_text"]="Нібито загинули троє."
    assert _relation(ungrounded,incoming(1,BASE))=="DUPLICATE"
