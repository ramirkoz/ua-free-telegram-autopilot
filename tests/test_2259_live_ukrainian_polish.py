"""v2.2.59: verified operator Ukrainian errors without factual mutation."""
import inspect

from telegram_autopilot.ukrainian_quality import apply_safe_ukrainian_fixes
from telegram_autopilot.v2.editorial import EditorialEngine, validate_writer_output
from telegram_autopilot.v2.editorial_polish_259 import UA_EDITORIAL_POLISH_RULE_259
from telegram_autopilot.v2.source_final_fidelity_255 import source_final_fidelity_issues


def test_live_86826_orthography_and_agreement_keep_real_names_numbers():
    real = (
        "Дві вежі штаб-квартири Sany Irootech у Гуанчжоу. "
        "Їх спроектували компанія Skidmore, Owings & Merrill "
        "разом із Пекінським інститутом архітектурного проектування. "
        "Висота будівель – 204 і 186 метрів."
    )
    got = apply_safe_ukrainian_fixes(real)
    assert "Їх спроєктувала компанія" in got
    assert "архітектурного проєктування" in got
    assert "Skidmore, Owings & Merrill" in got
    assert "204 і 186 метрів" in got
    assert "спроектували" not in got


def test_live_86839_sentence_capitalization_and_modal_fact_preserved():
    real = (
        "Бригада екстреної допомоги двічі повертала її до життя. "
        "причиною критичного стану могли стати порушення електролітного балансу."
    )
    got = apply_safe_ukrainian_fixes(real)
    assert ". Причиною критичного стану могли стати" in got
    assert "могли" in got
    assert "порушення електролітного балансу" in got


def test_live_86807_job_is_ukrainian_not_russianism():
    real = "Шукають повара в шкільну їдальню з графіком 4/4 та зарплатою 13 000 грн."
    got = apply_safe_ukrainian_fixes(real)
    assert "Шукають кухаря до шкільної їдальні" in got
    assert "4/4" in got and "13 000 грн" in got


def test_user_originals_unchanged_when_no_sure_local_fix():
    original = "За попередніми даними, рятувальники могли евакуювати трьох людей."
    assert apply_safe_ukrainian_fixes(original) == original
    brand = "Компанія Projector створила нову систему."
    assert apply_safe_ukrainian_fixes(brand) == brand


def test_old_video_86652_was_pre_255_guard_and_current_guard_blocks_it():
    source = (
        "Отакий ранок у Запоріжжі. Це не сьогоднішній. "
        "Відео в мережі підписують, як учорашнє."
    )
    bad = "У Запоріжжі вранці пролунали вибухи. Відео не сьогоднішнє."
    issues = source_final_fidelity_issues({"raw_text": source, "title": "Old clip"}, bad)
    assert "FACT_ARCHIVE_VIDEO_NEW_EVENT_255" in issues


def test_existing_writer_final_pipeline_keeps_source_guard_no_new_ai_requests():
    writer = inspect.getsource(EditorialEngine.write)
    editor = inspect.getsource(EditorialEngine._final_edit)
    quality = inspect.getsource(validate_writer_output)
    assert "{UA_EDITORIAL_POLISH_RULE_259}" in writer
    assert "{UA_EDITORIAL_POLISH_RULE_259}" in editor
    assert "{SOURCE_FINAL_FIDELITY_RULE_255}" in writer
    assert "{SOURCE_FINAL_FIDELITY_RULE_255}" in editor
    assert "source_fact_issues(article, value)" in quality
    assert "могли" in UA_EDITORIAL_POLISH_RULE_259
    assert "ТОГО САМОГО SOURCE" in UA_EDITORIAL_POLISH_RULE_259
