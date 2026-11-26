"""2.3.53 regression: valid original must not be silenced by rejected anchor.

Observed 23 Nov: 111301 and 111303 had 686 meaningful characters but were
DEDUPED to 111304 (303 chars) which was later rejected. Test IDs are evidence
labels only. No Telegram writes, no operator database or remote reads.
"""
from types import SimpleNamespace

from telegram_autopilot.v2.dedupe_eligible_winner_2353 import eligible_event_anchor_2353
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.monitoring_short_material_2352 import monitoring_short_material_reason_2352
from telegram_autopilot.v2.semantic_dedupe import _breaking_incident_same_event


def monitoring():
    return ChannelConfig(
        id=3, name="Моніторинг", telegram_chat_id="@none",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(target_min_chars=500, target_max_chars=750),
    )


def article(body, *, stage="COLLECTED", decision="PENDING"):
    return SimpleNamespace(
        raw_text=body, title="Виплата житлових сертифікатів",
        stage=stage, decision=decision, article_layout_json="{}",
        source_name="ЗМІ Запоріжжя", source_url="https://t.me/original/1",
    )


def housing_text():
    return (
        "У Запоріжжі сім'ї отримали чотири житлові сертифікати на 7,1 млн грн. "
        "Зареєстровано 650 звернень, 98 із них перебувають на розгляді. "
        "Міська комісія опрацювала документи, а отримувачі мають право "
        "обрати житло за встановленою процедурою. "
    ) * 4


def test_111301_111303_not_anchored_to_111304_short_unpublished():
    incoming = article(housing_text())
    short_anchor = article(
        "У Запоріжжі жителі оформлюють житлові сертифікати. "
        "Комісія опрацьовує звернення про пошкоджене житло. "
    )
    assert len(short_anchor.raw_text) < 500 < len(incoming.raw_text)
    assert not monitoring_short_material_reason_2352(monitoring(), short_anchor)
    assert not eligible_event_anchor_2353(monitoring(), incoming, short_anchor)
    assert not eligible_event_anchor_2353(
        monitoring(), incoming, article(short_anchor.raw_text, decision="REJECT")
    )


def test_existing_complete_same_event_can_be_anchor():
    original = housing_text()
    assert eligible_event_anchor_2353(monitoring(), article(original), article(original))


def test_richer_incoming_source_not_silenced_by_uncommitted_weaker_one():
    full = article(housing_text())
    partial = article(housing_text()[:525], stage="EXTRACTED")
    assert not eligible_event_anchor_2353(monitoring(), full, partial)
    # A completed, previously published item remains a valid delivery anchor.
    assert eligible_event_anchor_2353(
        monitoring(), full, article(partial.raw_text, stage="PUBLISHED", decision="PUBLISH")
    )


def test_historical_short_but_published_source_remains_ledger_protection():
    previously_published = article("Коротке повідомлення.", stage="PUBLISHED", decision="PUBLISH")
    assert eligible_event_anchor_2353(monitoring(), article(housing_text()), previously_published)


def test_civic_support_guides_do_not_look_like_same_breaking_incident():
    children = {
        "source_id": 1, "title": "Як оформити статус дитини, постраждалої внаслідок війни",
        "raw_text": "Дитина, яка постраждала від обстрілу, може отримати статус. "
                    "Для оформлення потрібні документи, подача заяви та рішення комісії.",
    }
    veterans = {
        "source_id": 2, "title": "Послуги психологічної підтримки ветеранів",
        "raw_text": "Ветерани, які постраждали внаслідок обстрілів, отримують "
                    "медичну психологічну допомогу. Заявку можна подати у центрі.",
    }
    assert not _breaking_incident_same_event(children, veterans)[0]


def test_damage_and_housing_certificates_are_not_a_breaking_incident():
    a = {
        "source_id": 1, "title": "Видача сертифікатів за пошкоджене житло у Запоріжжі",
        "raw_text": housing_text(),
    }
    b = {
        "source_id": 2, "title": "Компенсація за зруйноване житло",
        "raw_text": housing_text().replace("отримали", "видали"),
    }
    assert not _breaking_incident_same_event(a, b)[0]


def test_real_attack_still_eligible_for_incident_matcher():
    a = {"source_id": 1, "title": "Обстріл житлових будинків у Запоріжжі",
         "raw_text": "Через російську атаку в Запоріжжі пошкоджені житлові будинки. "
                     "Зруйнована частина фасаду, комісія фіксує наслідки."}
    b = {"source_id": 2, "title": "Атака на житловий квартал Запоріжжя",
         "raw_text": "Після обстрілу Запоріжжя пошкоджено житлові будинки. "
                     "Місцева комісія фіксує зруйновані частини будівель."}
    assert _breaking_incident_same_event(a, b)[0]


def test_other_channels_remain_outside_monitoring_eligibility():
    other = ChannelConfig(id=2, name="Креатив", telegram_chat_id="@none",
                          mode=ChannelMode.EDITORIAL, policy=ChannelPolicy(target_min_chars=500))
    assert eligible_event_anchor_2353(other, article(housing_text()), article("Short"))
