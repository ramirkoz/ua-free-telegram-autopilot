"""2.3.30 owner-confirmed LIVE editorial escapes and positive controls.

No AI, network or operator Data. The test checks both production entrypoints,
not just a standalone regex. A passing test is NOT 1472-label owner acceptance.
"""
import pytest

from telegram_autopilot.v2 import editorial as ed
from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, ChannelPolicy, Decision,
    DedupeProfile, EditorialRuntimeProfile,
)
from telegram_autopilot.v2.editorial_human_calibration_236 import MARKER
from telegram_autopilot.v2.editorial_source_topic_2319 import editorial_source_topic_reason_2319
from telegram_autopilot.v2.private_document_contact_2322 import no_announcement_reason_2322


SCIENCE = ChannelConfig(
    id=1, name="Science", telegram_chat_id="-1001", mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
    dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
    dedupe_scientific_names=True, dedupe_compound_events=True,
    policy=ChannelPolicy(channel_id=1, selection_rules=MARKER + " цікава наука"),
)
CREATIVE = ChannelConfig(
    id=2, name="Creative", telegram_chat_id="-1002", mode=ChannelMode.EDITORIAL,
    editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
    policy=ChannelPolicy(channel_id=2, selection_rules=MARKER + " креатив"),
)
MONITOR = ChannelConfig(
    id=3, name="Regional", telegram_chat_id="-1003", mode=ChannelMode.MONITORING,
)
HONDA = {
    "id": 97876,
    "title": "Honda’s $2,000 electric moped is a winner. So why can’t Americans buy it?",
    "raw_text": (
        "Honda has been expanding its electric motorcycle lineup. "
        "Prices now dip close to $2,000 in local markets. In Vietnam the Honda UC3 "
        "electric scooter is a practical commuter. The US market has no announced "
        "sales plan. Price, buyers and local availability determine the market."
    ),
}
NOCTUA = {
    "id": 97917,
    "title": "Noctua brings space-grade carbon nanotube thermal pad to AMD AM5 and AM4 processors — promises years of maintenance-free performance for $24.95",
    "raw_text": (
        "The thermal pad for AMD AM5 processors is a replacement for thermal paste "
        "for desktop CPUs. It promises maintenance-free operation at $24.95."
    ),
}
SENATOR = {
    "id": 97837,
    "title": "Former senator whose arrest went viral on YouTube wins another election",
    "raw_text": (
        "A former senator in Minnesota has been elected to a city council after "
        "a conviction on two felony burglary counts. A true crime YouTuber "
        "reported the incident. The politician won a local election."
    ),
}
VACANCY = {
    "id": 97925,
    "title": "📢 Шукаємо інспектора відділу кадрів у м. Запоріжжя!",
    "raw_text": (
        "Комунальне підприємство Запорізької обласної ради запрошує до команди "
        "фахівця з кадрової справи. Що ми пропонуємо: заробітну плату "
        "від 25 000 грн, офіційне працевлаштування, оплачувану відпустку."
    ),
}


@pytest.mark.parametrize("channel,article,code", [
    (SCIENCE, HONDA, "SCIENCE_ROUTINE_FOREIGN_CONSUMER_AVAILABILITY_2330"),
    (SCIENCE, NOCTUA, "SCIENCE_NICHE_PC_ACCESSORY_RELEASE_2330"),
    (CREATIVE, SENATOR, "CREATIVE_OFFTOPIC_LOCAL_ELECTION_2330"),
])
def test_2330_three_operator_rejected_posts_fail_before_ai_and_at_send(channel, article, code):
    assert editorial_source_topic_reason_2319(channel, article) == code
    engine = object.__new__(ed.EditorialEngine)
    outcome = engine.select(channel, article)
    assert outcome.decision == Decision.REJECT
    assert outcome.reason == code
    assert engine._select_editorial(channel, article).reason == code
    assert ed.hard_editorial_reject(channel, article, "READY rewritten old post") == code


def test_2330_regional_vacancy_blocked_before_ai_and_at_send():
    assert no_announcement_reason_2322(VACANCY) == "MONITORING_JOB_OFFER_2330"
    assert ed.hard_editorial_reject(MONITOR, VACANCY, "Зарплата, подати резюме.") == "MONITORING_JOB_OFFER_2330"


@pytest.mark.parametrize("role,article", [
    ("science", {
        "title": "Researchers demonstrate a novel carbon nanotube cooling mechanism",
        "raw_text": "University researchers measured a new heat transfer property and published experimental findings."
    }),
    ("science", {
        "title": "Honda engineers unveil new solid state battery that improves safety",
        "raw_text": "Engineers tested a new battery chemistry in real-world driving trials."
    }),
    ("science", {
        "title": "Electric scooters achieve first independently tested 1000 km range",
        "raw_text": "Laboratory evidence shows a breakthrough in charging efficiency and energy density."
    }),
    ("science", {
        "title": "New electric scooter could improve accessibility for older people",
        "raw_text": "Researchers presented a new mobility invention and showed accessibility improvements."
    }),
    ("science", {
        "title": "How a paper changed our understanding of superconductors",
        "raw_text": "A new scientific result disproved a published theory."
    }),
    ("creative", {
        "title": "Artists turn election posters into a striking recycled sculpture",
        "raw_text": "An original art installation transforms campaign posters into unusual artwork."
    }),
    ("creative", {
        "title": "An unusual Vietnamese product design blends sculpture and robotics",
        "raw_text": "Designers created a remarkable object with a surprising mechanism."
    }),
    ("creative", {
        "title": "An original campaign turns a senator's speech into a documentary film",
        "raw_text": "An acclaimed documentary film explores political speech through animation."
    }),
    ("creative", {
        "title": "Local council launches public sculpture with interactive projection",
        "raw_text": "An original art installation was unveiled in an urban square."
    }),
])
def test_2330_nontrivial_science_and_creativity_remain_eligible(role, article):
    channel = SCIENCE if role == "science" else CREATIVE
    assert editorial_source_topic_reason_2319(channel, article) == ""


@pytest.mark.parametrize("title,raw", [
    ("У Запоріжжі провели ярмарок вакансій для переселенців",
     "Служба зайнятості провела ярмарок вакансій: взяли участь 200 мешканців, обговорили перенавчання."),
    ("Запорізький центр зайнятості відкрив нову послугу",
     "Відкрили консультації для безробітних. Міськрада підтвердила рішення та графік послуги."),
    ("У Запоріжжі поранено трьох людей через атаку дрона",
     "Російський дрон влучив у рейсовий автобус. Поранено трьох жінок, допомога надається."),
])
def test_2330_real_civic_news_not_vacancies(title, raw):
    assert no_announcement_reason_2322({"title":title,"raw_text":raw}) == ""


def test_2330_a_foreign_country_and_a_price_alone_are_never_vetoes():
    assert editorial_source_topic_reason_2319(SCIENCE, {
        "title":"New $2000 robotic device could save lives in Vietnam",
        "raw_text":"A research lab developed and tested an original disaster-rescue robot."
    }) == ""
