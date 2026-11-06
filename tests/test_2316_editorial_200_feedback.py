"""v2.3.16 bounded editorial, source hydration and publication QA regressions.

Real user-labelled examples are topic examples; no old Telegram replay.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from telegram_autopilot.v2.editorial_feedback_2316 import calibrated_feedback_2316
from telegram_autopilot.v2.editorial_queue_2316 import priority_sort_sql_2316
from telegram_autopilot.v2.ingest import collect
from telegram_autopilot.v2.post_quality_2316 import (
    post_language_issues_2316, mixed_topic_issues_2316,
)
from telegram_autopilot.v2.app_notification_dedupe_2316 import (
    app_notification_same_event_2316,
)


def test_reviewed_200_examples_in_editor_prompt_not_whitelists():
    science = calibrated_feedback_2316("science")
    creative = calibrated_feedback_2316("creative")
    assert "68 зі 100" in science and "32 відхилив" in science
    assert "50 зі 100" in creative and "Excel" in creative
    assert "не дозволені бренди" in creative
    assert calibrated_feedback_2316("") == ""
    assert "#91990" not in science and "#91050" not in creative


def test_queue_priority_is_scoped_to_channel_role_and_stays_bounded():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY,title TEXT)")
    c.execute("CREATE TABLE channels(id INTEGER PRIMARY KEY,channel_mode TEXT,"
              "editorial_runtime_profile TEXT,dedupe_profile TEXT)")
    c.executemany("INSERT INTO articles VALUES(?,?)", [
        (1, "Scientists discover new quantum effect"),
        (2, "Winter boots coupon discount"),
        (3, "A routine company update"),
        (4, "Brand launches innovative chocolate packaging campaign"),
    ])
    c.executemany("INSERT INTO channels VALUES(?,?,?,?)", [
        (1, "editorial", "standard", "scientific_news"),
        (2, "editorial", "commercial_editorial", "standard"),
        (3, "monitoring", "standard", "standard"),
    ])
    expr = priority_sort_sql_2316()
    def rank(article_id, channel_id):
        return c.execute(
            f"SELECT {expr} FROM articles a CROSS JOIN channels c "
            "WHERE a.id=? AND c.id=?", (article_id, channel_id)
        ).fetchone()[0]
    assert rank(1,1)==0
    assert rank(2,1)==2
    assert rank(3,1)==1
    assert rank(4,2)==0
    assert rank(4,3)==1  # monitoring not affected
    assert rank(2,3)==1


def test_short_current_rss_prioritizes_same_publisher_hydration(monkeypatch):
    from telegram_autopilot.v2 import ingest
    source = SimpleNamespace(kind="rss",url="https://publisher.example/feed.xml")
    now = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
    short = SimpleNamespace(raw_text="Одна фраза.",published_at=now)
    complete = SimpleNamespace(raw_text=("Дослідники отримали результат. "
                                           "Вчені його пояснили та перевірили. ")*40,published_at=now)
    expired = SimpleNamespace(raw_text="Одна фраза.",published_at=old)
    calls=[]
    def spy(src, **kw):
        calls.append(kw["rss_enrich_eligible"])
        return []
    monkeypatch.setattr(ingest.collector, "collect_source", spy)
    assert collect(source)==[]
    assert calls[0](short)
    assert not calls[0](complete)
    assert not calls[0](expired)


def test_only_observed_live_language_corruptions_rejected():
    assert "UA_2316_PERSHOPRESTOLOVE" in post_language_issues_2316(
        "Поліція Токіо відкрила першопрестолове управління.")
    assert "UA_2316_LAKOMSTVA" in post_language_issues_2316(
        "Бренд рекламує новорічні лакомства.")
    assert "UA_2316_LOWERCASE_SENTENCE_START" in post_language_issues_2316(
        "Виставка відкрилася вчора. у липні запланували інший захід.")
    assert not post_language_issues_2316(
        "У Токіо відкрили нове управління поліції. У місті працює нова команда.")


def test_culture_story_cannot_steal_weather_tail():
    original={"title":"Палац культури «АвтоЗАЗ» відзначив сторіччя",
              "raw_text":"Палац культури відзначив сторіччя. Синоптики прогнозують дощ."}
    final=("Палац культури «АвтоЗАЗ» відзначив сторіччя. "
           "На заході вшанували працівників. За прогнозом синоптиків, завтра буде дощ.")
    assert mixed_topic_issues_2316(original,final)==("EDITORIAL_2316_UNRELATED_WEATHER_TAIL",)
    clean="Палац культури «АвтоЗАЗ» відзначив сторіччя. На заході вшанували працівників."
    assert not mixed_topic_issues_2316(original,clean)
    weather={"title":"Прогноз погоди на вихідні","raw_text":original["raw_text"]}
    assert not mixed_topic_issues_2316(weather,final)


APP_4418=("У застосунку «Цифрове Запоріжжя» тепер доступні графіки "
          "погодинних відключень електроенергії. Сповіщення про зміни "
          "у графіках та анонсовані відключення надходитимуть на телефон.")
APP_4449=("У міському застосунку «Цифрове Запоріжжя» запрацювала нова "
          "функція автоматичних сповіщень про зміни графіків відключення "
          "електроенергії. Мешканці отримуватимуть повідомлення на смартфони.")


def test_actual_4418_4449_redundant_feature_must_dedupe():
    a={"source_id":50,"raw_text":APP_4418,
       "source_published_at":"2026-11-05T15:00:00+02:00"}
    b={"source_id":51,"raw_text":APP_4449,
       "source_published_at":"2026-11-05T18:00:00+02:00"}
    duplicate, reason=app_notification_same_event_2316(a,b)
    assert duplicate and "same Zaporizhzhia app" in reason


def test_genuine_new_time_table_or_new_feature_is_not_a_duplicate():
    a={"source_id":50,"raw_text":APP_4418,
       "source_published_at":"2026-11-05T15:00:00+02:00"}
    updated={"source_id":51,"raw_text":APP_4449+" З 09:00 до 12:00 не буде світла.",
             "source_published_at":"2026-11-05T18:00:00+02:00"}
    assert not app_notification_same_event_2316(a,updated)[0]
    other={"source_id":51,"raw_text":"У «Цифровому Запоріжжі» запустили оплату квитків.",
           "source_published_at":"2026-11-05T18:00:00+02:00"}
    assert not app_notification_same_event_2316(a,other)[0]
    later={"source_id":51,"raw_text":APP_4449,
           "source_published_at":"2026-11-09T18:00:00+02:00"}
    assert not app_notification_same_event_2316(a,later)[0]
