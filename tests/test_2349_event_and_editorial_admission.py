"""2.3.49 editorial safety regressions from the 23 Nov live audit.

Real article IDs are test context, never production keyword rules.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram_autopilot.v2.monitoring_event_identity_2349 import rescue_same_event_2349
from telegram_autopilot.v2.editorial_admission_2349 import (
    commercial_catalog_reason_2349,
    expired_service_reason_2349,
    regional_no_result_reason_2349,
)
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event


def _row(title, body, published="2026-11-22T18:30:00+02:00", **extra):
    return {
        "title": title, "raw_text": body,
        "source_published_at": published, "source_id": 1,
        **extra,
    }


def _rescues():
    # 110485/110490/110793: same rescue, rewritten and forwarded by 3 sources.
    official = _row(
        "У Хортицькому районі врятували жінку",
        "Жінка травмувала ногу на скелястому березі Дніпра. "
        "Рятувальники ДСНС разом із міською службою вивезли її човном.",
        "2026-11-22T18:00:00+02:00", source_id=11,
    )
    repost = _row(
        "Травмовану жінку евакуювали човном",
        "На скелях у Хортицькому районі постраждала жінка: "
        "після травми ноги вибратися зі скелястого берега Дніпра не могла. "
        "Рятувальники дісталися до неї човном.",
        "2026-11-22T18:05:00+02:00", source_id=12,
    )
    morning = _row(
        "Порятунок на березі: човен допоміг травмованій",
        "У Хортицькому районі жінка отримала травму ноги на скелях "
        "біля берега Дніпра. Через складний рельєф рятувальники "
        "використали човен для евакуації.",
        "2026-11-23T07:41:29+02:00", source_id=13,
    )
    return official, repost, morning


def test_third_cross_source_rescue_is_duplicate_after_overnight_repost():
    first, second, third = _rescues()
    assert rescue_same_event_2349(second, first)[0]
    assert rescue_same_event_2349(third, first)[0]
    assert event_fingerprint_same_event(
        third, first, monitoring_profile=True
    )[0]


def test_different_district_same_rescue_facts_must_not_merge():
    first, _, third = _rescues()
    third["raw_text"] = third["raw_text"].replace(
        "Хортицькому", "Шевченківському"
    )
    assert not rescue_same_event_2349(third, first)[0]


def test_different_victim_or_rescue_method_must_not_merge():
    first, _, third = _rescues()
    third["raw_text"] = third["raw_text"].replace("жінка", "чоловік")
    assert not rescue_same_event_2349(third, first)[0]
    _, _, third = _rescues()
    third["raw_text"] = third["raw_text"].replace("човен", "гелікоптер")
    third["title"] = third["title"].replace("човен", "гелікоптер")
    assert not rescue_same_event_2349(third, first)[0]


def test_confirmed_new_fatality_is_an_update_not_duplicate():
    first, _, third = _rescues()
    third["raw_text"] += " Пізніше постраждала померла у лікарні."
    assert not rescue_same_event_2349(third, first)[0]


def test_same_topic_on_different_day_without_specific_place_not_a_duplicate():
    first, _, third = _rescues()
    third["raw_text"] = third["raw_text"].replace(
        "Хортицькому районі", "іншому районі"
    ).replace("Дніпра", "річки")
    assert not rescue_same_event_2349(third, first)[0]
    _, _, third = _rescues()
    third["source_published_at"] = "2026-11-27T07:41:29+02:00"
    assert not rescue_same_event_2349(third, first)[0]


def test_schedule_extended_to_2030_cannot_publish_as_current_at_2116():
    source = _row(
        "Графік електропостачання 22 листопада",
        "У Запоріжжі обмеження електропостачання продовжили до 20:30.",
        "2026-11-22T18:50:00+02:00",
    )
    assert expired_service_reason_2349(
        source, now=datetime(2026, 11, 22, 21, 16, tzinfo=ZoneInfo("Europe/Kyiv"))
    ) == "MONITORING_SERVICE_EXPIRED_AT_PUBLISH_2349"
    assert not expired_service_reason_2349(
        source, now=datetime(2026, 11, 22, 20, 15, tzinfo=ZoneInfo("Europe/Kyiv"))
    )


def test_future_or_multi_day_service_not_falsely_expired():
    future = _row(
        "Графік електропостачання 24 листопада",
        "Обмеження подовжили до 20:30.",
        "2026-11-23T08:00:00+02:00",
    )
    mixed = _row(
        "Оновлені графіки",
        "22 листопада до 20:30, 24 листопада до 20:30. "
        "Обмеження діятимуть за графіком.",
    )
    instant = datetime(2026, 11, 23, 21, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert not expired_service_reason_2349(future, now=instant)
    assert not expired_service_reason_2349(mixed, now=instant)


def test_undated_service_or_plain_retrospective_is_not_guessed():
    undated = _row(
        "Автобусні маршрути",
        "Перевізник повідомив про зміни маршруту, без часу завершення.",
    )
    assert not expired_service_reason_2349(undated)
    retrospective = _row(
        "Підсумки графіків відключень 22 листопада",
        "Обмеження тривали до 20:30.",
    )
    assert not expired_service_reason_2349(
        retrospective, now=datetime(2026, 11, 23, 8, tzinfo=ZoneInfo("Europe/Kyiv"))
    )


def test_routine_inspection_with_no_outcome_is_not_news():
    source = _row(
        "Посадовці перевірили енергооб'єкти та лікарні",
        "Щотижня працівники оглянули заклади, провели моніторинг "
        "і обговорили безперебійність їхньої роботи.",
    )
    assert regional_no_result_reason_2349(source) == (
        "MONITORING_ROUTINE_INSPECTION_NO_OUTCOME_2349"
    )
    source["raw_text"] += " За підсумками перевірки виявили порушення."
    assert not regional_no_result_reason_2349(source)


def test_short_unverified_fireworks_signal_is_not_a_confirmed_result():
    rumor = _row(
        "Феєрверки у мікрорайоні",
        "Очевидці повідомляють про феєрверки. Деталі з'ясовують."
    )
    assert regional_no_result_reason_2349(rumor) == (
        "MONITORING_UNVERIFIED_SHORT_SIGNAL_2349"
    )
    rumor["raw_text"] += " Поліція встановила організатора."
    assert not regional_no_result_reason_2349(rumor)


def test_creative_best_n_catalog_is_rejected_but_original_object_survives():
    catalog = _row(
        "5 Best Cabin Accessories That Add Comfort",
        "Five ordinary accessories for interiors and cabins.",
    )
    assert commercial_catalog_reason_2349(catalog) == (
        "CREATIVE_ROUTINE_BEST_N_CATALOG_2349"
    )
    original = _row(
        "Unusual phone combines thermal imaging with a projector",
        "A specific and original device mechanism.",
    )
    assert not commercial_catalog_reason_2349(original)
    cultural_list = _row(
        "Five artists reinterpret LEGO in public art",
        "A surprising group exhibition with an original result.",
    )
    assert not commercial_catalog_reason_2349(cultural_list)
