"""2.3.12 tests: replay the completed 319 human labels and observed P0 posts.

These tests check deterministic guard boundaries and label provenance. AI
selection quality itself requires version-scoped fresh LIVE evidence; no
offline fixture is treated as proof that 319 texts were newly published.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.editorial_feedback_2312 import (
    calibrated_feedback_2312,
    source_only_promotion_veto_2312,
)
from telegram_autopilot.v2.monitoring_integrity_2312 import (
    monitoring_editorial_integrity_2312,
)


def row(raw: str, title: str = "", url: str = "https://t.me/info_zp/172134"):
    return SimpleNamespace(raw_text=raw, title=title, source_url=url)


def test_completed_operator_workbook_has_159_accepted_160_rejected_without_overlap():
    f = json.loads(
        (Path(__file__).parent / "fixtures" / "editorial_labels_2312.json").read_text(
            encoding="utf-8"
        )
    )
    assert f["terminal_previous_ids"] == {"1": 90293, "2": 90281}
    assert [(len(f["channels"][k]["accepted"]), len(f["channels"][k]["rejected"]))
            for k in ("1", "2")] == [(120, 110), (39, 50)]
    for cid, labels in f["channels"].items():
        selected, rejected = set(labels["accepted"]), set(labels["rejected"])
        assert not (selected & rejected)
        assert min(selected | rejected) > f["terminal_previous_ids"][cid]
    assert sum(len(c["accepted"]) + len(c["rejected"])
               for c in f["channels"].values()) == 319
    assert f["published_against_editor"] == {
        "1": [90311, 91085],
        "2": [90462, 90467, 90470, 90512, 90721],
    }
    for cid, ids in f["published_against_editor"].items():
        assert set(ids) <= set(f["channels"][cid]["rejected"])


def test_science_feedback_distinguishes_science_from_opinion_and_shopping():
    prompt = calibrated_feedback_2312("science")
    assert "120 із 230" in prompt
    assert "кіберзагрози" in prompt
    assert "пандемію" in prompt and "гітарних" in prompt
    assert "Не забороняй усі думки" in prompt
    assert calibrated_feedback_2312("monitoring") == ""


def test_creative_feedback_preserves_idea_led_campaigns_not_generic_branding():
    prompt = calibrated_feedback_2312("creative")
    assert "39 із 89" in prompt
    assert "Dogs Trust" in prompt and "Deutsche Telekom" in prompt
    assert "логотип пекарні" in prompt
    assert "каталожні переліки" in prompt


def test_only_explicit_deals_facing_price_promotion_gets_preference_veto():
    deal = row(
        "A tabletop console for family night is now $60 cheaper.",
        title="This tabletop console just got $60 cheaper",
        url="https://www.creativebloq.com/deals/tabletop-console-cheaper",
    )
    assert source_only_promotion_veto_2312("creative", deal) == (
        "EDITORIAL_OPERATOR_PRICE_PROMO_2312"
    )
    assert source_only_promotion_veto_2312("science", deal)
    assert not source_only_promotion_veto_2312("monitoring", deal)
    # Price or brand in a real, sourced product story isn't a deal by itself.
    assert not source_only_promotion_veto_2312("creative", row(
        "The new prototype uses carbon-fibre wheels and an unusual mechanism.",
        title="Limited prototype design with $200 components",
        url="https://www.yankodesign.com/2026/11/04/carbon-wheels/",
    ))
    assert not source_only_promotion_veto_2312("creative", row(
        "An original design story.",
        title="Introducing an original concept from a design magazine",
        url="https://www.creativebloq.com/deals/original-concept",
    ))


NATIONAL_90710 = (
    "Мережа на 21 мільйон підписників: як блогери та проросійські ресурси "
    "розкручують антимобілізаційні настрої в Україні. Як з’ясували Texty.org.ua, "
    "мережа використовує резонансні конфлікти для дискредитації мобілізації."
)


def test_published_90710_national_network_analysis_rejected_from_source():
    a = row(NATIONAL_90710)
    assert monitoring_editorial_integrity_2312(a) == (
        "MONITORING_NATIONAL_ONLY_NETWORK_ANALYSIS_2312"
    )
    channel = SimpleNamespace(
        mode=ChannelMode.MONITORING,
        policy=SimpleNamespace(monitoring_denied_origins=""),
    )
    assert hard_editorial_reject(channel, a) == (
        "MONITORING_NATIONAL_ONLY_NETWORK_ANALYSIS_2312"
    )


def test_real_local_investigation_not_blocked_by_national_network_rule():
    local = row(
        NATIONAL_90710 + " Запорізькі журналісти розкрили локальну групу "
        "поширення повідомлень у Запоріжжі."
    )
    assert monitoring_editorial_integrity_2312(local) == ""


def test_general_national_public_service_and_local_water_notice_pass():
    assert monitoring_editorial_integrity_2312(row(
        "Енергетикам, комунальникам та залізничникам доплачуватимуть "
        "за відновлення після атак. Доплата стосується працівників "
        "українських громад."
    )) == ""
    assert monitoring_editorial_integrity_2312(row(
        "Міська рада Запоріжжя повідомила, що через ремонт тимчасово "
        "не буде води у кількох будинках."
    )) == ""


def test_published_90809_unverified_serious_killing_stopped_despite_local_place():
    case = row(
        "В Гуляйполі капітан, командир мотострілецької роти, "
        "вбив двох танкістів. З контрольними пострілами у голову."
    )
    assert monitoring_editorial_integrity_2312(case) == (
        "MONITORING_UNVERIFIED_INTERNAL_KILLING_2312"
    )


def test_verified_official_case_not_blanket_blocked():
    case = row(
        "У Гуляйполі поліція офіційно підтвердила, що офіцер "
        "застрелив військовослужбовця; відкрито провадження."
    )
    assert monitoring_editorial_integrity_2312(case) == ""


def test_published_90845_anonymous_angry_veteran_opinion_without_event_stopped():
    opinion = row(
        "Заява ветерана — для тих особєй, у кого вистачає нахабства "
        "патякати в бік військових. Сором і антиукраїнські вкиди.",
        url="https://t.me/info_zp/172163",
    )
    assert monitoring_editorial_integrity_2312(opinion) == (
        "MONITORING_UNATTRIBUTED_OPINION_2312"
    )


def test_named_veteran_and_real_regional_event_remain_eligible():
    assert monitoring_editorial_integrity_2312(row(
        "Запорізький ветеран засудив антиукраїнські вкиди та "
        "оголосив у Запоріжжі нову програму допомоги сім’ям."
    )) == ""
    assert monitoring_editorial_integrity_2312(row(
        "Заява ветерана: Петро Коваленко обурився поширенням дезінформації."
    )) == ""
