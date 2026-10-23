"""2.2.27 regressions: source-owned fact card, queue pressure, exact post media."""
import json
from types import SimpleNamespace

from telegram_autopilot.v2.source_fact_card import build_source_fact_card
from telegram_autopilot.v2.capacity_pressure import capacity_window
from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.media_pipeline import build_publication_media_bundle
from telegram_autopilot.v2 import telegram_media_publish_guard as guard


def _row(raw, title="Madewell and New York Public Library launch a collaboration"):
    return {
        "id": 76521,
        "title": title,
        "raw_text": raw,
        "canonical_source_url": "https://example.org/real-article",
        "source_published_at": "2026-10-23T12:00:00Z",
    }


def test_fact_card_keeps_survey_denominator_and_source_spans():
    raw = (
        "Madewell partnered with New York Public Library on a 15-item collection. "
        "The label will donate $100,000 to support the library. "
        "According to a 2025 study, 28% of Americans read for pleasure on an average day in 2004, "
        "compared with 16% in 2023. These figures track participation on an average day, "
        "not the number of books read by each person."
    )
    card = build_source_fact_card(_row(raw))
    assert card.source_spans_valid(raw)
    assert "Madewell" in card.text and "New York Public Library" in card.text
    assert "28%" in card.text and "16%" in card.text
    assert any("average day" in x for x in card.statistic_contexts)
    assert "ANGLE не є доказом" in card.text
    assert "удвічі рідше" not in card.text


def test_fact_card_does_not_invent_actor_or_statistic_for_short_source():
    raw = "Міська рада повідомила про відкриття ЦНАП. Прийом розпочнеться 26 жовтня."
    card = build_source_fact_card(_row(raw, title="Повідомлення громади"))
    assert card.source_spans_valid(raw)
    assert "26 жовтня" in card.text
    assert not card.statistic_contexts
    assert "New York Public Library" not in card.text


def test_fact_card_bounded_and_no_external_facts_added():
    raw = "Новина про громадські послуги. " + "Деталі та пояснення для мешканців. " * 350
    card = build_source_fact_card(_row(raw), char_budget=620)
    assert len(card.text) <= 620
    assert card.source_spans_valid(raw)
    assert card.truncated
    assert "SOURCE ID:" in card.text


def test_capacity_reports_pressure_without_silent_operator_changes():
    data = capacity_window(
        pending_jobs=110, min_interval_minutes=45,
        publish_24h=False, publish_start="08:00", publish_end="20:00",
        max_age_hours=24,
    )
    assert data["overloaded"] and data["pending_selection"] == "FRESHNESS_FIRST"
    assert data["selection_jobs_per_possible_post_slot"] > 6
    assert data["selection_pressure"] == "HIGH"
    assert data["jobs_are_not_posts"]
    assert not data["automatic_drop_or_interval_change"]
    assert data["preserves_operator_interval"]


class _Store:
    def __init__(self):
        self.updated = []
        self.blocked = []

    def update_article(self, article_id, **fields):
        self.updated.append((article_id, fields))

    def publication_backoff(self, article_id, **kwargs):
        self.blocked.append((article_id, kwargs))


def _media_case():
    source_image = "https://cdn.example.org/real.jpg"
    neighbour_image = "https://cdn.example.org/other-post.jpg"
    article = {
        "id": 76810, "title": "Офіційна новина",
        "raw_text": "У громаді оголосили про новий захід.",
        "canonical_source_url": "https://t.me/officialrada/76810",
        "media_json": json.dumps([source_image, neighbour_image]),
        "article_layout_json": json.dumps({
            "source_kind": "telegram",
            "telegram": {"media_count": 2, "message_ids": ["76810", "76811"]},
            "blocks": [
                {"type": "media", "kind": "image", "url": source_image},
                {"type": "media", "kind": "image", "url": neighbour_image},
            ],
        }),
    }
    channel = SimpleNamespace(id=3, mode=ChannelMode.MONITORING)
    check = SimpleNamespace(
        outcome="confirmed", media=(source_image,), expected_photos=1,
        video_expected=False, photo_signal="photo_wrap", video_signal="",
        reason="exact_post_media_confirmed",
    )
    return article, channel, check, source_image, neighbour_image


def test_exact_post_media_replaces_neighbour_contamination(monkeypatch):
    article, channel, check, real, other = _media_case()
    monkeypatch.setattr(guard, "check_exact_telegram_media", lambda url: check)
    store = _Store()
    publisher = SimpleNamespace(store=store)
    bundle = build_publication_media_bundle(channel, article)
    result = guard.enforce_source_media_parity(
        publisher, channel, article["id"], article, bundle,
        article["canonical_source_url"],
    )
    assert isinstance(result, tuple)
    clean_article, clean_bundle = result
    assert clean_bundle.encoded_items == [real] or tuple(clean_bundle.encoded_items) == (real,)
    assert other not in clean_article["media_json"]
    assert len(store.updated) == 1
    assert not store.blocked


def test_no_media_repair_without_positive_exact_source_confirmation(monkeypatch):
    article, channel, check, real, other = _media_case()
    check.outcome = "uncertain"
    monkeypatch.setattr(guard, "check_exact_telegram_media", lambda url: check)
    store = _Store()
    bundle = build_publication_media_bundle(channel, article)
    guard.enforce_source_media_parity(
        SimpleNamespace(store=store), channel, article["id"],
        article, bundle, article["canonical_source_url"],
    )
    assert not store.updated
