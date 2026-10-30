"""2.2.58 regression: read-only topic-mix signals, real published feed, no veto."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3

from telegram_autopilot.v2.commercial_topic_balance_258 import (
    commercial_theme_258, commercial_topic_mix_7d_258,
    commercial_topic_advisory_258,
)


class FeedStore:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
          CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT);
          CREATE TABLE articles(
            id INTEGER PRIMARY KEY,channel_id INTEGER,source_id INTEGER,
            title TEXT,final_text TEXT,stage TEXT,published_at TEXT
          );
          INSERT INTO sources VALUES(199,'Yanko Design');
          INSERT INTO sources VALUES(129,'Campaign Brief');
          INSERT INTO sources VALUES(97,'Muse by Clio');
        """)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        old = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat(timespec="seconds")
        posts = [
          (1,2,199,"A tiny house with modular windows","Modular tiny cabin","PUBLISHED",now),
          (2,2,199,"Another tiny home for snowy mountains","Small house","PUBLISHED",now),
          (3,2,199,"New tiny cabin has hidden rooms","Tiny house","PUBLISHED",now),
          (4,2,129,"LEGO makes a pop culture Halloween stunt","Halloween LEGO","PUBLISHED",now),
          (5,2,199,"A compact cabin hides a sauna","Compact cabin","PUBLISHED",now),
          (6,2,97,"Robot goose surprises museum visitors","A robot","PUBLISHED",now),
          (7,2,199,"A new smart watch concept","A watch","REJECTED",""),
          (8,2,199,"Very old tiny house","Old","PUBLISHED",old),
          (9,1,199,"Other channel tiny house","Other","PUBLISHED",now),
        ]
        self.con.executemany("INSERT INTO articles VALUES(?,?,?,?,?,?,?)", posts)
        self.con.commit()

    @contextmanager
    def connect(self):
        yield self.con


def test_topic_mix_uses_published_posts_and_reports_true_source_share():
    store = FeedStore()
    before = store.con.total_changes
    report = commercial_topic_mix_7d_258(store, 2)
    assert report["published_sample_size"] == 6
    assert report["theme_counts"]["tiny_living"] == 4
    assert report["theme_counts"]["pop_culture"] == 1
    assert report["consecutive_theme_run"] == 1  # newest real post is robotics, not tiny living
    assert report["source_published_total_7d"] == 6
    assert report["top_sources"][0]["name"] == "Yanko Design"
    assert report["top_sources"][0]["posts_7d"] == 4
    assert report["top_sources"][0]["share"] == round(4/6, 4)
    assert report["mode"] == "advisory_only"
    assert report["no_rejection_or_quota"] is True
    assert store.con.total_changes == before


def test_theme_advisory_raises_fatigue_context_without_rejecting_any_story():
    store = FeedStore()
    before = store.con.total_changes
    candidate = {"title":"The tiny house that folds into a suitcase"}
    advice = commercial_topic_advisory_258(store, 2, candidate)
    assert "tiny_living" in advice
    assert "SOURCE" in advice
    assert "НЕ заборона" in advice
    assert "Не відхиляй сильну" in advice
    assert store.con.total_changes == before


def test_no_fabricated_theme_or_repeat_when_lexical_evidence_absent():
    store = FeedStore()
    assert commercial_theme_258({"title":"An extraordinary object with a strange twist"}) == "other"
    assert commercial_topic_advisory_258(store, 2, {"title":"A festival of dolphins"}) == ""


def test_unknown_or_empty_feed_has_no_fatigue_veto():
    store = FeedStore()
    assert commercial_topic_advisory_258(store, 4, {"title":"A tiny house"}) == ""
    empty = commercial_topic_mix_7d_258(store, 4)
    assert empty["published_sample_size"] == 0
    assert empty["source_published_total_7d"] == 0
    assert empty["top_sources"] == []


def test_headline_similarity_is_advisory_not_event_dedupe():
    store = FeedStore()
    title = "A tiny house with modular windows"
    advice = commercial_topic_advisory_258(store, 2, {"title":title})
    assert "Подібні заголовки" in advice
    assert "#1" in advice
    assert "НЕ доводять дубль" in advice


def test_actual_consecutive_theme_run_is_counted_from_newest_publication():
    store = FeedStore()
    stamp = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(timespec="seconds")
    with store.connect() as con:
        con.executemany(
            "INSERT INTO articles VALUES(?,?,?,?,?,?,?)",
            [
                (10,2,199,"Tiny house with folding walls","Tiny house","PUBLISHED",stamp),
                (11,2,199,"A tiny home for coastal vacations","Tiny home","PUBLISHED",stamp),
                (12,2,199,"Another tiny cabin for hikers","Tiny cabin","PUBLISHED",stamp),
            ],
        )
    report = commercial_topic_mix_7d_258(store, 2)
    assert report["consecutive_theme_run"] == 3
    assert report["theme_counts"]["tiny_living"] == 7
