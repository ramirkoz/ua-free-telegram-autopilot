from __future__ import annotations

import json
from datetime import datetime, timezone

from telegram_autopilot import rc79_runtime as rc79
from telegram_autopilot.rc59_universal_policy import ChannelPolicy


def test_telegram_forward_metadata_and_adjacent_media_stitching():
    html = """
    <div class="tgme_widget_message" data-post="demo/100">
      <div class="tgme_widget_message_forwarded_from">Переслано від Іван Федоров</div>
      <div class="tgme_widget_message_text">Важливий текст громади</div>
      <time datetime="2026-09-07T10:00:00+00:00"></time>
    </div>
    <div class="tgme_widget_message" data-post="demo/101">
      <a style="background-image:url('https://cdn.example/a.jpg')"></a>
      <time datetime="2026-09-07T10:00:20+00:00"></time>
    </div>
    <div class="tgme_widget_message" data-post="demo/102">
      <a style="background-image:url('https://cdn.example/b.jpg')"></a>
      <time datetime="2026-09-07T10:00:30+00:00"></time>
    </div>
    """
    parser = rc79._TelegramRC79Parser("demo")
    parser.feed(html)
    parser.close()
    items = rc79._stitch_telegram_entries(
        "demo", parser.entries, now=datetime(2026, 9, 7, 11, 0, tzinfo=timezone.utc)
    )
    assert len(items) == 1
    item = items[0]
    assert item.raw_text == "Важливий текст громади"
    assert len(item.media_urls) == 2
    layout = json.loads(item.article_layout_json)
    assert layout["telegram"]["forwarded"] is True
    assert layout["telegram"]["stitched"] is True
    assert layout["telegram"]["message_ids"] == ["100", "101", "102"]
    assert layout["telegram"]["media_count"] == 2


def test_telegram_latest_text_only_is_held_for_media_grace_window():
    html = """
    <div class="tgme_widget_message" data-post="demo/200">
      <div class="tgme_widget_message_text">Щойно опублікований текст</div>
      <time datetime="2026-09-07T10:00:00+00:00"></time>
    </div>
    """
    parser = rc79._TelegramRC79Parser("demo")
    parser.feed(html)
    parser.close()
    items = rc79._stitch_telegram_entries(
        "demo", parser.entries, now=datetime(2026, 9, 7, 10, 1, tzinfo=timezone.utc)
    )
    assert items == []


def test_media_first_then_text_is_one_logical_post():
    html = """
    <div class="tgme_widget_message" data-post="demo/300">
      <a style="background-image:url('https://cdn.example/a.jpg')"></a>
      <time datetime="2026-09-07T10:00:00+00:00"></time>
    </div>
    <div class="tgme_widget_message" data-post="demo/301">
      <div class="tgme_widget_message_text">Пояснення до фото</div>
      <time datetime="2026-09-07T10:00:20+00:00"></time>
    </div>
    """
    parser = rc79._TelegramRC79Parser("demo")
    parser.feed(html)
    parser.close()
    items = rc79._stitch_telegram_entries(
        "demo", parser.entries, now=datetime(2026, 9, 7, 11, 0, tzinfo=timezone.utc)
    )
    assert len(items) == 1
    assert items[0].raw_text == "Пояснення до фото"
    assert len(items[0].media_urls) == 1


def test_local_monitoring_exclusions_are_driven_by_saved_rules():
    policy = ChannelPolicy(
        rejection_rules=(
            "Не брати репости та переслані повідомлення. "
            "Не брати повітряні тривоги та відбій. "
            "Не брати протокольні привітання і календарні свята. "
            "Не брати побажання гарного дня та пости настрою без події."
        )
    )
    forwarded = {
        "title": "Новина",
        "raw_text": "Текст",
        "article_layout_json": json.dumps(
            {"version": 79, "source_kind": "telegram", "telegram": {"forwarded": True}}
        ),
    }
    assert "репост" in rc79._configured_local_monitoring_exclusion(policy, forwarded).casefold()

    alert = {"title": "Повітряна тривога", "raw_text": "У Запорізькій області повітряна тривога"}
    assert "тривог" in rc79._configured_local_monitoring_exclusion(policy, alert).casefold()

    greeting = {"title": "З Днем розвідки", "raw_text": "Щиро вітаємо розвідників та бажаємо міцного здоров'я"}
    assert "привітан" in rc79._configured_local_monitoring_exclusion(policy, greeting).casefold()

    mood = {"title": "Доброго ранку", "raw_text": "Нехай усе заплановане вдасться. Гарного дня!"}
    assert "побажан" in rc79._configured_local_monitoring_exclusion(policy, mood).casefold()


def test_forward_is_not_hidden_global_rule_when_channel_does_not_forbid_it():
    policy = ChannelPolicy(rejection_rules="Не брати лише оголошення без дати.")
    article = {
        "title": "Новина",
        "raw_text": "Текст",
        "article_layout_json": json.dumps(
            {"version": 79, "source_kind": "telegram", "telegram": {"forwarded": True}}
        ),
    }
    assert rc79._configured_local_monitoring_exclusion(policy, article) == ""


def test_actionable_facts_keep_phone_url_and_address_line():
    article = {
        "title": "Безоплатна правова допомога",
        "raw_text": (
            "Консультації надають за адресою: м. Запоріжжя, вул. Південноукраїнська, 3.\n"
            "Телефон: +38 (097) 021 41 53.\n"
            "Telegram: https://t.me/zatyshnoZaporizhzhia"
        ),
    }
    facts = "\n".join(rc79._extract_actionable_facts(article))
    assert "+38 (097) 021 41 53" in facts
    assert "https://t.me/zatyshnoZaporizhzhia" in facts
    assert "Південноукраїнська" in facts


def test_compact_multisource_footer_uses_labels_not_raw_urls():
    text, entities = rc79._caption_with_sources(
        "Короткий пост.",
        ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        hard_limit=900,
    )
    assert "Джерело 1 · Джерело 2 · Джерело 3" in text
    assert "https://example.com" not in text
    assert [x["url"] for x in entities] == [
        "https://example.com/a", "https://example.com/b", "https://example.com/c"
    ]


def test_policy_fit_mechanism_lane_accepts_strong_mechanism_without_big_stakes():
    rc79._PREV["value_allowed"] = lambda data: (False, "legacy_reject", 53)
    data = {
        "mechanism": 63,
        "consequence_or_insight": 45,
        "reader_payoff": 60,
        "retellability": 58,
        "novelty": 55,
    }
    allowed, code, score = rc79._policy_value_allowed(data, 80)
    assert allowed is True
    assert code == "policy_fit_mechanism_lane"
    assert score == 53


def test_event_anchor_guard_keeps_same_topic_different_event_related():
    rc79._PREV["fallback_relation"] = lambda *_args: ("DUPLICATE", "legacy")
    a = {
        "title": "DLSS 5 запустили на AMD RDNA 4 через мод",
        "raw_text": "RX 9070 XT та DLSS 5",
    }
    b = {
        "title": "DLSS 5 офіційно запустили в NBA 2K27",
        "raw_text": "RTX 50 та DLSS 5 у NBA 2K27",
    }
    relation, reason = rc79._fallback_relation_rc79(a, b, None, None)
    assert relation == "RELATED"
    assert "event-anchor" in reason
