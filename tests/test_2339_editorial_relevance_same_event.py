"""Regression controls from owner-reviewed LIVE posts 17 November 2026.

No Telegram sends; in-memory database only. Tests include both negative
operator-RED examples and positive cases for real updates/creative mechanisms.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from telegram_autopilot.v2.editorial_live_2339 import (
    creative_routine_pet_rescue_reason,
    monitoring_appeal_not_news_reason,
    recent_committed_source_duplicate,
    source_same_event_without_update,
)


SIGNALS = """На основних вулицях Запоріжжя світлофори під час відключень
працюють від акумуляторних батарей. Сьогодні через тривалі аварійні
відключення розряджені батареї довелось замінювати.
На інших об’єктах світлофори заживили від генераторів."""

OFFICIAL = """На основних вулицях міста світлофори обладнані акумуляторними
батареями, які дозволяють продовжувати роботу під час відключень
електроенергії. Сьогодні через тривалу відсутність світла комунальники
оперативно замінювали розряджені АКБ на заряджені. На інших об’єктах
безперебійну роботу світлофорів забезпечували за допомогою генераторів."""

POSTED = {
    "source_id": 140,
    "title": "Світлофори мають працювати за будь-яких умов. На основних вулицях міста світлофори обладнані акумуляторними батареями",
    "raw_text": OFFICIAL,
}
FOLLOWUP = {
    "source_id": 197,
    "title": "На основних вулицях Запоріжжя світлофори під час відключень працюють від акумуляторних батарей",
    "raw_text": SIGNALS,
}


def test_actual_cross_source_traffic_lights_is_same_event():
    assert source_same_event_without_update(FOLLOWUP, POSTED)


def test_unrelated_energy_recovery_is_not_same_traffic_event():
    unrelated = {
        "source_id": 197,
        "title": "У Запоріжжі продовжується відновлення електропостачання після обстрілів",
        "raw_text": "Обстріли ускладнюють ремонт електромереж. Енергетики працюють над відновленням електропостачання мешканцям.",
    }
    assert not source_same_event_without_update(unrelated, POSTED)


def test_real_new_status_is_not_silenced():
    update = dict(FOLLOWUP)
    update["raw_text"] = SIGNALS + " Після ремонту електропостачання відновлено."
    assert not source_same_event_without_update(update, POSTED)


def test_new_numerical_fact_is_not_silenced():
    update = dict(FOLLOWUP)
    update["raw_text"] = SIGNALS + " Сьогодні замінили 27 батарей."
    assert not source_same_event_without_update(update, POSTED)


def test_different_streets_are_not_merged():
    a = dict(FOLLOWUP)
    b = dict(POSTED)
    a["raw_text"] += " На вулиці Хортицькій було завершено заміну."
    b["raw_text"] += " На вулиці Соборній роботи тривають."
    assert not source_same_event_without_update(a, b)


def test_pet_rescue_is_not_a_creative_channel_story():
    article = {
        "title": "Flatbush Cats Rescues Isaac, A Beloved Cat Trapped for Four Days After Tragic Brooklyn Building Collapse",
        "raw_text": "Flatbush Cats founder entered the damaged building and rescued Isaac, who was trapped under the sink, reuniting him with his family.",
    }
    assert creative_routine_pet_rescue_reason(article) == "CREATIVE_ROUTINE_PET_RESCUE_NOT_CHANNEL_FIT_2339"


def test_original_creative_or_engineering_pet_story_is_not_autoblocked():
    article = {
        "title": "New robot rescues trapped dogs in a landmark demonstration",
        "raw_text": "Engineers built a new robot prototype that rescues trapped dogs under rubble.",
    }
    assert not creative_routine_pet_rescue_reason(article)


def test_complaint_to_utility_is_not_a_verified_news_event():
    article = {
        "title": "Обленерго, оприлюднить інформацію по районах чи чергах, будь ласка",
        "raw_text": "Сотні людей з ранку без світла, шукають інформацію, якої немає ніде! У нас чат-бот лопає від запитів, і відповіді на них немає.",
    }
    assert monitoring_appeal_not_news_reason(article) == "MONITORING_READER_APPEAL_NOT_VERIFIED_NEWS_2339"


def test_official_verified_restoration_status_not_blocked():
    article = {
        "title": "Роботи з відновлення електропостачання у Запоріжжі тривають",
        "raw_text": "Обленерго повідомило, що аварійні бригади відновили живлення частини споживачів. Роботи продовжуються.",
    }
    assert not monitoring_appeal_not_news_reason(article)


class ReadOnlyScenarioStore:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """CREATE TABLE articles (
                   id INTEGER PRIMARY KEY, channel_id INTEGER, source_id INTEGER,
                   title TEXT, raw_text TEXT, published_at TEXT, stage TEXT);
               CREATE TABLE publication_delivery_journal
                   (article_id INTEGER, channel_id INTEGER, state TEXT);
               CREATE TABLE delivery_receipt_archive
                   (article_id INTEGER, channel_id INTEGER, state TEXT);"""
        )

    @contextmanager
    def connect(self):
        yield self.connection


def test_duplicate_requires_telegram_committed_receipt():
    store = ReadOnlyScenarioStore()
    store.connection.execute(
        "INSERT INTO articles VALUES (?,?,?,?,?,?,?)",
        (104329, 3, 140, POSTED["title"], POSTED["raw_text"],
         datetime.now(timezone.utc).isoformat(), "PUBLISHED"),
    )
    store.connection.execute(
        "INSERT INTO publication_delivery_journal VALUES (?,?,?)",
        (104329, 3, "COMMITTED"),
    )
    assert recent_committed_source_duplicate(store, 3, 104380, FOLLOWUP) == 104329
    store.connection.execute(
        "UPDATE publication_delivery_journal SET state='UNKNOWN'"
    )
    assert recent_committed_source_duplicate(store, 3, 104380, FOLLOWUP) == 0
    store.connection.close()


def test_another_channel_publication_does_not_block_this_channel():
    store = ReadOnlyScenarioStore()
    store.connection.execute(
        "INSERT INTO articles VALUES (?,?,?,?,?,?,?)",
        (104329, 1, 140, POSTED["title"], POSTED["raw_text"],
         datetime.now(timezone.utc).isoformat(), "PUBLISHED"),
    )
    store.connection.execute(
        "INSERT INTO publication_delivery_journal VALUES (?,?,?)",
        (104329, 1, "COMMITTED"),
    )
    assert recent_committed_source_duplicate(store, 3, 104380, FOLLOWUP) == 0
    store.connection.close()
