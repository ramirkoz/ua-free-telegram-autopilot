"""2.3.17: original-source regional scope and retailer advertising regressions.

No operator SQLite, Telegram send, remote AI or retroactive publication.
"""
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import (
    EditorialEngine, hard_editorial_reject, prepublish_quality_issues,
)
from telegram_autopilot.v2.monitoring_source_scope_2317 import (
    monitoring_source_scope_reason_2317,
)
from telegram_autopilot.v2.source_fact_integrity import non_overridable_quality_issues


def channel(mode=ChannelMode.MONITORING, opted_in=True):
    return ChannelConfig(
        id=3, name="Будь-який регіональний канал", telegram_chat_id="-100123",
        mode=mode,
        policy=ChannelPolicy(
            channel_id=3,
            rejection_rules="[LIVE_NOW_RC96]" if opted_in else "",
        ),
    )


def article(title, body, name="5 РЕДАКЦІЯ"):
    return {
        "id": 92302, "title": title, "raw_text": body,
        "source_name": name, "source_url": "https://t.me/publisher/123",
    }


PENGUINS = article(
    "Біля української станції «Вернадський» з'явилися перші пінгвінячі яйця",
    "В Антарктиді пінгвіни почали кладку яєць. "
    "Біля станції у гніздах уже нарахували 14 яєць. "
    "Батьки висиджують кладки.",
    name="Запоріжжя | місцевий Telegram",  # brand is not event evidence
)
COMFY_FLYER = article(
    "У Запоріжжі відкрили новий магазин техніки",
    "6 листопада у Запоріжжі відкривається магазин на проспекті Соборному. "
    "Знижки до 60% на товари, телевізор за 9 999 грн. "
    "Завітайте та купуйте товари за акційними цінами.",
)
NEUTRAL_OPENING = article(
    "У Запоріжжі відкрився новий магазин",
    "6 листопада у Запоріжжі відкрили магазин на проспекті Соборному. "
    "У закладі облаштовано доступний вхід, а персонал пройшов навчання.",
)
LOCAL_PUBLIC_SALE = article(
    "У Запоріжжі стартувала програма пільгових закупівель",
    "Соціальний магазин у Запоріжжі запровадив знижки для ВПО. "
    "Переселенці можуть придбати необхідні речі за 200 грн.",
)
TRAIN = article(
    "Зміни руху транспорту у Запоріжжі 6 листопада",
    "У Запоріжжі через роботи на дамбі змінився рух транспорту. "
    "Тролейбус №3 з 08:00 до 17:00 курсує за об'їзним маршрутом.",
)


def test_nonlocal_nature_must_not_borrow_locality_from_publisher_name():
    assert monitoring_source_scope_reason_2317(channel(), PENGUINS) == (
        "MONITORING_NONLOCAL_NATURE_2317"
    )


def test_retail_sale_flyer_not_equal_local_business_opening():
    assert monitoring_source_scope_reason_2317(channel(), COMFY_FLYER) == (
        "MONITORING_RETAIL_FLYER_2317"
    )
    assert monitoring_source_scope_reason_2317(channel(), NEUTRAL_OPENING) == ""


def test_local_transport_and_public_benefit_pass_source_scope():
    assert monitoring_source_scope_reason_2317(channel(), TRAIN) == ""
    assert monitoring_source_scope_reason_2317(channel(), LOCAL_PUBLIC_SALE) == ""


def test_opt_in_and_channel_mode_isolation():
    assert monitoring_source_scope_reason_2317(channel(opted_in=False), PENGUINS) == ""
    assert monitoring_source_scope_reason_2317(channel(ChannelMode.EDITORIAL), COMFY_FLYER) == ""


def test_source_veto_prevents_ai_selector_and_is_repeated_at_publish_boundary():
    ch = channel()
    engine = object.__new__(EditorialEngine)
    engine.gateway = SimpleNamespace(run=lambda *args, **kwargs: (
        _ for _ in ()
    ).throw(AssertionError("AI must not evaluate a source-only rejected article")))
    for bad, reason in (
        (PENGUINS, "MONITORING_NONLOCAL_NATURE_2317"),
        (COMFY_FLYER, "MONITORING_RETAIL_FLYER_2317"),
    ):
        outcome = engine.select(ch, bad)
        assert str(outcome.decision).upper().endswith("REJECT")
        assert outcome.reason == reason
        assert hard_editorial_reject(ch, bad, "Коректний за формою текст. Ще одне речення.") == reason
        assert reason in non_overridable_quality_issues(
            ch, bad, "Коректний за формою текст. Ще одне речення."
        )
        assert reason in prepublish_quality_issues(
            ch, bad, "Коректний за формою текст. Ще одне речення."
        )
