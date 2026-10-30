"""2.2.55 factual fidelity regression from real 29-30 October 2.2.54 operator posts."""
import inspect
import pytest

from telegram_autopilot.v2.source_final_fidelity_255 import (
    SOURCE_FINAL_FIDELITY_RULE_255,
    source_final_fidelity_issues,
)
from telegram_autopilot.v2.source_fact_integrity import (
    source_fact_issues,
    non_overridable_quality_issues,
)
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import EditorialEngine, validate_writer_output, prepublish_quality_issues


def story(raw, title="News", source_url="https://t.me/source/42"):
    return {"raw_text": raw, "title": title, "source_url": source_url}


def codes(raw, final):
    return source_final_fidelity_issues(story(raw), final)


def test_real_86318_residence_and_train_are_not_event_location():
    src = (
        "Троє загиблих та семеро поранених, серед них — 11-річна дитина. "
        "Йдеться про мешканців Запоріжжя, які чекали на потяг Дніпро-Запоріжжя "
        "та потрапили під терористичний удар росіян."
    )
    bad = "У Запоріжжі троє людей загинули та семеро поранені внаслідок російського удару."
    assert "FACT_EVENT_LOCATION_VS_RESIDENCE_255" in codes(src, bad)
    assert "FACT_EVENT_LOCATION_VS_RESIDENCE_255" in source_fact_issues(story(src), bad)
    good = (
        "Троє мешканців Запоріжжя загинули під час російського удару. "
        "Вони чекали на потяг Дніпро — Запоріжжя."
    )
    assert codes(src, good) == "" or codes(src, good) == ()


def test_same_city_with_explicit_incident_source_is_allowed():
    src = (
        "У Запоріжжі внаслідок російського удару загинули троє мешканців Запоріжжя, "
        "які чекали на потяг Дніпро-Запоріжжя."
    )
    assert codes(src, "У Запоріжжі троє людей загинули внаслідок російського удару.") == ()


def test_incident_in_dnipro_is_not_blocked_if_identified_correctly():
    src = (
        "У Дніпрі внаслідок удару загинули троє мешканців Запоріжжя, "
        "які чекали на потяг Дніпро-Запоріжжя."
    )
    assert codes(src, "У Дніпрі загинули троє мешканців Запоріжжя.") == ()


def test_real_86652_old_video_cannot_create_new_morning_explosions():
    src = (
        "Отакий ранок у Запоріжжі. Це не сьогоднішній. "
        "Відео в мережі підписують, як учорашнє. Надіслати новину."
    )
    bad = (
        "У Запоріжжі вранці пролунали вибухи.\n"
        "Відео, яке зараз поширюють, насправді не сьогоднішнє."
    )
    assert "FACT_ARCHIVE_VIDEO_NEW_EVENT_255" in codes(src, bad)
    safe = "У мережі поширюють відео із Запоріжжя, яке не є сьогоднішнім."
    assert codes(src, safe) == ()


def test_old_video_describing_old_explosion_is_not_new_incident():
    src = (
        "На відео видно вибух, ролик не сьогоднішній. "
        "Це архівні кадри."
    )
    final = "На архівному відео видно вибух. Це старий запис."
    assert codes(src, final) == ()


def test_real_86359_42_percent_increase_not_to_42_percent():
    src = (
        "The US power sector could release 42 percent more planet-heating "
        "carbon dioxide pollution by 2030 than it did in 2025."
    )
    bad = "У США викиди вуглекислого газу можуть зрости до 42 % до 2030 року."
    assert "FACT_PERCENT_BY_TO_INVERSION_255" in codes(src, bad)
    assert codes(src, "Викиди CO2 в електроенергетиці можуть бути на 42% вищими.") == ()


def test_percent_to_valid_when_source_explicitly_supports_target_level():
    src = "The share could increase to 42 percent by the end of the year."
    assert codes(src, "Частка може зрости до 42% до кінця року.") == ()
    src2 = "Pollution increased 42 percent more last year, reaching 42 percent of overall emissions."
    assert codes(src2, "Частка викидів зросла до 42%.") == ()


def test_percentage_different_metric_not_reinterpreted():
    src = "Emissions are 42 percent more, and the share of renewables is 63 percent."
    assert codes(src, "Частка відновлюваних джерел зросла до 63%.") == ()


def test_real_86673_small_rocket_count_not_most_intensive_against_drones():
    src = (
        "За добу ворог завдав 792 удари. Запоріжжя, Магдалинівку, "
        "Таврійське та Оріхів росіяни п’ять разів обстріляли з РСЗВ. "
        "БпЛА ворог 624 рази атакував Запоріжжя та інші населені пункти."
    )
    bad = "Найінтенсивніше били з РСЗВ — п’ять разів. Крім того, 624 рази застосували БпЛА."
    assert "FACT_UNSUPPORTED_CATEGORY_SUPERLATIVE_255" in codes(src, bad)
    safe = "За добу було п’ять ударів із РСЗВ та 624 атаки БпЛА."
    assert codes(src, safe) == ()


def test_ranking_guard_requires_source_comparable_categories():
    src = "Росіяни п’ять разів обстріляли з РСЗВ, інших даних не опублікували."
    assert codes(src, "Найінтенсивніше били з РСЗВ.") == ()
    src2 = "З РСЗВ обстріляли двічі, ще один удар завдали з дрона."
    assert codes(src2, "Найінтенсивніше били з РСЗВ.") == ()


def test_source_asserted_category_ranking_must_not_be_silently_overridden():
    src = (
        "Найінтенсивніше били з РСЗВ: п’ять разів. "
        "БпЛА ворог 624 рази атакував інші об'єкти."
    )
    # Explicit source statement, whether the comparison is sensible or not:
    # this is a source-accuracy tool, not fact-checking external evidence.
    assert codes(src, "Найінтенсивніше били з РСЗВ.") == ()


@pytest.mark.parametrize("mode", [ChannelMode.MONITORING, ChannelMode.EDITORIAL])
def test_cannot_bypass_factual_guards_in_force_publish(mode):
    a = story(
        "The US power sector could release 42 percent more carbon dioxide pollution.",
        "US emissions could increase.",
    )
    channel = ChannelConfig(
        id=3 if mode == ChannelMode.MONITORING else 1,
        name="test", telegram_chat_id="@test", mode=mode,
        policy=ChannelPolicy(channel_id=3 if mode == ChannelMode.MONITORING else 1)
    )
    bad = "Викиди вуглекислого газу в США можуть зрости до 42% у новому прогнозі."
    assert "FACT_PERCENT_BY_TO_INVERSION_255" in non_overridable_quality_issues(channel, a, bad)
    assert any("FACT_PERCENT_BY_TO_INVERSION_255" in issue
               for issue in prepublish_quality_issues(channel, a, bad))


def test_writer_final_and_prepublish_use_same_source_first_guard():
    writer = inspect.getsource(EditorialEngine.write)
    editor = inspect.getsource(EditorialEngine._final_edit)
    quality = inspect.getsource(validate_writer_output)
    prepublish = inspect.getsource(prepublish_quality_issues)
    assert "{SOURCE_FINAL_FIDELITY_RULE_255}" in writer
    assert "{SOURCE_FINAL_FIDELITY_RULE_255}" in editor
    assert "source_fact_issues(article, value)" in quality
    assert "source_fact_issues(article, value)" in prepublish
    assert "SOURCE → DRAFT → FINAL" in SOURCE_FINAL_FIDELITY_RULE_255
