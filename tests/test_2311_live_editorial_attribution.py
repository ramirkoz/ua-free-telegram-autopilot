"""2.3.11 regressions from 04 Nov verified v2.3.10 operator SQLite.

Case #90628 is a nationwide NABU/SAP investigation copied into a ZP
newsroom feed, not regional news; #90617 is a genuine local assistance
notice with a source-owned phone line, not an incomplete AI sentence.
"""
from types import SimpleNamespace

from telegram_autopilot.v2.editorial import _source_owned_practical_tail
from telegram_autopilot.v2.live_editorial_integrity_2311 import (
    national_criminal_case_without_local_2311,
    unattributed_criminal_allegation_2311,
)


def article(raw_text, title="", source_url="https://t.me/info_zp/172123"):
    return SimpleNamespace(raw_text=raw_text, title=title, source_url=source_url)


NABU_SOURCE_90628 = (
    "Офіційно: НАБУ і САП викрили злочинну організацію, учасники "
    "якої налагодили підкуп правоохоронців за безперешкодну діяльність "
    "шахрайських колцентрів. Організатором був раніше засуджений чоловік. "
    "Під прикриттям правоохоронців учасники забезпечували роботу колцентрів. "
    "Ми в 📲 WhatsApp."
)


def test_national_investigation_in_local_aggregator_rejected():
    assert national_criminal_case_without_local_2311(article(NABU_SOURCE_90628)) == (
        "MONITORING_NONLOCAL_NATIONAL_CRIMINAL_CASE_2311"
    )


def test_local_nabu_case_not_globally_banned():
    text = "НАБУ повідомило про підозру посадовцю Запорізької міської ради. " \
           "За версією слідства, підозрюваний отримував хабарі у Запоріжжі."
    assert national_criminal_case_without_local_2311(article(text)) == ""


def test_genuine_regional_service_not_banned():
    text = "У Терпіннівській громаді Запорізької області працює служба допомоги дітям. " \
           "За довідками телефонуйте до служби у справах дітей."
    assert national_criminal_case_without_local_2311(article(text)) == ""


def test_general_national_civic_notice_still_allowed():
    assert national_criminal_case_without_local_2311(article(
        "НСЗУ відкрила електронну мапу безоплатної психологічної допомоги. "
        "Послуга доступна жителям усіх областей."
    )) == ""


def test_unqualified_guilt_in_90628_final_rejected():
    text = (
        "НАБУ і САП викрили злочинну організацію, яка підкуповувала "
        "правоохоронців заради діяльності шахрайських колцентрів. "
        "Організатором став раніше засуджений чоловік. "
        "Угруповання забезпечувало роботу колцентрів."
    )
    assert unattributed_criminal_allegation_2311(article(NABU_SOURCE_90628), text) == (
        "MONITORING_UNATTRIBUTED_CRIMINAL_ALLEGATION_2311"
    )


def test_qualified_investigation_report_allowed():
    text = (
        "За даними НАБУ і САП, слідство викрило ймовірну схему підкупу "
        "посадовців для роботи шахрайських колцентрів. "
        "Правоохоронці підозрюють групу людей у причетності до неї."
    )
    assert unattributed_criminal_allegation_2311(article(NABU_SOURCE_90628), text) == ""


def test_source_record_with_court_verdict_not_misclassified():
    row = article(
        "За вироком суду в Запоріжжі доведено підкуп посадовця. "
        "НАБУ повідомило про завершення розслідування."
    )
    assert unattributed_criminal_allegation_2311(row, "За вироком суду особа винна.") == ""


def test_source_owned_phone_tail_is_complete():
    row = article(
        "У Запорізькій області доступна консультація. "
        "Телефон гарячої лінії: 0 800 100 102."
    )
    assert _source_owned_practical_tail(
        row,
        "Громади можуть отримати психологічну консультацію за гарячою лінією.\n\n"
        "Телефон: 0 800 100 102",
    )


def test_random_numeric_tail_stays_blocked():
    row = article("Надають консультації: 0 800 100 102. Новини з області.")
    assert not _source_owned_practical_tail(
        row, "Громади отримали консультації за номером 2026"
    )
    assert not _source_owned_practical_tail(
        row, "Громади можуть звернутися та\n\nТелефон: 0 800 100 102"
    )
    assert not _source_owned_practical_tail(
        row, "Громади отримують консультації.\n\nТелефон: 0 800 000 000"
    )


def test_unrelated_legal_story_without_allegation_trigger_untouched():
    row = article("У Запоріжжі поліція відкрила новий центр допомоги свідкам.")
    assert unattributed_criminal_allegation_2311(row, "Поліція відкрила центр.") == ""


def test_prepublish_guard_blocks_older_ready_without_local_case():
    from telegram_autopilot.v2.domain import ChannelMode
    from telegram_autopilot.v2.editorial import hard_editorial_reject
    channel = SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(monitoring_denied_origins=""),
    )
    assert hard_editorial_reject(channel, article(NABU_SOURCE_90628)) == (
        "MONITORING_NONLOCAL_NATIONAL_CRIMINAL_CASE_2311"
    )


def test_human_approval_cannot_bypass_unattributed_criminal_case():
    from telegram_autopilot.v2.domain import ChannelMode
    from telegram_autopilot.v2.source_fact_integrity import non_overridable_quality_issues
    row = article(
        NABU_SOURCE_90628 + " За повідомленням відомства ведеться розслідування."
    )
    channel = SimpleNamespace(mode=ChannelMode.MONITORING)
    final = (
        "НАБУ і САП розслідують ймовірну діяльність колцентрів. "
        "Організатором став раніше засуджений чоловік, який підкуповував посадовців."
    )
    assert "MONITORING_UNATTRIBUTED_CRIMINAL_ALLEGATION_2311" in (
        non_overridable_quality_issues(channel, row, final)
    )
