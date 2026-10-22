"""Cross-publisher regression for two posts describing one fatal residential strike."""
import sqlite3
from datetime import datetime, timedelta
from telegram_autopilot.v2.incident_guard import (
    _fatal_count, _same_short_fatal_residential_event, recent_community_incident_duplicate,
)

FIRST = "Ворог атакував Запоріжжя. Удар прийшовся по приватному будинку. Загинули двоє людей."
SECOND = "Росіяни завдали удару по приватному сектору Запоріжжя: загинули двоє людей."

class Store:
    def __init__(self, path, *, age=11):
        self.path = path
        with self.connect() as con:
            con.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY,channel_id INTEGER,stage TEXT,title TEXT,raw_text TEXT,final_text TEXT,published_at TEXT)")
            con.execute("CREATE TABLE publication_delivery_journal(article_id INTEGER,channel_id INTEGER,state TEXT)")
            con.execute("CREATE TABLE delivery_receipt_archive(article_id INTEGER,channel_id INTEGER,state TEXT)")
            at = (datetime.now().astimezone()-timedelta(minutes=age)).isoformat()
            con.execute("INSERT INTO articles VALUES(75211,3,'PUBLISHED',?,?,?,?)",(FIRST,FIRST,FIRST,at))
            con.execute("INSERT INTO publication_delivery_journal VALUES(75211,3,'COMMITTED')")

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

def row(text=SECOND):
    return {"id":75338,"title":text,"raw_text":text,"final_text":text}

def test_exact_pair_rejected_before_second_send(tmp_path):
    store=Store(str(tmp_path/"dedupe.db"))
    assert _fatal_count(FIRST)==_fatal_count(SECOND)==2
    assert _same_short_fatal_residential_event(SECOND,FIRST)
    assert recent_community_incident_duplicate(store,3,75338,row())==75211

def test_followup_changed_count_and_target_survive(tmp_path):
    store=Store(str(tmp_path/"dedupe.db"))
    for text in (
        "У Запоріжжі внаслідок удару по приватному будинку загинули троє людей.",
        "У Запоріжжі після удару по багатоповерхівці загинули двоє людей.",
        "У Дніпрі після удару по приватному будинку загинули двоє людей.",
        "Оновлені дані: у Запоріжжі після удару по приватному будинку загинули двоє людей.",
    ):
        assert recent_community_incident_duplicate(store,3,75338,row(text))==0

def test_20_minute_window_and_channel_scope(tmp_path):
    store=Store(str(tmp_path/"old.db"),age=21)
    assert recent_community_incident_duplicate(store,3,75338,row())==0
    recent=Store(str(tmp_path/"recent.db"))
    assert recent_community_incident_duplicate(recent,2,75338,row())==0

def test_different_explicit_streets_not_conflated():
    a="Росіяни атакували приватний будинок на вул. Весняній у Запоріжжі. Загинули двоє людей."
    b="Росіяни атакували приватний будинок на вул. Літній у Запоріжжі. Загинули двоє людей."
    assert not _same_short_fatal_residential_event(a,b)


def test_unknown_receipt_does_not_prove_delivery(tmp_path):
    store=Store(str(tmp_path/"unknown.db"))
    with store.connect() as con:
        con.execute("UPDATE publication_delivery_journal SET state='UNKNOWN'")
    assert recent_community_incident_duplicate(store,3,75338,row()) == 0

def test_archived_receipt_proves_delivery(tmp_path):
    store=Store(str(tmp_path/"archive.db"))
    with store.connect() as con:
        con.execute("DELETE FROM publication_delivery_journal")
        con.execute("INSERT INTO delivery_receipt_archive VALUES(75211,3,'COMMITTED')")
    assert recent_community_incident_duplicate(store,3,75338,row()) == 75211

def test_actual_ova_and_newsroom_wording_same_fatal_strike(tmp_path):
    store=Store(str(tmp_path/"exact_operator.db"))
    official="Ворог атакував Запоріжжя. Удар прийшовся по приватному будинку. Загинули двоє людей. Щирі співчуття рідним і близьким."
    newsroom="Росіяни завдали удару по приватному сектору Запоріжжя: загинули двоє людей - ЗОВА."
    with store.connect() as con:
        con.execute("UPDATE articles SET title=?,raw_text=?,final_text=? WHERE id=75211",
                    (official,official,official))
    assert recent_community_incident_duplicate(store,3,75338,row(newsroom))==75211


def test_unpublished_article_cannot_be_used_as_confirmation(tmp_path):
    store=Store(str(tmp_path/"not_published.db"))
    with store.connect() as con:
        con.execute("UPDATE articles SET stage='READY' WHERE id=75211")
    assert recent_community_incident_duplicate(store,3,75338,row()) == 0
