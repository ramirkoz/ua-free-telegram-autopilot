"""v2.2.31 regressions from 2026-10-25 real operator 832-attack triple.

The three publishers' original facts are redacted/excerpted, not AI captions.
No Telegram action, no operator database writes, no fabricated publication receipt.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from telegram_autopilot.v2.regional_daily_event_231 import (
    regional_daily_facts, regional_daily_relation, regional_daily_relation_facts,
)
from telegram_autopilot.v2.event_dedupe_guard import (
    EventFingerprintDedupeEngine, event_fingerprint_same_event,
)
from telegram_autopilot.v2.event_memory import find_published_event, record_committed_event

STAMP = "2026-10-25T11:20:53+02:00"
POLICE = (
    "Подробиці ударів по Запоріжжю та області 24 жовтня. "
    "Вчора армія РФ атакувала Запоріжжя ракетами та безпілотниками. "
    "У результаті ударів поранення отримали 43-річна жінка та 60-річний чоловік. "
    "У Лежиному та Кушугумі Запорізького району внаслідок атак FPV-дронів "
    "поранені 14-річна дівчинка та 61-річний чоловік."
)
NEWSROOM = (
    "У Запоріжжі та Запорізькому районі внаслідок російських атак "
    "поранені четверо людей, серед них 14-річна дівчинка. "
    "Упродовж доби війська РФ завдали 832 удари по населених пунктах області. "
    "У Запоріжжі поранені 43-річна жінка та 60-річний чоловік. "
    "У Лежиному та Кушугумі FPV-дрони поранили 14-річну дівчинку "
    "та 61-річного чоловіка. Поліцейські евакуювали трьох жінок."
)
AGGREGATE = (
    "Постраждали четверо людей: у суботу під удари військ потрапили 55 "
    "міст та сіл Запорізької області. Упродовж доби, 24 жовтня, "
    "російські війська завдали 832 удари по 55 населених пунктах. "
    "Четверо людей дістали поранень унаслідок атак на Запоріжжя "
    "та Запорізький район. 60-річний чоловік отримав осколкове поранення. "
    "Надійшло 50 повідомлень про пошкодження."
)


def row(article_id, source, *, when=STAMP, channel=3, source_id=None, stage="PENDING"):
    return {
        "id": article_id, "source_id": source_id if source_id is not None else article_id,
        "channel_id": channel, "title": source[:120], "raw_text": source,
        "source_published_at": when, "stage": stage,
        "decision": "PUBLISH", "published_at": "",
        "event_key": "", "content_hash": "", "source_url": "",
    }


def test_actual_three_sources_have_same_day_and_facts():
    first, second, third = (regional_daily_facts(row(i, s))
                            for i, s in enumerate((POLICE, NEWSROOM, AGGREGATE), 1))
    assert all(f["report_day"] == "2026-10-24" for f in (first, second, third))
    assert first["injured"] == second["injured"] == third["injured"] == 4, (first, second, third)
    assert first["strikes"] is None
    assert second["strikes"] == third["strikes"] == 832
    assert first["ages"] == second["ages"] == [14, 43, 60, 61]


def test_direct_same_event_matches_all_three_original_publishers():
    for i, left in enumerate((POLICE, NEWSROOM, AGGREGATE)):
        for j, right in enumerate((POLICE, NEWSROOM, AGGREGATE)):
            if i == j:
                continue
            assert regional_daily_relation(row(100+i, left), row(100+j, right)) == "DUPLICATE"
            assert event_fingerprint_same_event(row(100+i, left), row(100+j, right))[0]


def test_more_detail_without_new_casualty_count_is_not_update():
    assert regional_daily_relation(row(2, NEWSROOM), row(1, POLICE)) == "DUPLICATE"
    assert regional_daily_relation(row(3, AGGREGATE), row(2, NEWSROOM)) == "DUPLICATE"


def test_confirmed_increase_and_correction_remain_updates():
    changed = AGGREGATE.replace("Четверо людей дістали поранень", "За оновленими даними, п'ятеро людей дістали поранень")
    # Remove the other 4-injury headline, so the original source isn't contradictory.
    changed = changed.replace("Постраждали четверо людей:", "Уточнено наслідки:")
    assert regional_daily_relation(row(5, changed), row(1, AGGREGATE)) == "UPDATE"
    assert not event_fingerprint_same_event(row(5, changed), row(1, AGGREGATE))[0]
    without_confirmation = changed.replace("За оновленими даними,", "")
    assert regional_daily_relation(row(5, without_confirmation), row(1, AGGREGATE)) == ""


def test_different_day_is_new_even_with_same_832_attacks():
    changed = AGGREGATE.replace("24 жовтня", "23 жовтня")
    assert regional_daily_relation(row(2, changed), row(1, AGGREGATE)) == ""


def test_report_publication_time_without_a_timezone_fails_closed():
    r = row(2, NEWSROOM, when="2026-10-25T11:20:53")
    assert not regional_daily_facts(r)
    assert regional_daily_relation(r, row(1, POLICE)) == ""
    r["source_published_at"] = ""
    r["discovered_at"] = STAMP
    assert not regional_daily_facts(r)


def test_single_town_attack_not_equivalent_to_regionwide_daily_digest():
    local = (
        "Вчора у Кушугумі Запорізького району ворог атакував автівку. "
        "Поранені четверо людей, серед яких 60-річний чоловік. "
        "Потерпілих доправили до лікарні."
    )
    assert regional_daily_facts(row(2, local)) == {}
    assert regional_daily_relation(row(2, local), row(1, POLICE)) == ""


def test_missing_region_and_different_victims_do_not_merge():
    different = AGGREGATE.replace("Запорізької області", "Дніпропетровської області").replace("Запоріжжя", "Дніпро").replace("Запорізький", "Дніпровський")
    assert regional_daily_relation(row(2, different), row(1, POLICE)) == ""
    isolated = POLICE.replace("43-річна", "35-річна").replace("60-річний", "70-річний").replace("14-річна", "16-річна").replace("61-річний", "62-річний")
    assert regional_daily_relation(row(2, isolated), row(1, POLICE)) == ""


def test_ai_caption_cannot_authorize_identity_or_changed_casualty_count():
    current = row(2, "Сьогодні сталася ще одна атака. У Запоріжжі пошкоджено автівку.")
    current["final_text"] = AGGREGATE
    assert regional_daily_facts(current) == {}
    assert regional_daily_relation(current, row(1, AGGREGATE)) == ""
    current = row(2, NEWSROOM)
    current["final_text"] = "За уточненням, загинули десятеро людей."
    assert regional_daily_relation(current, row(1, AGGREGATE)) == "DUPLICATE"


def test_different_proven_hours_window():
    future = "2026-10-26T13:20:53+02:00"
    assert regional_daily_relation(row(2, NEWSROOM, when=future), row(1, POLICE)) == ""


class SqliteEventStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as con:
            con.executescript("""
              CREATE TABLE articles (
                id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,
                stage TEXT,decision TEXT,title TEXT,raw_text TEXT,
                source_published_at TEXT,published_at TEXT,event_key TEXT DEFAULT ''
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

    def insert(self, article, *, receipt="COMMITTED", archive=False):
        with self.connect() as con:
            con.execute(
                "INSERT INTO articles VALUES(?,?,?,?,?,?,?,?,?,?)",
                (article["id"], article["channel_id"], article["source_id"],
                 "PUBLISHED", "PUBLISH", article["title"], article["raw_text"],
                 article["source_published_at"], STAMP, ""),
            )
            if receipt:
                table = "delivery_receipt_archive" if archive else "publication_delivery_journal"
                con.execute("INSERT INTO " + table + " VALUES(?,?,?)",
                            (article["id"], article["channel_id"], receipt))

    def get_article(self, article_id):
        with self.connect() as con:
            return con.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()

    def update_article(self, article_id, **values):
        with self.connect() as con:
            con.execute("UPDATE articles SET event_key=? WHERE id=?",
                        (values["event_key"], article_id))

    def get_channel(self, channel_id):
        return None


def test_archived_committed_original_blocks_new_daily_duplicate(tmp_path):
    store = SqliteEventStore(tmp_path / "daily.sqlite3")
    store.insert(row(79194, POLICE), archive=True)
    match = find_published_event(store, row(79198, NEWSROOM))
    assert match.relation == "DUPLICATE"
    assert match.prior_article_id == 79194
    assert record_committed_event(store, 79194).startswith("ev25:")
    assert find_published_event(store, row(79195, AGGREGATE)).relation == "DUPLICATE"


def test_unknown_or_failed_cannot_prove_daily_publication(tmp_path):
    store = SqliteEventStore(tmp_path / "unknown.sqlite3")
    store.insert(row(79194, POLICE), receipt="UNKNOWN")
    assert find_published_event(store, row(79198, NEWSROOM)).relation == "NEW"
    store.insert(row(79195, AGGREGATE), receipt="FAILED")
    assert find_published_event(store, row(79200, NEWSROOM)).relation == "NEW"


def test_committed_event_update_keeps_same_event_id(tmp_path):
    store = SqliteEventStore(tmp_path / "update.sqlite3")
    store.insert(row(79195, AGGREGATE))
    first_event_id = record_committed_event(store, 79195)
    updated = AGGREGATE.replace("Постраждали четверо людей:", "Уточнено наслідки:").replace(
        "Четверо людей дістали поранень", "За оновленими даними, п'ятеро людей дістали поранень"
    )
    match = find_published_event(store, row(79255, updated))
    assert match.relation == "UPDATE"
    assert match.event_id == first_event_id


def test_no_cross_channel_or_missing_receipt_authority(tmp_path):
    store = SqliteEventStore(tmp_path / "channels.sqlite3")
    store.insert(row(79194, POLICE, channel=3))
    assert find_published_event(store, row(79198, NEWSROOM, channel=2)).relation == "NEW"
    store.insert(row(79195, AGGREGATE, channel=3, when="2026-10-25T11:30:53+02:00"), receipt="FAILED")
    assert find_published_event(store, row(79196, NEWSROOM, channel=3)).prior_article_id == 79194
