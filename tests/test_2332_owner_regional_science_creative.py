"""Regression: the owner-confirmed 15 Nov 142-post LIVE audit, without operator Data.

Fixtures mirror the *type* and original text signals. Detailed, private
operator SQLite stays READ ONLY / out of the repository. No network or Telegram.
"""
from __future__ import annotations

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, EditorialRuntimeProfile, DedupeProfile
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial import hard_editorial_reject
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.editorial_owner_2332 import (
    monitoring_source_reason_2332, editorial_source_reason_2332, final_artifact_reason_2332
)

SCIENCE = ChannelConfig(id=1, name="science", telegram_chat_id="-1001", mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD, dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True, dedupe_compound_events=True,
    policy=ChannelPolicy(channel_id=1, selection_rules=MARKER+" наука"))
CREATIVE = ChannelConfig(id=2, name="creative", telegram_chat_id="-1002", mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    policy=ChannelPolicy(channel_id=2, selection_rules=MARKER+" дизайн"))
REGION = ChannelConfig(id=3, name="regional", telegram_chat_id="-1003", mode=ChannelMode.MONITORING,
    policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]"))


@pytest.mark.parametrize("title,raw,expected", [
    ("Реактив між районами. Мопед на Запоріжжя.", "Реактив між районами. ✉️ Надіслати новину. Мопед на Запоріжжя.", "MONITORING_ACTIVE_AERIAL_ROUTE_2332"),
    ("Мопед на Запоріжжя.", "Реактив між районами. Мопед на Запоріжжя. ✉️ https://t.me/example_bot Надіслати новину", "MONITORING_ACTIVE_AERIAL_ROUTE_2332"),
    ("Звертаємося із проханням підтримати збір", "ЗБІР НА ECOFLOW. Прошу долучитися сумою. Мета збору: 57 000 грн.", "MONITORING_FUNDRAISING_APPEAL_2332"),
    ("16 листопада відбудеться прощання з мешканкою", "16 листопада відбудеться прощання у залі. Висловлюємо співчуття.", "MONITORING_FUTURE_FUNERAL_NOTICE_2332"),
    ("УВАГА! ПРЯМА ЛІНІЯ", "У понеділок відбудеться пряма гаряча телефонна лінія для мешканців.", "MONITORING_HOTLINE_INVITATION_2332"),
    ("Шановні працівники! Щиро вітаю вас із Днем працівників сільського господарства", "Прийміть щирі побажання!", "MONITORING_RITUAL_GREETING_2332"),
    ("ХЛІБ, ЗДОБУТИЙ КРІЗЬ ВОГОНЬ", "У День працівників сільського господарства низький уклін усім аграріям.", "MONITORING_RITUAL_GREETING_2332"),
    ("Всесвітній день боротьби з діабетом: що треба знати про хворобу", "За даними огляду, хвороба поширена у країні. Нових місцевих рішень немає.", "MONITORING_GENERIC_ADVICE_NOT_NEWS_2332"),
    ("Для дорослих, які хочуть кинути курити", "Використовуйте інтернет-сервіс. Звертайтеся за порадою.", "MONITORING_GENERIC_ADVICE_NOT_NEWS_2332"),
    ("Немає диму — не означає, що немає шкоди", "Загальні поради про вейпи. Немає нової події.", "MONITORING_GENERIC_ADVICE_NOT_NEWS_2332"),
    ("Місце для кожного: як організувати простір?", "Поради зі стільцями і проходами.", "MONITORING_GENERIC_ADVICE_NOT_NEWS_2332"),
    ("Норвегія заборонила в’їзд спортсменам з рф", "Норвегія не допускатиме спортсменів на змагання на своїй території.", "MONITORING_NONLOCAL_SUBJECT_2332"),
    ("Понад 80% українських медиків використовують ШІ, — МОЗ", "Це загальноукраїнська статистика за даними міністерства.", "MONITORING_NONLOCAL_SUBJECT_2332"),
    ("Іспанія продовжує підтримувати Україну: відвідала родини", "Міністерка оборони Іспанії відвідала родини військових в Іспанії.", "MONITORING_NONLOCAL_SUBJECT_2332"),
    ("Удар по Павлограду на Дніпропетровщині", "Повідомили про поранених у Павлограді, Дніпропетровська область.", "MONITORING_NONLOCAL_SUBJECT_2332"),
    ("ДТП на Україні за участі мотоцикліста", "На місці працює швидка. Вкажіть місце через наш чат-бот.", "MONITORING_ACCIDENT_LOCATION_AMBIGUOUS_2332"),
    ("Вчора аналогічно вчинили з будинками", "Люди, які займаються чергами та плануванням, ну як так?", "MONITORING_UNVERIFIED_READER_RANT_2332"),
])
def test_region_source_veto_both_selection_and_ready_boundary(title,raw,expected):
    row={"title":title,"raw_text":raw,"final_text":""}
    assert monitoring_source_reason_2332(row)==expected
    assert hard_editorial_reject(REGION,row,"Підготовлений старою версією текст.")==expected


@pytest.mark.parametrize("title,raw,expected", [
    ("Build a Robot Pick-and-Place Simulation with SimReady Assets", "This walkthrough shows how to compose a scene and run a simulation.", "SCIENCE_SIMULATOR_TUTORIAL_NOT_NEWS_2332"),
    ("This Week In Space podcast: Episode 236 — Alienspotting", "The hosts discuss theories and revisit assumptions.", "SCIENCE_PODCAST_EPISODE_PROMO_2332"),
    ("Here's when a dedicated graphics card is worth it", "Buy a discrete GPU if you game or use graphic editors.", "SCIENCE_GPU_BUYER_TIPS_2332"),
    ("The Hands-Down Best Fried Fish Joint In Every State", "A ranking of places to buy fried food across all fifty states.", "CREATIVE_GENERIC_RESTAURANT_RANKING_2332"),
    ("Walmart's Great Value Vs Ocean Spray: Who Makes The Better Cranberry Sauce", "Grocery products review of cranberry sauce.", "CREATIVE_ROUTINE_GROCERY_COMPARISON_2332"),
    ("Costco Vs Trader Joe's: Which Shredded Rotisserie Chicken Is Best?", "Reviews of shredded rotisserie chicken grocery products.", "CREATIVE_ROUTINE_GROCERY_COMPARISON_2332"),
    ("What Do All The Flags Mean In Racing?", "An explanation of regulations and flags.", "CREATIVE_REFERENCE_TUTORIAL_2332"),
    ("ASICS Dresses the GEL-CUMULUS 16 in Three Earthy, Warm-Toned Colorways", "A product in three new colorways with the exact same old midsole.", "CREATIVE_COLORWAY_ONLY_2332"),
    ("Pebblebee Holiday Toast Trackers Bring Cranberry and Champagne to Your Keychain", "Existing trackers with new seasonal colors.", "CREATIVE_COLORWAY_ONLY_2332"),
    ("Next-Gen Audi RS6 Avant Coming To US", "The export to the United States may occur.", "CREATIVE_ROUTINE_EXPORT_RUMOR_2332"),
])
def test_science_creative_veto_at_source_and_ready(title,raw,expected):
    role = "science" if expected.startswith("SCIENCE") else "creative"
    channel= SCIENCE if role=="science" else CREATIVE
    row={"title":title,"raw_text":raw}
    assert editorial_source_reason_2332(role,row)==expected
    assert editorial_source_topic_reason_2319(channel,row)==expected
    assert hard_editorial_reject(channel,row,"Раніше підготовлений READY текст")==expected


@pytest.mark.parametrize("text", [
    "Мета збору 57 000 грн. Долучитися за посиланням: або перерахувати кошти.",
    "Для дорослих працює сервіс. На сайті можна отримати професійну допомогу:\nДорослий приклад.",
    "Контакти розміщено за посиланням:\n",
])
def test_final_text_broken_links_blocked(text):
    assert final_artifact_reason_2332({"title":"Допомога у регіоні","raw_text":"Почали роботу."},text)=="FINAL_BROKEN_OR_MISSING_LINK_2332"
    assert hard_editorial_reject(SCIENCE,{"title":"New lab discovery","raw_text":"New result verified"},text)=="FINAL_BROKEN_OR_MISSING_LINK_2332"


@pytest.mark.parametrize("text", [
    "Подробиці за посиланням: https://example.org/official",
    "На сайті можна отримати професійну допомогу: https://example.org/support",
    "Нова транспортна схема. Графік відключень доступний на офіційному сайті.",
])
def test_final_text_with_real_url_and_no_dangling_cta_preserved(text):
    assert final_artifact_reason_2332({"title":"Нова послуга","raw_text":"Служба оновила послугу."},text)==""


@pytest.mark.parametrize("title,raw", [
    ("FPV-дрон влучив у багатоповерхівку в Запоріжжі", "Влучив у будинок у Космічному районі Запоріжжя. Сталася пожежа."),
    ("Кількість постраждалих у Запоріжжі зросла до 50 людей", "Попередньо 30, пізніше 50 людей поранено, з них вісім дітей."),
    ("У Запоріжжі оновили графік відключень для черг", "У графіках зміни: для черги 2.1 відключення з 15:30 до 18:00."),
    ("Запорізька служба змінила маршрут транспорту", "Сьогодні у Запоріжжі тролейбус №14 об'їздить закриту греблю."),
    ("В Запоріжжі відкрили виставку", "Митці відкрили нову виставку. Створили 22 авторські картини."),
    ("Запорізька громада виплатила допомогу сім'ям", "У громаді надано виплати та підтримку постраждалим."),
])
def test_real_regional_events_not_blocked_by_new_2332_guard(title,raw):
    assert monitoring_source_reason_2332({"title":title,"raw_text":raw})==""


@pytest.mark.parametrize("role,title,raw", [
    ("science","Runway open-sources Praxis-1 robot controller", "Company released a new trained control model with open weights and measurements."),
    ("science","SpaceX completes first Starship chopstick catch", "The company caught the upper-stage vehicle for the first time using tower arms."),
    ("science","Researchers discover the cause of a rare brain signal", "New lab result has been measured and independently verified."),
    ("science","Neuroscience behind stuttering: new clinical consensus", "Researchers and a panel of doctors published the first practice consensus guidelines."),
    ("creative","Artist Shin Noguchi produces original street photography", "A named photographer created an original authored set of photographs."),
    ("creative","The five original cabin design objects of November", "Five architects made their own objects and presented new architectural materials."),
    ("creative","Michael Mapes builds new framed artworks", "An original installation by an artist transformed found portraits."),
    ("creative","New Star Wars 3D printed chair with shelving", "A designer created an original design with a built-in shelf."),
    ("creative","On and Erewhon unveil original campaign", "A brand created an original advertising collaboration."),
])
def test_positive_science_and_original_creative_material_remains(role,title,raw):
    assert editorial_source_reason_2332(role,{"title":title,"raw_text":raw})==""