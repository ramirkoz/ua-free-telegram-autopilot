"""2.3.9 regressions grounded in 2026-11-04 live operator posts."""
from types import SimpleNamespace

from telegram_autopilot.v2.live_editorial_integrity_239 import (
    final_integrity_issues, monitoring_scope_issue,
)


def article(raw_text, title="", source_url="https://t.me/info_zp/42"):
    return SimpleNamespace(raw_text=raw_text, title=title, source_url=source_url)


def test_off_region_social_reaction_rejected_even_local_source_url():
    row = article("😂 АХААХАХА Канал Fox News несе відповідальність за діяльність демократів. Ото його плавить.")
    assert monitoring_scope_issue(row) == "MONITORING_EXTERNAL_POLITICAL_REACTION_239"


def test_national_currency_story_not_local_news():
    row = article("НБУ оприлюднив курс долара на 4 листопада. Валюта коштує 45,66 грн.")
    assert monitoring_scope_issue(row) == "MONITORING_NATIONAL_FINANCE_NO_LOCAL_EVENT_239"


def test_city_specific_other_region_not_hijacked_by_zp_domain():
    row = article("У Києві спростували фейк про мобілізацію. Такої публікації DW не було.", source_url="https://inform.zp.ua/post")
    assert monitoring_scope_issue(row) == "MONITORING_OTHER_REGION_ONLY_239"


def test_valid_regional_event_survives():
    assert monitoring_scope_issue(article("У Запоріжжі після обстрілу пошкоджено автобуси. Частину машин відновили.")) == ""


def test_valid_national_civic_service_survives():
    assert monitoring_scope_issue(article("Міністерство запустило курс лекцій з безбар'єрності для громад. Доступний запис навчання.")) == ""


def test_local_population_claim_without_named_source_blocked():
    row = article("Запоріжжя втратило на третину населення. Це статистика. Ніхто не каже, звідки вона.")
    assert monitoring_scope_issue(row) == "MONITORING_UNSUPPORTED_POPULATION_STATS_239"


def test_arabic_character_inside_ukrainian_word_blocked():
    assert "MIXED_SCRIPT_WORD_239" in final_integrity_issues(
        article("Автобус ремонтують."), "Один автобуس ремонту не підлягає."
    )


def test_unrelated_arabic_word_not_indiscriminately_blocked():
    assert "MIXED_SCRIPT_WORD_239" not in final_integrity_issues(
        article("Вивчають арабську."), "У школі вивчають العربية мову."
    )


def test_link_promise_without_link_blocked():
    assert "ACTION_LINK_PLACEHOLDER_239" in final_integrity_issues(
        article("Інформація про вакансії."), "Деталі вакансій — у посиланні."
    )


def test_source_link_in_text_is_not_blocked():
    assert "ACTION_LINK_PLACEHOLDER_239" not in final_integrity_issues(
        article("Є вакансії."), "Деталі вакансій за посиланням: https://example.org/jobs"
    )


def test_legal_guilt_wording_rejected():
    assert "UNPRESUMED_LEGAL_GUILT_239" in final_integrity_issues(
        article("До суду скеровано обвинувальний акт."), "Шахраї привласнили кошти."
    )


def test_national_energy_disruption_with_city_not_false_rejected():
    row = article("Укренерго повідомило: енергосистема України зазнала ударів. Через атаки у Києві та низці областей ввели відключення.")
    assert monitoring_scope_issue(row) == ""
