"""2.2.4 monitoring: event types, live-now vocabulary, no padding, initiative dedupe.

Operator LIVE review 19.10 (ЗАПОРІЖЖЯ | ГРОМАДИ): "Загроза КАБ", "реактивний
мопед", "Орки знову закидають КАБами Оріхів", a lost bag notice and three
"ВідНОВА:UA" posts were published. Only settled summaries of attacks are wanted.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import (
    DEFAULT_MONITORING_BLOCKED_EVENT_TYPES, ChannelConfig, ChannelMode, ChannelPolicy, Decision,
)
from telegram_autopilot.v2.editorial import EditorialEngine, _monitoring_limits
from telegram_autopilot.v2.initiative_dedupe import find_initiative_duplicate, initiative_keys
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.storage import V2Store, now_iso


def _channel(blocked: str = DEFAULT_MONITORING_BLOCKED_EVENT_TYPES, days: int = 7) -> ChannelConfig:
    return ChannelConfig(
        id=3, name="ЗАПОРІЖЖЯ | ГРОМАДИ", telegram_chat_id="-1001", mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(
            channel_id=3, selection_rules="Місцеві новини громад.",
            rejection_rules="[LIVE_NOW_RC96] Не брати live-now сигнали",
            monitoring_blocked_event_types=blocked, initiative_dedupe_days=days,
        ),
    )


def _article(text: str) -> dict:
    return {"title": text, "raw_text": text, "source_name": "Оріхівська громада", "source_url": "https://t.me/ormr_gov_ua/22199"}


# ------------------------------------------------------------------ live-now vocabulary

@pytest.mark.parametrize("text", [
    "❗ Загроза КАБ для передмістя",
    "🤬Загроза КАБ❗️реактивний мопед",
    "Зафіксовано запуск реактивного мопеда",
    "🚧🤬⚡️Орки знову закидають КАБами Оріхів та сусідів",
    "Загроза застосування керованих авіабомб",
    "🚧🚀🚀 РСЗВ вдарило по Юрївці.",
])
def test_live_alerts_and_unsettled_attacks_are_rejected_before_ai(text):
    assert live_now_exclusion(_channel(), _article(text))


@pytest.mark.parametrize("text", [
    "Внаслідок ранкової атаки КАБами на Кушугум пошкоджено 12 будинків, 3 людини поранені",
    "Оріхів: за підсумками атаки КАБами загинули 2 людини",
    "У кабінеті ЦНАПу змінився графік прийому громадян",
    "Ремонт кабелю: завтра відключать світло на трьох вулицях",
    "Модульне укриття вже встановили на площі Поляка у Запоріжжі.",
    "Шановні батьки! Діти катаються на мопедах без шоломів, просимо провести бесіду.",
])
def test_settled_summaries_and_ordinary_words_pass(text):
    assert not live_now_exclusion(_channel(), _article(text))


# ------------------------------------------------------------------ typed selector

class _Gateway:
    def __init__(self, payload: dict):
        self.text = json.dumps(payload, ensure_ascii=False)

    def run(self, prompt, **kwargs):
        assert '"included":true' not in prompt.replace(" ", "")   # no ready-made answer in the schema
        return SimpleNamespace(text=self.text, provider="test", model="test-model")


def _select(payload: dict, channel: ChannelConfig | None = None, text: str = "У громаді відкрили центр підтримки."):
    engine = object.__new__(EditorialEngine)
    engine.gateway = _Gateway(payload)
    return engine._select_monitoring(channel or _channel(), _article(text))


def _payload(event_type: str, *, settled: bool = True, included: bool = True, excluded: bool = False,
             reason: str = "Конкретне повідомлення громади з фактами.") -> dict:
    return {"event_type": event_type, "settled": settled, "included": included, "excluded": excluded, "reason": reason}


@pytest.mark.parametrize("event_type", ["private_ad", "missing_person", "alert_threat", "attack_in_progress"])
def test_blocked_event_types_are_rejected_by_channel_setting(event_type):
    outcome = _select(_payload(event_type))
    assert outcome.decision == Decision.REJECT
    assert outcome.reason.startswith("MONITORING_EVENT_TYPE_BLOCKED: [" + event_type + "]")


def test_unsettled_attack_summary_counts_as_attack_in_progress():
    outcome = _select(_payload("attack_summary", settled=False))
    assert outcome.decision == Decision.REJECT
    assert "[attack_in_progress]" in outcome.reason


def test_settled_attack_summary_and_local_news_pass():
    for event_type in ("attack_summary", "local_news", "initiative"):
        outcome = _select(_payload(event_type))
        assert outcome.decision == Decision.PUBLISH, event_type
        assert f"[{event_type}]" in outcome.reason


def test_type_blocks_come_from_channel_settings_not_code():
    outcome = _select(_payload("private_ad"), channel=_channel(blocked=""))
    assert outcome.decision == Decision.PUBLISH


@pytest.mark.parametrize("payload", [
    _payload("local_news", reason="коротко"),
    _payload("local_news", reason="<одне речення: чому саме таке рішення>"),
    {"included": True, "excluded": False, "reason": "Old schema without a type"},
    {**_payload("local_news"), "event_type": "news"},
    {**_payload("local_news"), "included": "true"},
])
def test_copied_template_or_malformed_answer_is_not_a_decision(payload):
    with pytest.raises(ValueError):
        _select(payload)


# ------------------------------------------------------------------ no padding

def test_short_notice_cannot_be_expanded_into_an_article():
    channel = _channel()
    channel.policy.target_min_chars, channel.policy.target_max_chars = 500, 750
    low, high, _hard = _monitoring_limits(channel, _article("❗ Загроза КАБ для передмістя"), 4000)
    assert high <= int(len("❗ Загроза КАБ для передмістя") * 1.5) + 20
    assert low <= high
    low, high, _hard = _monitoring_limits(channel, _article("Модульне укриття вже встановили на площі Поляка у Запоріжжі."), 4000)
    assert high < 120


# ------------------------------------------------------------------ initiative dedupe

def test_initiative_keys_need_an_initiative_word():
    assert initiative_keys("Триває реєстрація на обміни програми «ВідНОВА:UA» 2026") == {"відноваua"}
    assert initiative_keys("Долучайтеся до фотоконкурсу «Вікі любить пам’ятки»") == {"вікілюбитьпамятки"}
    assert initiative_keys("Поїзди «Укрзалізниці» затримуються на 6 годин") == set()
    assert initiative_keys("Послуга доступна в застосунку «Дія»") == set()


def _seed(store: V2Store, rows: list[tuple[int, str, str, str]]) -> None:
    stamp = now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,enabled,created_at,updated_at) VALUES(3,'c','',1,?,?)", (stamp, stamp))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,initialized,priority) VALUES(1,3,'telegram','s','https://t.me/s/a',1,1,100)")
        for aid, stage, decision, text in rows:
            con.execute(
                """INSERT INTO articles(id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                       discovered_at,stage,decision,published_at,ready_at) VALUES(?,3,1,?,?,?,?,?,?,?,?,?,?)""",
                (aid, f"e{aid}", text[:60], f"https://t.me/a/{aid}", f"https://t.me/a/{aid}", text, stamp, stage, decision,
                 stamp if stage == "PUBLISHED" else "", stamp if stage == "READY" else ""),
            )
        con.commit()


def test_same_initiative_from_another_community_is_a_duplicate(tmp_path):
    store = V2Store(tmp_path / "v2.sqlite3")
    _seed(store, [
        (1, "PUBLISHED", "PUBLISH", "Мінмолодьспорт: Національна програма «ВідНОВА:UA», наказ № 5276."),
        (2, "NEW", "PENDING", "Триває реєстрація на молодіжні обміни програми «ВідНОВА:UA» 2026."),
        (3, "NEW", "PENDING", "Організатори покривають проїзд. Програма «ВідНОВА:UA» впроваджується Мінмолодьспортом. Збір: вул. Шевченка, 5, тел. 067 123 45 67."),
    ])
    found = find_initiative_duplicate(store, store.get_article(2), _channel())
    assert found is not None and found[0] == 1 and found[1].startswith("INITIATIVE_DUPLICATE")
    # Own local logistics (address/phone) make it a separate local event of the initiative.
    assert find_initiative_duplicate(store, store.get_article(3), _channel()) is None
    # The window is a channel setting; 0 disables the rule.
    assert find_initiative_duplicate(store, store.get_article(2), _channel(days=0)) is None


def test_initiative_window_defaults_on_only_for_monitoring(tmp_path):
    store = V2Store(tmp_path / "v2.sqlite3")
    with store.connect() as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(channel_policies)")}
    assert {"monitoring_blocked_event_types", "initiative_dedupe_days"} <= cols
    assert ChannelPolicy().initiative_dedupe_days == 0
    assert ChannelPolicy().blocked_event_types() == frozenset()
    assert ChannelPolicy(monitoring_blocked_event_types="private_ad, bogus;alert_threat").blocked_event_types() == {"private_ad", "alert_threat"}
