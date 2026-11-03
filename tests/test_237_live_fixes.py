"""2.3.7: source-grounded 03-Nov operator regressions; zero LIVE mutations."""
from __future__ import annotations

from types import SimpleNamespace

from telegram_autopilot.v2.monitoring_event_update_237 import (
    clean_event_boilerplate_237, material_monitoring_update_237,
)
from telegram_autopilot.v2.event_dedupe_guard import (
    event_fingerprint_same_event, _fingerprint_stats, _validated_cluster_same_event,
)
from telegram_autopilot.v2.editorial_copyedit_237 import (
    copyedit_issues_237, safe_copyedit_237,
)
from telegram_autopilot.v2.editorial import _rc111_prepare_candidate
from telegram_autopilot.v2.domain import ChannelMode


def row(raw: str, *, title: str = "", source_id: int = 1) -> dict:
    return {"title": title or raw, "raw_text": raw, "source_id": source_id,
            "final_text": "", "event_summary": ""}


def test_mourning_update_29_deaths_and_three_days_are_new_event_facts():
    old = row("Завтра, 3 листопада, у Запорізькій області День жалоби по Комишувасі. "
              "Відомо про 24 загиблих людей, є поранені та зниклі безвісти.", source_id=139)
    new = row("3, 4 та 5 листопада — дні жалоби в Запорізькій області за загиблими "
              "від удару по Комишувасі. 29 загиблих, 5 поранених, 48 зниклих безвісти.", source_id=180)
    assert material_monitoring_update_237(new, old) == "MONITORING_MATERIAL_CASUALTY_UPDATE_237"
    assert not event_fingerprint_same_event(new, old, monitoring_profile=True)[0]
    equal = row("3, 4 та 5 листопада дні жалоби. Відомо про 29 загиблих і 5 поранених, "
                "48 зниклих безвісти. Комишуваха", source_id=124)
    assert not material_monitoring_update_237(new, equal)
    date_only = row(new["raw_text"].replace("3, 4 та 5 листопада", "3 листопада"))
    assert material_monitoring_update_237(new, date_only) == "MONITORING_MOURNING_DATES_UPDATED_237"


def test_transport_1_vs_3_november_and_changed_routes():
    old = row("1 листопада у Запоріжжі змінять рух громадського транспорту через "
              "греблю ДніпроГЕС. Автобуси № 17, 18 і 72 їздитимуть через Хортицю.")
    new = row("3 листопада у Запоріжжі громадський транспорт працюватиме по-новому через "
              "закриття ДніпроГЕС. Тролейбуси № 1 та № 11 не курсуватимуть, "
              "тролейбус № 14 має іншу ділянку.")
    assert material_monitoring_update_237(new, old) == "MONITORING_NEW_TRANSPORT_SERVICE_DATE_237"
    assert not event_fingerprint_same_event(new, old, monitoring_profile=True)[0]
    # Same date, different route lists is also relevant new service information.
    changed = row(old["raw_text"].replace("1 листопада", "3 листопада"))
    assert material_monitoring_update_237(new, changed) == "MONITORING_DISTINCT_TRANSPORT_ROUTES_237"


def test_social_promo_footer_not_civic_event_identity():
    footer = ("Ми в 📲 https://whatsapp.com/channel/0029VaDz615LNSaBvcjwTB1p WhatsApp "
              "📲 https://www.instagram.com/zaporizhia_info/ Instagram "
              "📲 https://www.tiktok.com/@zaporizhia_info TikTok "
              "📲 https://www.threads.com/@zaporizhia_info Threads")
    a = row("Наслідки вчорашнього удару по Запоріжжю, дані від Суспільного. " + footer)
    b = row("Коментар про подію на Борщагівці без встановлених фактів і "
            "непідтверджені версії. " + footer)
    clean = clean_event_boilerplate_237(a["raw_text"])
    assert "whatsapp" not in clean.casefold()
    assert "tiktok" not in clean.casefold()
    same, _ = event_fingerprint_same_event(a,b,monitoring_profile=True)
    assert not same
    assert not _validated_cluster_same_event(_fingerprint_stats(a,b))[0]


def test_preserve_real_same_event_multiathlete_sports_digest():
    a=row("Запорізькі спортсмени здобули медалі. Тхеквондо у Катарі — Максим Маненков. "
          "Шашки в Нідерландах — Богдан Панченков. Веслування в Аргентині — Людмила Бабак.")
    b=row("Медалі міжнародних змагань: Максим Маненков у Катарі з тхеквондо, "
          "Богдан Панченков у Нідерландах із шашок, Людмила Бабак в Аргентині "
          "із веслування — всі призери.")
    # The sports guard itself requires published source timestamps; that is
    # tested in test_236_local_release, not silently bypassed here.
    assert not material_monitoring_update_237(a,b)


def test_bounded_copyedit_repairs_both_real_live_posts():
    ai = ("Дослідники проектують механізми: ці результати співпадають із тестами. "
          "Це ускладнює «песочникові» тести (sandbagging) і приховування справді здібностей.")
    light = ("Студія випустила лампу, тепер не треба таскати її всю. "
             "Кнопка знаходиться на верхушки корпусу, автономність цієїєї лампи "
             "сягає дванадцяти годин.")
    for before in (ai,light):
        assert copyedit_issues_237(before)
        after = safe_copyedit_237(before)
        assert not copyedit_issues_237(after)
        assert safe_copyedit_237(after) == after
    assert "тести зі штучним заниженням" in safe_copyedit_237(ai)
    assert "проєктують" in safe_copyedit_237(ai)
    assert "верхівки" in safe_copyedit_237(light)
    assert "цієї лампи" in safe_copyedit_237(light)


def test_long_paragraph_wrapped_only_at_sentence_boundaries_and_facts_preserved():
    raw = " ".join(("Ініціатива відбулася 3 листопада і отримала 5 заявок. "
                    "Окрема програма дає учасникам 200 гривень і безкоштовний проїзд. "
                    "Організатори відкрили реєстрацію для громади.") for _ in range(4))
    repaired = safe_copyedit_237(raw, paragraph_limit=270)
    assert "\n\n" in repaired
    assert repaired.replace("\n\n", " ") == raw
    assert repaired.count("200 гривень") == 4
    assert repaired.count("3 листопада") == 4
    broken = "Неповна розповідь без жодної крапки " * 20
    assert safe_copyedit_237(broken, paragraph_limit=200) == broken


def test_live_writer_preparation_keeps_src_links_and_formatting():
    channel = SimpleNamespace(mode=ChannelMode.EDITORIAL)
    article = {"title": "Нова лампа", "raw_text": "Нова лампа з верхівкою.", "source_name": "Publisher"}
    text = "Нова лампа має верхушки корпусу. Також не треба таскати її разом із підставкою."
    prepared = _rc111_prepare_candidate(channel,article,text,hard_max_chars=850,min_chars=100)
    assert "верхівки" in prepared
    assert "носити" in prepared
    assert "верхушки" not in prepared
