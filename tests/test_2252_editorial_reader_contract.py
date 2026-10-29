"""v2.2.52 regression: real 29 Oct operator posts and negative controls."""
import inspect

from telegram_autopilot.v2.editorial_reader_contract_252 import (
    READER_COMPLETENESS_RULE_252,
    final_reader_issue,
    source_completeness_issue,
)
from telegram_autopilot.v2.editorial import EditorialEngine, validate_writer_output


def article(title, raw, source_url="https://t.me/example/123"):
    return {"title": title, "raw_text": raw, "source_url": source_url}


def test_real_renaming_teaser_blocked_before_ai():
    a = article(
        "У Запоріжжі перейменували три вулиці: які нові назви вони отримали",
        "Перейменували три вулиці. Нові назви отримали вулиці МВО-7, "
        "Лейтенанта Шмідта та Військкоматська. "
        "Детальніше: https://example.org/renames",
    )
    assert "SOURCE_DETAIL_MISSING_252" in source_completeness_issue(a)
    assert "SOURCE_DETAIL_MISSING_252" in final_reader_issue(
        a, "У Запоріжжі перейменували три вулиці. Назви отримали МВО-7 та інші."
    )


def test_real_water_teaser_blocked_without_addresses():
    a = article(
        "У Запоріжжі відключили воду за десятками адрес: повний перелік",
        "29 жовтня відключили воду через витік. Повний перелік адрес опубліковано. "
        "Детальніше: https://example.org/water",
    )
    assert "SOURCE_DETAIL_MISSING_252" in source_completeness_issue(a)


def test_verified_renaming_mapping_is_allowed():
    a = article(
        "У Запоріжжі перейменували три вулиці: які нові назви вони отримали",
        "Вулиця МВО-7 стала вулицею Ґрунтовою. "
        "Про рішення повідомили на сесії ради. "
        "Детальніше: https://example.org/renames",
    )
    assert source_completeness_issue(a) == ""


def test_verified_water_address_is_allowed():
    a = article(
        "У Запоріжжі відключили воду за десятками адрес: повний перелік",
        "Воду відключили на вулиці Сонячній, 5. "
        "Тривають ремонтні роботи. Детальніше: https://example.org/water",
    )
    assert source_completeness_issue(a) == ""


def test_direct_short_attack_report_stays_eligible():
    a = article(
        "Ворог поцілив FPV-дроном у маршрутку в центрі Запоріжжя",
        "Постраждала одна людина. Медики надають допомогу.",
    )
    assert source_completeness_issue(a) == ""
    assert final_reader_issue(a, "У Запоріжжі атакували маршрутку. Поранено людину.") == ""


def test_old_injury_total_is_not_reported_as_current():
    a = article(
        "13 загинули та 5 отримали поранення",
        "Унаслідок атаки 13 загинули, ще 5 отримали поранення. "
        "До 10 зросла кількість поранених через атаку.",
    )
    bad = (
        "Загинули 13 людей, ще 5 отримали поранення. "
        "Пізніше кількість поранених зросла до 10."
    )
    assert "OUTDATED_CASUALTY_COUNT_252" in final_reader_issue(a, bad)
    good = "Загинули 13 людей, кількість поранених зросла до 10."
    assert final_reader_issue(a, good) == ""


def test_explicit_chronology_remains_permitted():
    a = article("Удар", "Спочатку поранено 5. До 10 зросла кількість поранених.")
    text = "Спочатку 5 отримали поранення, згодом кількість поранених зросла до 10."
    assert final_reader_issue(a, text) == ""


def test_new_figure_does_not_contaminate_different_measure():
    a = article("Удар", "До 10 зросла кількість поранених.")
    assert final_reader_issue(a, "Пошкоджено 5 автобусів. Поранено 10 людей.") == ""


def test_apple_reviewers_opinion_not_company_intent():
    a = article(
        "Apple is finally embracing chaos and I’m here for it",
        "I'm calling it: Apple is finally cool. "
        "It seems Apple is embracing a bit of playfulness. "
        "In a new campaign, Apple showed works by young creatives.",
        "https://example.org/story",
    )
    assert "UNATTRIBUTED_BRAND_INTENT_252" in final_reader_issue(
        a, "Apple свідомо впускає в рекламу хаос. Кампанія представляє митців."
    )
    assert final_reader_issue(
        a, "Оглядач вважає, що кампанія відходить від мінімалізму. "
           "Apple представила роботи молодих креативників."
    ) == ""


def test_verified_intent_is_not_blocked():
    a = article(
        "Brand campaign",
        "The company deliberately changed its advertising approach. "
        "Brand confirmed the decision.",
        "https://example.org/brand",
    )
    assert final_reader_issue(a, "Бренд свідомо змінив рекламний підхід.") == ""


def test_editorial_runtime_wired_to_pre_ai_and_pre_telegram():
    select = inspect.getsource(EditorialEngine.select)
    writer = inspect.getsource(validate_writer_output)
    write = inspect.getsource(EditorialEngine.write)
    final = inspect.getsource(EditorialEngine._final_edit)
    assert "source_completeness_issue(article)" in select
    assert "final_reader_issue(article, value)" in writer
    assert "READER_COMPLETENESS_RULE_252" in write
    assert "READER_COMPLETENESS_RULE_252" in final
    assert "SOURCE" in READER_COMPLETENESS_RULE_252
