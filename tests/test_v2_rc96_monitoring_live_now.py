from __future__ import annotations

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.migration_repair import repair_polling_baseline
from telegram_autopilot.v2.monitoring_live_now import live_now_exclusion
from telegram_autopilot.v2.storage import V2Store

LIVE_RULE = "[LIVE_NOW_RC96] Не публікувати оперативні live-now події."


def _channel(rule: str = LIVE_RULE) -> ChannelConfig:
    return ChannelConfig(
        id=3,
        name="monitoring-test",
        telegram_chat_id="-1001",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(channel_id=3, rejection_rules=rule),
    )


def test_live_now_examples_are_rejected_but_durable_facts_survive() -> None:
    rejected = (
        "У Запоріжжі зафіксували рух мопеда через Шевченківський район у напрямку автовокзалу.",
        "Повітряна тривога у Запорізькій області.",
        "Відбій повітряної тривоги.",
        "Загроза застосування БпЛА.",
        "Зараз палає будівля у центрі міста.",
        "Щойно пролетів дрон над районом.",
    )
    allowed = (
        "Запоріжжя було атаковано вночі, пошкоджено два будинки.",
        "У місті відкрили новий центр підтримки.",
        "Завтра буде змінено маршрут автобуса №5.",
        "У Запоріжжі знайшли номерні знаки.",
        "У громаді побудували укриття.",
    )
    for text in rejected:
        assert live_now_exclusion(_channel(), {"title": text, "raw_text": text})
    for text in allowed:
        assert live_now_exclusion(_channel(), {"title": text, "raw_text": text}) == ""


def test_live_now_gate_is_channel_policy_opt_in() -> None:
    text = "У Запоріжжі зафіксували рух мопеда у напрямку автовокзалу."
    assert live_now_exclusion(_channel("Не брати календарні привітання"), {"title": text, "raw_text": text}) == ""


def test_upgrade_seeds_existing_monitoring_channel_policy_once(tmp_path) -> None:
    store = V2Store(tmp_path / "autopilot.sqlite3")
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(?,?,?,?,datetime('now'),datetime('now'))",
            ("test-monitor", "-1001", 1, "monitoring"),
        )
        cid = int(con.execute("SELECT id FROM channels WHERE name='test-monitor'").fetchone()[0])
        con.execute(
            "INSERT INTO channel_policies(channel_id,rejection_rules,updated_at) VALUES(?,?,datetime('now'))",
            (cid, "Не брати привітання"),
        )
        con.execute("DELETE FROM meta WHERE key='rc96_monitoring_live_now_policy_v1'")
    first = repair_polling_baseline(store)
    second = repair_polling_baseline(store)
    with store.connect() as con:
        rules = str(con.execute("SELECT rejection_rules FROM channel_policies WHERE channel_id=?", (cid,)).fetchone()[0])
    assert first["live_now_channels_changed"] == 1
    assert second["live_now_channels_changed"] == 0
    assert rules.count("[LIVE_NOW_RC96]") == 1
