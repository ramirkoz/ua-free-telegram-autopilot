"""Operator 20 Nov screenshots: two one-topic donor posts became two posts.

Exact source-owned article identities from LIVE telemetry:
107571 -> mih_gromada/4762 -> channel message 5409 at 10:36:18;
107572 -> mih_gromada/4763 -> channel message 5410 at 10:41:31.
No reliance on model-generated text, outgoing Telegram, or operator DB writes.
"""
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.event_dedupe_guard import event_fingerprint_same_event
from telegram_autopilot.v2.monitoring_no_event_2346 import (
    childhood_reflection_without_event_2346,
    same_source_reflective_continuation_2346,
)
from telegram_autopilot.v2.monitoring_civic_quality import civic_relevance_exclusion
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.editorial import hard_editorial_reject


def channel(opt_in=True):
    return ChannelConfig(id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1003",
                         mode=ChannelMode.MONITORING,
                         policy=ChannelPolicy(channel_id=3, rejection_rules="[LIVE_NOW_RC96]" if opt_in else ""))


FIRST = {
    "id": 107571, "channel_id": 3, "source_id": 159,
    "title": "Дитинство має пахнути какао, свіжими зошитами та маминими обіймами, а не пахнути війною.",
    "raw_text": ("Дитинство має пахнути какао, свіжими зошитами та маминими обіймами, "
                 "а не пахнути війною. На жаль, реальність змусила наших дітей знати "
                 "занадто багато дорослих слів: «евакуація», «укриття», «окупація», «втрата»."),
    "source_url": "https://t.me/mih_gromada/4762",
    "source_published_at": "2026-11-20T10:04:30+02:00",
    "published_at": "2026-11-20T10:36:18+02:00",
}
SECOND = {
    "id": 107572, "channel_id": 3, "source_id": 159,
    "title": ("Кожен з нас, дорослих, сьогодні живе з тихим болем від того, "
              "що ми не змогли вберегти їх від цих випробувань."),
    "raw_text": ("Але подивіться на них: вони вчаться, малюють, займаються спортом, "
                 "підтримують одне одного і надихають нас не опускати руки. "
                 "Вони — неймовірні. Вони знають, як звучить сирена, але досі щиро сміються. "
                 "Війна забрала у наших дітей безтурботність, розкидала по різних містах і країнах, "
                 "змусила сумувати за рідними домівками і обіймати батьків лише через екран телефону. "
                 "Їм побажали звичайного дитинства — без вибухів і страху, в рідному домі та під мирним небом."),
    "source_url": "https://t.me/mih_gromada/4763",
    "source_published_at": "2026-11-20T10:05:00+02:00",
    "published_at": "2026-11-20T10:41:31+02:00",
}


def test_both_source_fragments_rejected_before_ai():
    for r in (FIRST, SECOND):
        reason = childhood_reflection_without_event_2346(r)
        assert reason == "MONITORING_CHILDHOOD_REFLECTION_NOT_NEWS_2346"
        assert civic_relevance_exclusion(channel(), r) == reason
        assert live_now_exclusion(channel(), r) == reason
        assert hard_editorial_reject(channel(), r, "Грамотний AI текст із небажаної теми") == reason


def test_near_time_same_donor_childhood_continuation_duplicate():
    prior_ledger = {k:v for k,v in FIRST.items() if k not in ("source_url", "source_published_at")}
    same, reason = same_source_reflective_continuation_2346(SECOND, prior_ledger)
    assert same and "CONTINUATION" in reason
    yes, why = event_fingerprint_same_event(SECOND, prior_ledger, monitoring_profile=True)
    assert yes and "CONTINUATION" in why, why
    assert "CONTINUATION" not in event_fingerprint_same_event(SECOND, prior_ledger, monitoring_profile=False)[1]


def test_different_donor_or_distant_day_does_not_match():
    assert not same_source_reflective_continuation_2346(SECOND, dict(FIRST, source_id=188))[0]
    assert not same_source_reflective_continuation_2346(
        dict(SECOND, source_published_at="2026-11-23T10:05:00+02:00"), FIRST)[0]


def test_old_calendar_childrens_day_greeting_without_civic_action_is_not_news():
    greeting={"title":"20 листопада — Всесвітній день дитини",
              "raw_text":"Діти — наше майбутнє та спільна відповідальність. Бажаємо кожній дитині щастя й мирного неба."}
    assert childhood_reflection_without_event_2346(greeting) == "MONITORING_CALENDAR_GREETING_NO_CIVIC_EVENT_2346"


def test_actual_local_events_and_material_changes_remain_eligible():
    good=[
      "У Михайлівській громаді евакуювали 36 дітей із небезпечного району. Поліція забезпечила транспорт.",
      "У Запоріжжі відкрили простір для дітей. У закладі проводять заняття і надають психологічну допомогу.",
      "До Дня дитини в громаді провели благодійний захід, де передали 200 наборів дітям ВПО.",
      "У Михайлівській громаді надають допомогу дітям: реєстрація триває до 25 листопада.",
      "Для родин із дітьми Запорізька влада затвердила новий графік прийому заявок.",
      "У Михайлівці організували збір коштів на лікування дитини, реквізити опублікували в офіційному повідомленні.",
    ]
    for txt in good:
        r={"title":txt,"raw_text":txt,"source_id":159,
           "source_published_at":"2026-11-20T10:05:00+02:00"}
        assert childhood_reflection_without_event_2346(r) == "",txt
        assert civic_relevance_exclusion(channel(), r) == "", txt
        assert not same_source_reflective_continuation_2346(r,FIRST)[0],txt


def test_real_update_without_new_time_is_not_suppressed():
    new = dict(SECOND, title="Евакуювали 34 дітей з Михайлівської громади", raw_text="Після обстрілу евакуювали 34 дітей та 20 дорослих.")
    assert not event_fingerprint_same_event(new,FIRST,monitoring_profile=True)[0]


def test_unopted_other_channel_does_not_change():
    assert civic_relevance_exclusion(channel(False), FIRST) == ""
    assert not childhood_reflection_without_event_2346({"title":"Cactus creates 4.5 V", "raw_text":"8 cacti powered a sensor."})


def test_consecutive_donor_telegram_posts_confirm_one_nonchanging_report():
    from telegram_autopilot.v2.monitoring_no_event_2346 import same_source_telegram_thread_2346
    first = {
        "source_id":159,"source_url":"https://t.me/mih_gromada/6000",
        "title":"У Михайлівській громаді біля школи встановили модульне укриття",
        "raw_text":"Михайлівська громада: біля ліцею встановили модульне укриття для школярів. "
                   "Нове модульне укриття облаштоване поряд зі школою та дозволяє учням безпечно перебувати під час тривоги.",
        "source_published_at":"2026-11-20T12:03:00+02:00",
    }
    second = {
        "source_id":159,"source_url":"https://t.me/mih_gromada/6001",
        "title":"Модульне укриття біля школи Михайлівської громади",
        "raw_text":"Біля Михайлівської школи вже встановлене нове модульне укриття для школярів. "
                   "Це укриття біля ліцею в Михайлівській громаді, воно облаштоване для безпечного перебування учнів під час тривоги.",
        "source_published_at":"2026-11-20T12:07:00+02:00",
    }
    same, why = same_source_telegram_thread_2346(second, first)
    assert same and "SAME_DONOR_CONSECUTIVE" in why,why
    yes, detail = event_fingerprint_same_event(second, first, monitoring_profile=True)
    assert yes and "SAME_DONOR" in detail,detail
    assert not same_source_telegram_thread_2346(second,dict(first,source_id=188))[0]
    assert not same_source_telegram_thread_2346(second,dict(first,source_url="https://t.me/mih_gromada/5990"))[0]
    assert not same_source_telegram_thread_2346(second,dict(first,source_published_at="2026-11-19T12:03:00+02:00"))[0]
    # A new verifiable count is not the same event update.
    assert not same_source_telegram_thread_2346(
        dict(second,raw_text=second["raw_text"]+" Уже 150 дітей відвідали укриття."),first)[0]
    # A lifecycle change must remain a new report even if the headline overlaps.
    assert not same_source_telegram_thread_2346(
        dict(second,raw_text="Через обстріл закрили модульне укриття біля школи Михайлівської громади."),first)[0]


def test_different_neighbouring_posts_from_same_donor_not_a_duplicate():
    from telegram_autopilot.v2.monitoring_no_event_2346 import same_source_telegram_thread_2346
    road = {"source_id":159,"source_url":"https://t.me/mih_gromada/6001",
            "title":"На мосту перекрили смугу після ДТП",
            "raw_text":"Дорожня поліція повідомила про аварію на мосту, обмежено проїзд автомобілів.",
            "source_published_at":"2026-11-20T12:07:00+02:00"}
    clinic = dict(road, source_url="https://t.me/mih_gromada/6002",
                  title="У громаді відновили прийом у дитячій поліклініці",
                  raw_text="Лікарі відновили прийом дітей у поліклініці з 13:00, оприлюднили новий графік.")
    assert not same_source_telegram_thread_2346(clinic, road)[0]
    assert not event_fingerprint_same_event(clinic, road, monitoring_profile=True)[0]
