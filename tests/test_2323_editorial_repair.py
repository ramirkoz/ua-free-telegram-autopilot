"""2.3.23 editorial repair: regressions from the 2.3.22 LIVE failure (10.11.2026).

Evidence: operator SQLite snapshot + 1 472 human labels. Texts below are
shortened excerpts of the real source posts; no private data is added.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from telegram_autopilot.v2 import editorial as ed
from telegram_autopilot.v2.ai_gateway import AIGateway, GatewayExhausted, _contract_class_failure
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy, Decision
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_operator_2321 import (
    VERIFY_PUBLISH_PROMPT_2321, verify_low_confidence_publish,
)
from telegram_autopilot.v2.editorial_second_opinion_2320 import SECOND_OPINION_INSTRUCTION_2320
from telegram_autopilot.v2.event_dedupe_guard import _fingerprint_stats, _validated_cluster_same_event
from telegram_autopilot.v2.monitoring_call_to_action import call_to_action_reason
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.monitoring_service_facts import structured_schedule, utility_service_update
from telegram_autopilot.v2.numeric_grounding import unsupported_numbers
from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322


def _art(text: str, title: str = "") -> dict:
    return {"title": title or text[:80], "raw_text": text, "source_name": "Оріхівська громада",
            "source_url": "https://t.me/ormr_gov_ua/1"}


# ------------------------------------------------------------------ P0-A selector contract

def test_prompts_do_not_contain_a_ready_made_answer():
    for prompt in (VERIFY_PUBLISH_PROMPT_2321, SECOND_OPINION_INSTRUCTION_2320):
        compact = prompt.replace(" ", "")
        assert '"decision":"reject"' not in compact and '"decision":"publish"' not in compact
        assert "конкретне пояснення" not in prompt and "коротка конкретна причина" not in prompt


@pytest.mark.parametrize("reason", ["конкретне пояснення", "Конкретне пояснення.", "фактологічна причина",
                                    "коротко", "specific explanation", "", "<одне речення>"])
def test_template_wording_is_not_a_decision(reason):
    assert ed.placeholder_reason(reason)


def test_real_reason_is_accepted():
    assert not ed.placeholder_reason("Стаття описує новий результат вимірювання температури з цифрами.")


def test_score_no_longer_triggers_the_vetoing_review():
    assert not verify_low_confidence_publish("science", 12, {"title": "Pink noise during sleep may help the brain"})
    assert verify_low_confidence_publish("creative", 95, {"title": "Brand appoints agency as lead creative agency"})


class _Learning:
    def topic_assessment(self, cid, row):
        return SimpleNamespace(hard_suppress=False, fit_adjustment=0)

    def topic_memory_block(self, cid, row):
        return ""


def _science_channel():
    policy = ChannelPolicy(selection_rules=MARKER + " цікава наука", rejection_rules="PR", purpose="p", audience="a")
    from telegram_autopilot.v2.domain import DedupeProfile, EditorialRuntimeProfile
    return SimpleNamespace(id=1, mode=ChannelMode.EDITORIAL, editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
                           dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS, dedupe_scientific_names=True,
                           dedupe_compound_events=True, policy=policy)


def _engine(gateway):
    engine = object.__new__(ed.EditorialEngine)
    engine.learning, engine.gateway, engine.store = _Learning(), gateway, None
    return engine


_SCI = {"id": 7, "title": "Pink noise during sleep could help the brain clear waste", "source_name": "t",
        "raw_text": "Researchers measured brain fluid flow in 30 sleeping adults. Bursts of pink noise increased it."}


def test_copied_placeholder_is_invalid_and_the_next_model_decides():
    answers = ['{"decision":"reject","reason":"конкретне пояснення","angle":""}',
               '{"decision":"publish","reason":"Дослідники виміряли ефект на 30 людях.","angle":"сон і мозок"}']

    class Gateway:
        calls = 0

        def run(self, prompt, *, validator=None, **kw):
            assert '"fit_score":0' not in prompt.replace(" ", "")
            for text in answers[self.calls:]:
                self.calls += 1
                try:
                    validator(text)
                except ValueError:
                    continue
                return SimpleNamespace(text=text, provider="p", model="m")
            raise GatewayExhausted("all invalid")

    gateway = Gateway()
    out = _engine(gateway)._select_editorial(_science_channel(), _SCI)
    assert gateway.calls == 2
    assert out.decision == Decision.PUBLISH and out.reason.startswith("HUMAN_EDITORIAL_236_PASS")


def test_review_cap_and_review_failure_defer_instead_of_rejecting():
    channel = _science_channel()
    engine = _engine(SimpleNamespace(run=lambda *a, **k: (_ for _ in ()).throw(ValueError("AI не повернув JSON"))))
    with pytest.raises(GatewayExhausted):
        engine._operator_verify_publish_2321(channel, _SCI, "science", 70)
    import time
    engine._coverage_reviews_234 = {"1:publish_2321": [time.monotonic()] * 8}
    with pytest.raises(GatewayExhausted) as caught:
        engine._operator_verify_publish_2321(channel, _SCI, "science", 70)
    assert "CAP" in str(caught.value)


# ------------------------------------------------------------------ P0-B no announcements

@pytest.mark.parametrize("text,code", [
    ("Запоріжжя, поверніться у Середзем’я на один вечір. 10 листопада музика Говарда Шора прозвучить наживо. "
     "Сьогодні на каналі пройде конкурс - розігруємо квитки на концерт. Розіграш квитків з 12:00 по 12:20.",
     "MONITORING_GIVEAWAY"),
    ("Благодійний фонд звертається з проханням взяти участь у проведенні дослідження у сфері зайнятості. "
     "Опитування триватиме до 18 листопада. Анкета для участі в опитуванні доступна за посиланням.",
     "MONITORING_SURVEY_INVITATION"),
    ("Чому ваша думка важлива? Усі дані опрацьовуватимуться в узагальненому вигляді. "
     "Пройти опитування можна за посиланням: https://ee-eu.kobotoolbox.org/x/abc",
     "MONITORING_SURVEY_INVITATION"),
    ("Бульвар Марії Примаченко, 7, опаленням навіть не \"пахне\". В квартирах +14 градусів. Керуюча компанія, агов! "
     "Якщо у вас немає опалення — пишіть нам оголошення в такому вигляді: адреса.",
     "MONITORING_READER_COMPLAINT"),
    ("Від «Володаря Перснів» до рок-хітів: у філармонії підготували музичний тиждень. У програмі — знайомі мелодії, "
     "концерт при свічках. Також на запоріжців чекають дві прем’єри.",
     "MONITORING_FUTURE_EVENT_INVITATION"),
    ("Відкривається можливість безоплатного відпочинку для дітей. Триває набір на зміну, подати заявку можна до п'ятниці.",
     "MONITORING_APPLICATION_CALL"),
])
def test_calls_to_action_are_vetoed_from_source_text(text, code):
    assert call_to_action_reason(_art(text)) == code
    # The shared entry point guards selection AND READY rows right before a send;
    # an older, more specific 2.3.22 code may win there, but it must block.
    assert no_announcement_reason_2322(_art(text)).startswith("MONITORING_")


@pytest.mark.parametrize("text", [
    "Внаслідок ворожого удару по Запоріжжю постраждала 66-річна жінка. Її госпіталізували, повідомили в ОВА.",
    "У Запоріжжі провели заняття з живопису для людей старшого віку. Учасники створювали власні картини. "
    "Хочете долучитися до наступних зустрічей? Стежте за анонсами.",
    "10 та 11 листопада тимчасово не працюють реєстраційні та паспортні послуги через технічні роботи в реєстрах.",
    "У Дніпрорудненській громаді відбувся семінар для фахівців. Учасники взяли участь у практичних заняттях.",
    "Департамент соціального захисту міської ради оголосив прийом заявок на грошову допомогу ВПО.",
    "Місто очима його мешканців: у Запоріжжі презентували фотозін. Видання розповідає про жителів через фото.",
    "За результатами опитування мешканців міськрада змінила графік руху автобуса № 18.",
])
def test_facts_services_and_finished_events_are_not_announcements(text):
    assert call_to_action_reason(_art(text)) == ""


# ------------------------------------------------------------------ utility schedules

_GPV = ("Оновлено ГПВ на сьогодні:⚡ Черга 1.1 з 06:30 до 10:30 з 14:30 до 19:00"
        "⚡ Черга 1.2 з 08:30 до 13:30 з 17:30 до 22:30")


def _monitoring_channel():
    return ChannelConfig(id=3, name="г", telegram_chat_id="-1", mode=ChannelMode.MONITORING, policy=ChannelPolicy(
        channel_id=3, rejection_rules="3. ПРОСТІ РЕПОСТИ: не публікуй переслане. [LIVE_NOW_RC96]",
        monitoring_source_policy="connected_original"))


def test_forwarded_outage_schedule_is_not_vetoed_as_a_repost():
    import json
    article = {**_art(_GPV), "article_layout_json": json.dumps({"telegram": {"forwarded": True}})}
    assert utility_service_update(article) and structured_schedule(article)
    assert ed._monitoring_official_context_reject(article, _monitoring_channel()) == ""
    assert "репост" not in ed.deterministic_monitoring_exclusion(_monitoring_channel(), article)
    other = {**_art("Що таке «Гайд із кібергігієни» від Держспецзв’язку та чому варто з ним ознайомитися? "
                    "Це практичний посібник для громадян."),
             "article_layout_json": json.dumps({"telegram": {"forwarded": True}})}
    assert ed._monitoring_official_context_reject(other, _monitoring_channel()) == "MONITORING_NOT_ORIGINAL_FORWARD"


def test_schedule_table_passes_the_two_sentence_source_floor():
    class NeedsAI(Exception):
        pass

    engine = object.__new__(ed.EditorialEngine)
    engine.gateway = SimpleNamespace(run=lambda *a, **k: (_ for _ in ()).throw(NeedsAI()))
    engine.store = None
    with pytest.raises(NeedsAI):
        engine.select(_monitoring_channel(), _art(_GPV))
    short = engine.select(_monitoring_channel(), _art("Запоріжжя чекає своїх Захисників додому"))
    assert short.decision == Decision.REJECT and short.reason.startswith("EDITORIAL_MIN_TWO_SENTENCES")


def test_utility_rumour_is_not_a_service_update():
    assert not utility_service_update(_art("Кажуть, що завтра нібито будуть відключення світла з 10:00 до 12:00."))


# ------------------------------------------------------------------ live-now false positives

@pytest.mark.parametrize("text", [
    "У Запоріжжі через атаку БпЛА поранено 66-річну жінку. По селах Бабурка та Кущове ворог вдарив авіабомбами.",
    "Внаслідок російського удару спалахнув будинок у передмісті Запоріжжя. Рятувальники ліквідували пожежу.",
])
def test_reported_outcome_is_an_aftermath_report(text):
    assert live_now_exclusion(_monitoring_channel(), _art(text)) == ""


@pytest.mark.parametrize("text", ["Ланцет на Оріхів", "❗ Загроза КАБ для передмістя", "Шахед у напрямку Запоріжжя"])
def test_bare_threat_direction_is_still_blocked(text):
    assert live_now_exclusion(_monitoring_channel(), _art(text))


def test_long_narrative_is_not_an_operational_signal():
    story = ("Понад 60 км через міни та дрони: 69-річний житель Пологів утік з окупації на велосипеді. "
             + "Чоловік майже п'ять років прожив в окупованих Пологах, доглядав за хворою тещею. " * 6)
    assert ed._postfactum_security_policy(_monitoring_channel(), _art(story)) == ""
    assert ed._postfactum_security_policy(_monitoring_channel(), _art("Вибух у місті. Дрон над центром."))


# ------------------------------------------------------------------ P0-C number grounding and routing

@pytest.mark.parametrize("source,draft", [
    ("У середу, 11 листопада 2026 року з 10.00до 11.00 відбудеться лінія", "11 листопада 2026 року з 10:00 до 11:00"),
    ("зустріч з 10-00 до 13:00 (вул. Миру, 14 В)", "з 10:00 до 13:00 на вул. Миру, 14"),
    ("діє з 20.10.2026 до 20.11.2026Пропозиція", "до 20 листопада 2026 року"),
    ("Телефони:📲 +380676138616📲 +380672738096Не втрачайте", "+380 67 613 86 16 та +380672738096"),
    ("Понад 8,3 млн грн спрямовано", "спрямували понад 8,3 млн грн"),
])
def test_correctly_rewritten_source_numbers_are_grounded(source, draft):
    assert unsupported_numbers(source, draft) == []


@pytest.mark.parametrize("source,draft,bad", [
    ("Понад 8,3 млн грн спрямовано", "спрямували понад 9,3 млн грн", "9.3"),
    ("загинули 2 людини", "загинули 3 людини", "3"),
    ("відключення з 22:30", "відключення з 21:3041", "21:3041"),
    ("з 10.00 до 11.00", "з 10:00 до 12:00", "12:00"),
])
def test_invented_numbers_are_still_reported(source, draft, bad):
    assert bad in unsupported_numbers(source, draft)


def test_contract_failures_demote_a_model_for_that_task_only():
    gateway = object.__new__(AIGateway)
    slots = [SimpleNamespace(model="tiny", provider="openrouter"), SimpleNamespace(model="good", provider="openrouter")]
    for _ in range(5):
        gateway._note_contract_outcome("monitoring_selector", "tiny", ok=False, error=ValueError("AI не повернув JSON"))
    gateway._note_contract_outcome("monitoring_selector", "good", ok=True)
    assert [s.model for s in gateway._order_by_contract_success(list(slots), "monitoring_selector")] == ["good", "tiny"]
    assert [s.model for s in gateway._order_by_contract_success(list(slots), "writer")] == ["tiny", "good"]
    assert _contract_class_failure("reasoning but no final content")
    assert not _contract_class_failure("AI додав число, якого немає у джерелі: 90")


def test_openrouter_contract_is_not_excluded_by_a_legacy_provider_whitelist():
    import inspect
    source = inspect.getsource(AIGateway.run)
    assert "openrouter_contract" in source
    assert "provider not in allowed and not openrouter_contract" in source


# ------------------------------------------------------------------ P1 dedupe

def _stats(headline_shared):
    return {"containment": 0.9, "salient_containment": 0.8, "salient_shared": {f"w{i}" for i in range(14)},
            "shared_entities": {"creative", "lives"}, "shared_actions": set(), "shared_rare": set(),
            "shared_scientific": set(), "quantity_pairs": [(1, 1)], "duration_pairs": [], "numeric_pairs": [],
            "headline_shared": headline_shared, "headlines_known": True}


def test_shared_footer_or_series_intro_is_not_a_duplicate():
    assert _validated_cluster_same_event(_stats(set()))[0] is False
    assert _validated_cluster_same_event(_stats({"оріхів"}))[0] is True


def test_headline_terms_come_from_the_title_not_the_footer():
    footer = " Ми в WhatsApp https://whatsapp.com/channel/x Instagram TikTok Threads"
    a = {"title": "Файний протон", "raw_text": "Файний протон." + footer}
    b = {"title": "На вул. Скворцова починається неймовірне", "raw_text": "На вул. Скворцова починається неймовірне." + footer}
    stats = _fingerprint_stats(a, b)
    assert stats["headlines_known"] and not stats["headline_shared"]


# ------------------------------------------------------------------ sources

def test_dead_commercial_sources_are_disabled_once_and_working_feeds_added():
    from test_2322_no_announcements_consumer_portfolio import FakeStore
    from telegram_autopilot.v2.commercial_sources_2322 import apply_commercial_sources_2322
    from telegram_autopilot.v2.commercial_sources_2323 import apply_commercial_sources_2323

    store = FakeStore()
    assert apply_commercial_sources_2323(store)["channels"][0]["status"] == "custom_preserved"
    apply_commercial_sources_2322(store)
    store.db.execute("INSERT INTO sources(channel_id,name,url,kind,enabled,initialized,priority) "
                     "VALUES(2,'My custom','https://custom.example/feed','rss',1,1,5)")
    store.db.commit()
    total = store.db.execute("SELECT count(*) FROM sources").fetchone()[0]
    report = apply_commercial_sources_2323(store)["channels"][0]
    assert report["status"] == "applied"
    assert "My Modern Met" in report["disabled_dead_sources"]
    assert set(report["new_feeds"]) == {"designboom — Art", "The Awesomer"}
    # nothing deleted, custom row untouched, new feeds start uninitialised (no backlog replay)
    assert store.db.execute("SELECT count(*) FROM sources").fetchone()[0] == total + 2
    assert store.db.execute("SELECT enabled FROM sources WHERE name='My custom'").fetchone()[0] == 1
    assert store.db.execute("SELECT enabled FROM sources WHERE name='My Modern Met'").fetchone()[0] == 0
    assert store.db.execute("SELECT initialized FROM sources WHERE name='The Awesomer'").fetchone()[0] == 0
    assert apply_commercial_sources_2323(store)["channels"][0]["status"] == "already_applied"
