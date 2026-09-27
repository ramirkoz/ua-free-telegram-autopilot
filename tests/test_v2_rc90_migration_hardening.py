from __future__ import annotations

import sqlite3
from pathlib import Path

from telegram_autopilot.v2.migration_repair import repair_polling_baseline
from telegram_autopilot.v2.storage import V2Store, now_iso


def test_poll_marker_is_not_consumed_before_channels_exist(tmp_path: Path) -> None:
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    store = V2Store(db)

    first = repair_polling_baseline(store)
    assert first == {"repaired": False, "reason": "no_channels", "channels_changed": 0}

    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,poll_interval_minutes,created_at,updated_at)
               VALUES(1,'Imported','@imported',1,'editorial',5,?,?)""",
            (stamp, stamp),
        )

    second = repair_polling_baseline(store)
    assert second["repaired"] is True
    assert second["channels_changed"] == 1
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 15


def test_polling_baseline_runs_once_then_respects_operator_changes(tmp_path: Path) -> None:
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    store = V2Store(db)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,poll_interval_minutes,created_at,updated_at)
               VALUES(1,'A','@a',1,'editorial',5,?,?)""",
            (stamp, stamp),
        )

    result = repair_polling_baseline(store)
    assert result["repaired"] is True
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 15
        con.execute("UPDATE channels SET poll_interval_minutes=20 WHERE id=1")
        con.commit()

    again = repair_polling_baseline(store)
    assert again["reason"] == "already_applied"
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT poll_interval_minutes FROM channels WHERE id=1").fetchone()[0] == 20
