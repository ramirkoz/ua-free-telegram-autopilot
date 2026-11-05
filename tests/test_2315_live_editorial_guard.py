"""2.3.15 production P0 regressions, based on verified 5 Nov operator posts.

No Telegram send, writable DB, external AI, or historical replay.
"""
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import (
    EditorialEngine, hard_editorial_reject, prepublish_quality_issues,
)
from telegram_autopilot.v2.source_fact_integrity import (
    non_overridable_quality_issues, source_fact_issues,
)
from telegram_autopilot.v2.source_safety_2315 import (
    monitoring_invite_bait_reason, source_action_certainty_issues,
)


def channel(mode=ChannelMode.MONITORING):
    return ChannelConfig(
        id=3, name="Тестова регіональна редакція", telegram_chat_id="-100123",
        mode=mode, policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]"),
    )


def row(raw, *, title=None, url="https://t.me/zaborzp/157367"):
    return {
        "id": 91610, "channel_id": 3, "source_id": 191,
        "title": title if title is not None else raw,
        "raw_text": raw, "source_url": url, "canonical_source_url": url,
    }


BAIT = (
    "‼️‼️‼️‼️‼️ ⚠️😱 Зʼявились перші жахливі кадри з Запоріжжя ⬇️ "
    "❗️ https://t.me/+cpvWceQ5plI3ZjIy "
    "(Терміново перегляньте, це повний пздц… 🤯)"
    "🤬Підараси…інших слів немає …Всі переглянули?! Видаляємо за 3 хв…🤯👆"
)
BAIT_FINAL = (
    "У мережі з’явилися перші кадри з Запоріжжя. "
    "Детальнішої офіційної інформації щодо події у джерелі наразі не наведено."
)
TRAIN_SOURCE = (
    "З 5 листопада скасовуються електропоїзди Запоріжжя - Канцерівка. "
    "Про це повідомляє Укрзалізниця. "
    "№6502 Канцерівка – Запоріжжя-2; №6075 Запоріжжя-2 - Канцерівка; "
    "№6498/6497 Канцерівка - Запоріжжя-2."
)
TRAIN_FINAL = (
    "З 5 листопада скасовано електропоїзди Запоріжжя - Канцерівка. "
    "За повідомленням Укрзалізниці, зміни стосуються рейсів №6502, №6075 та №6498/6497."
)
CRIME_SOURCE = (
    "За процесуального керівництва прокуратури до суду скеровано обвинувальний акт "
    "щодо чотирьох чоловіків. Правоохоронці викрили лісорубів «на гарячому» "
    "під час незаконної порубки дерев. Екологічна шкода перевищує 1,7 млн грн."
)
CRIME_BAD = (
    "До суду скерували обвинувальний акт щодо чотирьох чоловіків. "
    "Правоохоронці затримали лісорубів під час незаконної порубки."
)
CRIME_GOOD = (
    "До суду скерували обвинувальний акт щодо чотирьох чоловіків. "
    "Правоохоронці викрили лісорубів під час незаконної порубки."
)
COUNCIL_SOURCE = (
    "5 листопада відбулося засідання Вільнянської міської ради. "
    "До порядку денного включили 21 питання. "
    "Зокрема, у порядку денному були питання щодо затвердження Положення "
    "про громадські слухання, оренди комунального майна та земельних відносин. "
    "За результатами розгляду депутати ухвалили відповідні рішення."
)
COUNCIL_BAD = (
    "На засіданні Вільнянської міської ради депутати розглянули 21 питання. "
    "Також затвердили Положення про громадські слухання, оренду майна та землекористування."
)
COUNCIL_GOOD = (
    "На засіданні Вільнянської міської ради депутати розглянули 21 питання. "
    "У порядку денному були питання щодо Положення про громадські слухання."
)


def test_actual_91610_bait_veto_before_ai_selection():
    ch = channel()
    fake = SimpleNamespace(run=lambda *args, **kw: (_ for _ in ()).throw(
        AssertionError("AI selector must not see unsafe source")))
    engine = object.__new__(EditorialEngine)
    engine.gateway = fake
    result = engine.select(ch, row(BAIT))
    assert str(result.decision).upper().endswith("REJECT")
    assert result.reason == "MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315"


def test_actual_91610_bait_veto_at_all_send_gates():
    article = row(BAIT)
    ch = channel()
    assert monitoring_invite_bait_reason(article) == "MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315"
    assert hard_editorial_reject(ch, article, BAIT_FINAL) == "MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315"
    assert "MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315" in non_overridable_quality_issues(ch, article, BAIT_FINAL)
    assert any("MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315" in issue
               for issue in prepublish_quality_issues(ch, article, BAIT_FINAL))


def test_actual_train_91614_not_blocked_or_publisher_blacklisted():
    article = row(TRAIN_SOURCE, url="https://t.me/zaborzp/157371")
    assert monitoring_invite_bait_reason(article) == ""
    assert hard_editorial_reject(channel(), article, TRAIN_FINAL) == ""
    assert "MONITORING_UNVERIFIED_FOOTAGE_INVITE_2315" not in non_overridable_quality_issues(
        channel(), article, TRAIN_FINAL
    )


def test_real_service_and_complete_invite_survive():
    complete = (
        "Запорізька громада передала переселенцям 150 продуктових наборів. "
        "Допомогу отримали родини, які звернулися до центру. "
        "Деталі у чаті https://t.me/+UGlLh2-lxcI0NWRi; "
        "приєднуйтесь зараз, щоб уточнити години."
    )
    article = row(complete)
    assert monitoring_invite_bait_reason(article) == ""


def test_without_invite_simple_real_footage_news_is_not_blocked():
    source = (
        "У Запоріжжі зафіксували наслідки обстрілу. "
        "Рятувальники повідомили про пошкодження будівлі, "
        "після чого оприлюднили кадри з місця."
    )
    assert monitoring_invite_bait_reason(row(source)) == ""


def test_action_91511_exposed_does_not_mean_arrested():
    article = row(CRIME_SOURCE, url="https://t.me/zap_gp_gov_ua/5233")
    assert source_action_certainty_issues(article, CRIME_BAD) == (
        "FACT_LAW_ENFORCEMENT_EXPOSURE_NOT_ARREST_2315",
    )
    assert "FACT_LAW_ENFORCEMENT_EXPOSURE_NOT_ARREST_2315" in source_fact_issues(article, CRIME_BAD)
    assert "FACT_LAW_ENFORCEMENT_EXPOSURE_NOT_ARREST_2315" in non_overridable_quality_issues(
        channel(), article, CRIME_BAD
    )
    assert source_action_certainty_issues(article, CRIME_GOOD) == ()


def test_actual_source_explicit_arrest_is_allowed():
    source = CRIME_SOURCE + " Після викриття поліція затримала двох підозрюваних."
    assert source_action_certainty_issues(row(source), CRIME_BAD) == ()


def test_action_91519_agenda_not_specific_document_approval():
    article = row(COUNCIL_SOURCE, url="https://t.me/vilnanskamtg/13624")
    assert source_action_certainty_issues(article, COUNCIL_BAD) == (
        "FACT_COUNCIL_AGENDA_NOT_DOCUMENT_APPROVAL_2315",
    )
    assert "FACT_COUNCIL_AGENDA_NOT_DOCUMENT_APPROVAL_2315" in source_fact_issues(article, COUNCIL_BAD)
    assert source_action_certainty_issues(article, COUNCIL_GOOD) == ()


def test_actual_document_approval_supported_when_source_explicit():
    source = COUNCIL_SOURCE + " Депутати затвердили Положення про громадські слухання."
    assert source_action_certainty_issues(row(source), COUNCIL_BAD) == ()


def test_non_monitoring_channel_keeps_source_bait_policy_isolated():
    assert hard_editorial_reject(channel(ChannelMode.EDITORIAL), row(BAIT), BAIT_FINAL) == ""


def test_source_91518_thanks_must_not_become_our_voice():
    from telegram_autopilot.v2.monitoring_source_voice_230 import source_voice_output_reason
    article = row(
        "4 листопада громаді передали гуманітарну допомогу. "
        "Одяг, взуття та ковдри отримали мешканці. "
        "Щиро дякуємо нашим німецьким партнерам за підтримку.",
        url="https://t.me/dniprorudnevma/27116",
    )
    faulty = (
        "Мешканці отримали гуманітарну допомогу від партнерів. "
        "\nДякуємо всім, хто долучився до передачі."
    )
    sober = (
        "4 листопада мешканці отримали гуманітарну допомогу від німецьких партнерів. "
        "Передали одяг, взуття та ковдри."
    )
    assert source_voice_output_reason(article, faulty) == "MONITORING_BORROWED_THANKS_VOICE_2315"
    assert "MONITORING_BORROWED_THANKS_VOICE_2315" == hard_editorial_reject(channel(), article, faulty)
    assert source_voice_output_reason(article, sober) == ""


def test_observed_ctrl_ua_grammar_blocks_but_correct_variants_pass():
    from telegram_autopilot.ukrainian_quality import final_language_blockers
    assert final_language_blockers("Це рідкісний знахід у стародавній печері.")
    assert final_language_blockers("Птаха майже не зустрічають у дикій природи.")
    assert not final_language_blockers("Це рідкісна знахідка у стародавній печері.")
    assert not final_language_blockers("Птаха майже не зустрічають у дикій природі.")
