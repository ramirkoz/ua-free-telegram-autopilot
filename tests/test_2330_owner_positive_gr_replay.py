"""v2.3.30 full 1472 owner-label replay: high-value GR source false positives.

These are small paraphrase-free source snippets from verified operator rows.
Original complete rows and operator database remain private and read-only.
"""
from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322
from telegram_autopilot.v2.monitoring_call_to_action import call_to_action_reason


def test_2330_aid_document_replacement_is_not_a_lost_found_ad():
    article = {
        "title": "«Елеос-Україна» допомагає жителям та ВПО Запорізької області",
        "raw_text": (
            "Безоплатно евакуюватися із прифронтових громад. "
            "Відновити втрачений або замінити пошкоджений паспорт. "
            "Надаємо юридичний супровід, витрати на відновлення документа "
            "організація оплачує безпосередньо на реквізити ДМС."
        ),
    }
    assert no_announcement_reason_2322(article) == ""


def test_2330_actual_found_document_classified_is_still_rejected():
    article = {
        "title": "Знайдено паспорт",
        "raw_text": (
            "Знайдено загублений паспорт. Поверніть документ власнику, "
            "телефонуйте для повернення."
        ),
    }
    assert no_announcement_reason_2322(article).startswith("MONITORING_CLASSIFIED_LOST_FOUND")


def test_2330_regional_weekly_weather_forecast_is_not_future_event():
    article = {
        "title": "У Запоріжжі цього тижня прогнозують дощі та потепління",
        "raw_text": (
            "З 10 по 14 листопада на містян чекає хмарна погода з опадами й туманами. "
            "Температура підніметься до +16°C, а потім знизиться."
        ),
    }
    assert call_to_action_reason(article) == ""
    assert no_announcement_reason_2322(article) == ""


def test_2330_true_future_event_cta_stays_rejected_despite_weather():
    article = {
        "title": "Синоптики прогнозують дощі на фестивалі",
        "raw_text": (
            "У суботу відбудеться фестиваль. Запрошуємо всіх на концерт, "
            "квитки продаються онлайн. Очікуються короткі дощі."
        ),
    }
    assert call_to_action_reason(article) == "MONITORING_FUTURE_EVENT_INVITATION"


def test_2330_registration_closed_is_service_update_not_new_application():
    article = {
        "title": "Форму реєстрації на подарунки закрито",
        "raw_text": (
            "Форму реєстрації на отримання подарунків від 05.11.2026 року "
            "закрито, реєстрацію припинено."
        ),
    }
    assert call_to_action_reason(article) == ""
    assert no_announcement_reason_2322(article) == ""


def test_2330_open_gift_registration_stays_a_call_to_action():
    article = {
        "title": "Реєстрація на подарунки для дітей",
        "raw_text": (
            "Відкрита реєстрація на подарунки. "
            "Заповніть онлайн-форму, подайте заявку до 27 листопада."
        ),
    }
    # Survey-form and application hard vetoes are both valid no-announcement
    # outcomes; the invariant is rejection, not the first matching reason.
    assert call_to_action_reason(article) in {
        "MONITORING_APPLICATION_CALL", "MONITORING_SURVEY_INVITATION"
    }
