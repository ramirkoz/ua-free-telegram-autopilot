from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot import codex_engine
from telegram_autopilot import rc82_stable_runtime as rc82


def test_selector_unavailable_is_technical_not_editorial_reject(monkeypatch):
    captured = {}

    def original(_db, _article_id, **fields):
        captured.update(fields)

    monkeypatch.setattr(rc82, "_ORIGINAL_UPDATE_ARTICLE", original)
    rc82._update_article_rc82(
        object(),
        10,
        status="rejected",
        reject_reason="SELECTOR_UNAVAILABLE: редакційний selector не дав валідного рішення; AI timeout",
        ai_provider="local-rule",
    )
    assert captured["status"] == "retry"
    assert captured["reject_reason"] is None
    assert str(captured["last_error"]).startswith("WAITING_AI:")
    assert captured["next_retry_at"]


def test_real_channel_policy_reject_stays_rejected(monkeypatch):
    captured = {}

    def original(_db, _article_id, **fields):
        captured.update(fields)

    monkeypatch.setattr(rc82, "_ORIGINAL_UPDATE_ARTICLE", original)
    rc82._update_article_rc82(
        object(),
        11,
        status="rejected",
        reject_reason="CHANNEL_POLICY_REJECT fit=0%: вакансії не входять до збережених inclusion rules",
    )
    assert captured["status"] == "rejected"
    assert "CHANNEL_POLICY_REJECT" in captured["reject_reason"]


class _RetryDb:
    def __init__(self, path: Path):
        self.path = path
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE articles(id INTEGER PRIMARY KEY,status TEXT,retry_count INTEGER,next_retry_at TEXT,last_error TEXT,reject_reason TEXT,processing_started_at TEXT)"
        )
        con.execute("INSERT INTO articles VALUES(1,'retry',9,NULL,'old',NULL,NULL)")
        con.commit(); con.close()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        try:
            yield con
            con.commit()
        finally:
            con.close()


def test_provider_outage_never_becomes_terminal_error(tmp_path):
    db = _RetryDb(tmp_path / "retry.sqlite3")
    for _ in range(8):
        assert rc82._schedule_retry_rc82(db, 1, "Network request failed: timeout", max_attempts=2) == "retry"
    with db.connect() as con:
        row = con.execute("SELECT status,retry_count,last_error,next_retry_at FROM articles WHERE id=1").fetchone()
    assert row[0] == "retry"
    assert row[1] >= 17
    assert str(row[2]).startswith("WAITING_AI:")
    assert row[3]


class _PublishDb:
    def __init__(self):
        self.updated = []

    def get_article(self, article_id):
        return {"id": article_id, "url": ""}


class _Service:
    def __init__(self):
        self.db = _PublishDb()
        self.audits = []

    def _audit(self, *args, **kwargs):
        self.audits.append((args, kwargs))


def test_publish_is_blocked_when_canonical_source_is_missing(monkeypatch):
    service = _Service()
    channel = SimpleNamespace(id=3)
    monkeypatch.setattr(rc82, "_source_urls", lambda _db, _row: [])
    called = {"publish": False}

    def original_publish(*_args, **_kwargs):
        called["publish"] = True
        return True

    def original_update(db, article_id, **fields):
        db.updated.append((article_id, fields))

    monkeypatch.setattr(rc82, "_ORIGINAL_PUBLISH_ONE", original_publish)
    monkeypatch.setattr(rc82, "_ORIGINAL_UPDATE_ARTICLE", original_update)
    assert rc82._publish_one_rc82(service, channel, {"id": 44}) is False
    assert called["publish"] is False
    assert service.db.updated[-1][1]["status"] == "error"
    assert str(service.db.updated[-1][1]["last_error"]).startswith("SOURCE_MISSING:")


def test_publish_with_real_source_uses_proven_rc79_path(monkeypatch):
    service = _Service()
    channel = SimpleNamespace(id=3)
    monkeypatch.setattr(rc82, "_source_urls", lambda _db, _row: ["https://t.me/official_channel/1234"])
    monkeypatch.setattr(rc82, "_ORIGINAL_PUBLISH_ONE", lambda *_args, **_kwargs: True)
    assert rc82._publish_one_rc82(service, channel, {"id": 45}) is True


def test_codex_uses_sdk_reported_default_before_other_models():
    class Response:
        data = [
            {"model": "model-b", "is_default": False},
            {"model": "model-a", "is_default": True},
            {"model": "model-c", "is_default": False},
        ]

    class FakeCodex:
        def models(self, include_hidden=False):
            assert include_hidden is False
            return Response()

    assert codex_engine._ordered_models(FakeCodex()) == ["model-a", "model-b", "model-c"]


def test_main_does_not_install_broken_rc81_runtime():
    source = Path("telegram_autopilot/main.py").read_text(encoding="utf-8")
    assert "install_rc82_stable_runtime()" in source
    assert "install_rc81_runtime()" not in source
    assert "repair_rc81_startup" not in source
