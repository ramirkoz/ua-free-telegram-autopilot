"""2.2.44 operator screenshots: two different stories and frames of one civic video.

Use original-source paraphrases, never AI output or a shared video URL as
the proof. Source A = veteran interview; source B = first-month service stats.
The same confirmed milestone can only appear once in the monitoring channel.
"""
from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.civic_milestone_identity_244 import (
    civic_milestone_same_event,
)
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


PUBLISHED = (
    "У Запоріжжі Простір турботи про ветеранів та ветеранок завершив "
    "перший місяць роботи. За цей час понад 50 людей отримали "
    "більше 100 послуг. Простір відкрили наприкінці вересня на базі лікарні. "
    "Надають психологічну допомогу та сприяють оформленню документів."
)
LATER = (
    "У Запоріжжі місяць тому відкрили «Простір турботи про ветерана». "
    "Тут ветерани та родини можуть отримати психологічну допомогу. "
    "55-річний ветеран Анатолій розповів про свій полон і про те, "
    "що тепер може отримати консультацію без проблем."
)
T = "2026-10-27T16:58:00+02:00"
EARLIER = "2026-10-27T15:22:00+02:00"


def story(text, *, article_id, source_id, published_at=T, title=None, final_text=""):
    return {
        "id": article_id, "channel_id": 3, "source_id": source_id,
        "title": title if title is not None else text[:108],
        "raw_text": text, "source_published_at": published_at,
        "published_at": published_at,
        "final_text": final_text, "event_summary": "",
        "source_url": f"https://example.org/source/{source_id}/{article_id}",
        "canonical_source_url": f"https://example.org/source/{source_id}/{article_id}",
        "content_hash": "",
    }


def test_operator_same_video_different_text_cross_source_duplicate():
    prior = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    new = story(LATER, article_id=84621, source_id=101)
    same, reason = civic_milestone_same_event(new, prior)
    assert same and "CIVIC_FIRST_MONTH_DUPLICATE" in reason, reason
    detected, detail = event_fingerprint_same_event(new, prior, monitoring_profile=True)
    assert detected and "CIVIC_FIRST_MONTH_DUPLICATE" in detail, detail
    # A different publisher's quote/story angle cannot reset event identity.


def test_previously_committed_ledger_without_original_source_time():
    prior = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    prior.pop("source_published_at")  # same columns as published_event_ledger
    current = story(LATER, article_id=84621, source_id=101)
    assert event_fingerprint_same_event(current, prior, monitoring_profile=True)[0]


def test_not_enabled_on_other_channel_profiles():
    prior = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    new = story(LATER, article_id=84621, source_id=101)
    same, reason = event_fingerprint_same_event(new, prior, monitoring_profile=False)
    assert not same, reason


def test_different_service_is_not_collapsed():
    other = story(
        LATER.replace("Простір турботи про ветерана", "Центр правової допомоги ветеранам"),
        article_id=84630, source_id=101,
    )
    assert not civic_milestone_same_event(other, story(PUBLISHED, article_id=84601, source_id=100, published_at=EARLIER))[0]


def test_different_city_is_not_collapsed():
    other = story(LATER.replace("У Запоріжжі", "У Дніпрі"), article_id=84630, source_id=101)
    assert not civic_milestone_same_event(other, story(PUBLISHED, article_id=84601, source_id=100, published_at=EARLIER))[0]


def test_new_second_location_is_an_independent_update():
    other = story(
        LATER + " Сьогодні відкрили нову філію цього простору.",
        article_id=84630, source_id=101,
    )
    assert not civic_milestone_same_event(other, story(PUBLISHED, article_id=84601, source_id=100, published_at=EARLIER))[0]


def test_later_two_months_is_not_same_first_month_event():
    older = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    later = story(
        LATER.replace("місяць тому", "два місяці тому"),
        article_id=84630, source_id=101,
    )
    assert not civic_milestone_same_event(later, older)[0]


def test_distant_day_and_unverified_timestamp_not_proven():
    older = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    later = story(LATER, article_id=84630, source_id=101,
                  published_at=(datetime.fromisoformat(T) + timedelta(days=4)).isoformat())
    assert not civic_milestone_same_event(later, older)[0]
    later["source_published_at"] = "2026-10-27 16:58:00"
    later["published_at"] = ""
    assert not civic_milestone_same_event(later, older)[0]


def test_source_name_and_video_url_alone_do_not_prove_identity():
    old = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    changed = story(
        "У Запоріжжі сьогодні відкрили новий центр підтримки ветеранів. "
        "Тут є допомога з документами та консультації.",
        article_id=84630, source_id=101,
    )
    old["media_json"] = changed["media_json"] = '["https://example.org/identical-video.mp4"]'
    assert not civic_milestone_same_event(changed, old)[0]


def test_same_source_not_merged_without_other_evidence():
    prior = story(PUBLISHED, article_id=84599, source_id=100, published_at=EARLIER)
    new = story(LATER, article_id=84630, source_id=100)
    assert not civic_milestone_same_event(new, prior)[0]
