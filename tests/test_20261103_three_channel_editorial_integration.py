"""Regression for full human-calibrated editorial integration.

No external AI calls; fixtures demonstrate the operator's dated LIVE failures.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import timedelta, datetime
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2.domain import ChannelMode, EditorialRuntimeProfile, DedupeProfile
from telegram_autopilot.v2.editorial_human_calibration_20261103 import (
    MARKER, MIGRATION_KEY, BACKUP_KEY,
    apply_human_editorial_policy, human_calibrated_editorial,
)
from telegram_autopilot.v2.monitoring_sports_event_20261103 import sports_medal_same_event
from telegram_autopilot.v2.source_final_fidelity_255 import source_final_fidelity_issues


class _Store:
    def __init__(self, path: Path):
        self.path = str(path)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()


def _policy_fixture(tmp_path: Path) -> _Store:
    store = _Store(tmp_path / "test.sqlite")
    with store.connect() as con:
        con.executescript("""
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE channels(
               id INTEGER PRIMARY KEY, channel_mode TEXT,
               editorial_runtime_profile TEXT, dedupe_profile TEXT,
               dedupe_scientific_names INTEGER, dedupe_compound_events INTEGER
            );
            CREATE TABLE channel_policies(
               channel_id INTEGER PRIMARY KEY,
               purpose TEXT, audience TEXT,
               selection_rules TEXT, rejection_rules TEXT,
               selector_extra_prompt TEXT, writer_extra_prompt TEXT,
               updated_at TEXT
            );
        """)
        con.executemany(
            "INSERT INTO channels VALUES(?,?,?,?,?,?)",
            [
                (1, "editorial", "standard", "scientific_news", 1, 1),
                (2, "editorial", "commercial_editorial", "commercial_editorial", 0, 0),
                (3, "monitoring", "standard", "standard", 0, 0),
            ],
        )
        con.executemany(
            "INSERT INTO channel_policies VALUES(?,?,?,?,?,?,?,?)",
            [(cid, "old purpose", "old audience", "old selection", "old reject",
              "old selector", "old writer", "old date")
             for cid in (1, 2, 3)],
        )
    return store


def test_scope_backup_idempotence_and_monitoring_untouched(tmp_path):
    store = _policy_fixture(tmp_path)
    assert apply_human_editorial_policy(store) == 2
    with store.connect() as con:
        items = {
            int(row["channel_id"]): dict(row)
            for row in con.execute("SELECT * FROM channel_policies").fetchall()
        }
        assert items[1]["selection_rules"].startswith(MARKER)
        assert items[2]["selection_rules"].startswith(MARKER)
        assert items[3]["selection_rules"] == "old selection"
        assert items[3]["rejection_rules"] == "old reject"
        assert "вірусності" in items[2]["selection_rules"]
        assert "популярна наука" in items[1]["selection_rules"]
        backup = json.loads(con.execute(
            "SELECT value FROM meta WHERE key=?", (BACKUP_KEY,)
        ).fetchone()[0])
        assert backup["1"]["selection_rules"] == "old selection"
        assert backup["2"]["writer_extra_prompt"] == "old writer"
        assert "3" not in backup
        assert con.execute(
            "SELECT value FROM meta WHERE key=?", (MIGRATION_KEY,)
        ).fetchone()[0] == "1"
    assert apply_human_editorial_policy(store) == 0


def test_marker_only_targets_selected_profile():
    science = SimpleNamespace(
        mode=ChannelMode.EDITORIAL,
        editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
        dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
        dedupe_scientific_names=True, dedupe_compound_events=True,
        policy=SimpleNamespace(selection_rules=MARKER + " science"),
    )
    assert human_calibrated_editorial(science)
    science.policy.selection_rules = "legacy"
    assert not human_calibrated_editorial(science)
    science.mode = ChannelMode.MONITORING
    science.policy.selection_rules = MARKER
    assert not human_calibrated_editorial(science)


def _sports(source: str, stamp: str):
    return {"raw_text": source, "source_published_at": stamp}


A = (
    "Запорізькі спортсмени здобули нагороди на міжнародних змаганнях: "
    "Тхеквондо, Катар, Максим Маненков, срібло; шашки, Нідерланди, "
    "Богдан Панченков, срібло; веслування, Аргентина, "
    "Людмила Бабак, бронза."
)
B = (
    "Запорізькі спортсмени отримали медалі на чемпіонатах: "
    "Максим Маненков у Катарі з тхеквондо, Богдан Панченков "
    "у Нідерландах із шашок, Людмила Бабак в Аргентині з веслування."
)


def test_same_zaporizhzhia_athletes_digest_different_source():
    a = _sports(A, "2026-11-02T15:29:01+02:00")
    b = _sports(B, "2026-11-02T15:44:58+02:00")
    same, reason = sports_medal_same_event(a, b)
    assert same
    assert "максим маненков" in reason


def test_distinct_medal_event_not_silenced():
    a = _sports(A, "2026-11-02T15:29:01+02:00")
    b = _sports(B, "2026-11-10T15:44:58+02:00")
    assert not sports_medal_same_event(a, b)[0]
    c = _sports(B.replace("Людмила Бабак", "Оксана Середа"),
                "2026-11-02T15:44:58+02:00")
    assert not sports_medal_same_event(a, c)[0]


def test_power_outage_source_schedule_cannot_disappear_from_final():
    article = {"raw_text":
        "Знову оновлено графіки відключень світла. Черга 1.1 з 09:00 до 13:00 "
        "та з 16:00 до 20:00. Черга 1.2 з 08:00 до 12:00."}
    poor = "У Запоріжжі оновили графіки відключень світла. Задіяні всі підчерги."
    assert "FACT_POWER_SCHEDULE_TIME_WINDOWS_LOST_20261103" in (
        source_final_fidelity_issues(article, poor)
    )
    complete = ("Графіки відключень світла: черга 1.1 з 09:00 до 13:00 "
                "та з 16:00 до 20:00; черга 1.2 з 08:00 до 12:00.")
    assert "FACT_POWER_SCHEDULE_TIME_WINDOWS_LOST_20261103" not in (
        source_final_fidelity_issues(article, complete)
    )


def test_unrelated_timings_not_blocked():
    article = {"raw_text": "Графік засідання комісії: з 09:00 до 10:00 та з 11:00 до 12:00."}
    assert not source_final_fidelity_issues(article, "Засідання комісії відбудеться сьогодні.")
