from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from telegram_autopilot import ai_router
from telegram_autopilot import rc81_runtime as rc81


def test_outage_classifier_distinguishes_transport_from_qa():
    assert rc81._provider_outage_text("Network request failed: https://example")
    assert rc81._provider_outage_text("404 Not Found: The model gpt-5.5 does not exist")
    assert not rc81._provider_outage_text("AI-моделі відповіли, але редакційний QA відхилив усі кандидати")


def test_cooldown_wrapper_promotes_model_404_to_long_provider_breaker(monkeypatch):
    seen = {}
    monkeypatch.setattr(rc81, "_ORIGINAL_SET_COOLDOWN", lambda slot, seconds, reason, provider=False: seen.update(seconds=seconds, provider=provider))
    slot = ai_router.Slot(1, "codex", "codex-chatgpt", "Codex", "codex")
    rc81._set_slot_cooldown_rc81(slot, 45, "404 Not Found: The model gpt-5.5 does not exist", provider=False)
    assert seen["seconds"] >= 7 * 24 * 3600
    assert seen["provider"] is True


def test_cooldown_wrapper_promotes_local_timeout_to_30_minutes(monkeypatch):
    seen = {}
    monkeypatch.setattr(rc81, "_ORIGINAL_SET_COOLDOWN", lambda slot, seconds, reason, provider=False: seen.update(seconds=seconds, provider=provider))
    slot = ai_router.Slot(9, "local", "local-model", "Local", "local")
    rc81._set_slot_cooldown_rc81(slot, 90, "Ollama не завершила локальне AI-завдання за 30 секунд", provider=False)
    assert seen["seconds"] >= 30 * 60


class _MiniDb:
    def __init__(self, path):
        self.path = path
        con = sqlite3.connect(path)
        con.executescript(
            """
            CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE articles(
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                event_cluster_id INTEGER,
                cluster_parent_id INTEGER,
                duplicate_of INTEGER,
                reject_reason TEXT,
                last_error TEXT,
                processing_started_at TEXT,
                next_retry_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        con.commit(); con.close()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        try:
            yield con
            con.commit()
        finally:
            con.close()


def test_cluster_repair_is_throttled_and_not_hot_new_queue(tmp_path):
    db = _MiniDb(tmp_path / "rc81-cluster.sqlite3")
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    with db.connect() as con:
        for i in range(1, 26):
            con.execute("INSERT INTO articles VALUES(?, 'clustered', ?, 1, 1, NULL, 'x', NULL, NULL, NULL, 0)", (i, recent))
    assert rc81._repair_recent_clusters_throttled(db, batch_size=20) == 20
    with db.connect() as con:
        counts = dict(con.execute("SELECT status,COUNT(*) FROM articles GROUP BY status").fetchall())
    assert counts == {"clustered": 5, "retry": 20}


def test_outage_recovery_is_bounded_and_staggered(tmp_path):
    db = _MiniDb(tmp_path / "rc81-outage.sqlite3")
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    with db.connect() as con:
        for i in range(1, 40):
            con.execute(
                "INSERT INTO articles VALUES(?, 'error', ?, NULL, NULL, NULL, NULL, 'Network request failed', NULL, NULL, 5)",
                (i, recent),
            )
    assert rc81._repair_recent_ai_failures(db, limit=30) == 30
    with db.connect() as con:
        rows = con.execute("SELECT status,next_retry_at,retry_count FROM articles ORDER BY id DESC").fetchall()
    assert sum(1 for row in rows if row[0] == "retry") == 30
    assert all(row[2] == 0 for row in rows if row[0] == "retry")
    retry_times = [row[1] for row in rows if row[0] == "retry"]
    assert len(set(retry_times)) == 30
