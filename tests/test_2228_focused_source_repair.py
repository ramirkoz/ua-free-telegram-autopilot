"""2.2.28: focused original-source correction and specialist model isolation."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import telegram_autopilot.v2.editorial as editorial
import telegram_autopilot.v2.source_fact_integrity as source_integrity
from telegram_autopilot.secrets_store import SecretConfig
from telegram_autopilot.v2.ai_gateway import AIGateway
from telegram_autopilot.v2.domain import ChannelMode, Decision
from telegram_autopilot.v2.editorial import EditorialEngine, EditorialOutcome
from telegram_autopilot.v2.focused_rewrite import focused_rewrite_instructions
from telegram_autopilot.v2.openrouter_catalog import _chat_compatible_id, _parse
from telegram_autopilot.v2.storage import V2Store, now_iso


PRIOR = (
    "Місцеве джерело спростувало твердження про подію. "
    "Однак попередній переказ безпідставно назвав чутку перевіреним фактом."
)


def _prior_row(**overrides):
    return {
        "id": 77337,
        "channel_id": 3,
        "canonical_source_url": "https://news.example.org/story",
        "title": "Спростовано інформацію про подію",
        "raw_text": "Джерело повідомляє, що чутку не підтверджено. Перевірка триває.",
        "final_text": PRIOR,
        "retry_count": 2,
        "last_error_code": "PREPUBLISH_SOURCE_SAFETY",
        "last_error_detail": "MONITORING_SOURCE_POLARITY_FLIP; MONITORING_UNCERTAINTY_ESCALATION",
        **overrides,
    }


def test_targeted_focus_only_when_factual_prepublish_hard_failure_exists():
    focus = focused_rewrite_instructions(_prior_row())
    assert "заперечення" in focus
    assert "певності" in focus
    assert "не запускаючи вибір новини заново" in focus
    assert focused_rewrite_instructions(_prior_row(last_error_code="SOURCE_MISSING")) == ""
    assert focused_rewrite_instructions(_prior_row(final_text="Немає тексту.")) == ""
    assert focused_rewrite_instructions(_prior_row(retry_count=0)) == ""
    assert focused_rewrite_instructions(_prior_row(retry_count=5)) == ""


class _FakeStore:
    def __init__(self, row):
        self.row = row
        self.updated = []
        self.ready = []

    def get_article(self, article_id):
        return self.row

    def get_channel(self, channel_id):
        return SimpleNamespace(id=channel_id, mode=ChannelMode.MONITORING)

    def update_article(self, article_id, **kwargs):
        self.updated.append((article_id, kwargs))

    def mark_ready(self, article_id):
        self.ready.append(article_id)


def test_prior_source_error_is_repaired_without_reselecting(monkeypatch):
    store = _FakeStore(_prior_row())
    engine = object.__new__(EditorialEngine)
    engine.store = store
    monkeypatch.setattr(editorial, "source_body_hard_limit", lambda *args, **kwargs: 800)
    monkeypatch.setattr(editorial, "_monitoring_limits", lambda *args: (150, 700, 800))
    calls = []

    def fake_final(self, channel, article, draft, **kwargs):
        calls.append(("trusted", kwargs.get("trusted_only"), kwargs.get("repair_focus")))
        return "Джерело не підтвердило чутку про подію. Перевірка інформації триває."

    def no_select(*args):
        pytest.fail("A focused source correction MUST NOT spend another selector call")

    monkeypatch.setattr(EditorialEngine, "_final_edit", fake_final)
    monkeypatch.setattr(EditorialEngine, "select", no_select)
    monkeypatch.setattr(
        source_integrity, "non_overridable_quality_issues",
        lambda channel, article, final: calls.append(("hard", final)) or (),
    )
    monkeypatch.setattr(
        editorial, "prepublish_quality_issues",
        lambda channel, article, final: calls.append(("soft", final)) or (),
    )
    result = engine.process_article(77337)
    assert result.decision == Decision.PUBLISH
    assert result.reason == "TARGETED_QA_REPAIR_FROM_SOURCE"
    assert store.ready == [77337]
    assert [x[0] for x in calls] == ["trusted", "hard", "soft"]
    assert calls[0][1] is True
    assert "спростування" in calls[0][2]
    assert store.updated[-1][1]["status_detail"] == "TARGETED_QA_REPAIR_FROM_ORIGINAL_SOURCE"


def test_failed_focused_edit_does_not_bypass_hard_qa(monkeypatch):
    store = _FakeStore(_prior_row())
    engine = object.__new__(EditorialEngine)
    engine.store = store
    monkeypatch.setattr(editorial, "source_body_hard_limit", lambda *args, **kwargs: 800)
    monkeypatch.setattr(editorial, "_monitoring_limits", lambda *args: (150, 700, 800))
    monkeypatch.setattr(EditorialEngine, "_final_edit", lambda *args, **kw: PRIOR)
    monkeypatch.setattr(source_integrity, "non_overridable_quality_issues", lambda *a: ("MONITORING_SOURCE_POLARITY_FLIP",))
    called = []
    monkeypatch.setattr(EditorialEngine, "select", lambda *a: called.append(True) or EditorialOutcome(Decision.REJECT, reason="fallback", fit_score=0))
    result = engine.process_article(77337)
    assert called and result.decision == Decision.REJECT
    assert not store.ready


def _seed_store(db):
    store = V2Store(db)
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(3,'Test','@test',1,'monitoring',?,?)",
            (stamp, stamp),
        )
        sid = con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(3,'page','Example','https://example.org',1,100)"
        ).lastrowid
        aid = con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,
                         canonical_source_url,raw_text,discovered_at,stage,decision)
               VALUES(3,?,'once','A','https://example.org/a','https://example.org/a',
                      'джерело',?,'READY','PUBLISH')""",
            (sid, stamp),
        ).lastrowid
    return store, int(aid)


def test_source_safety_retry_exhaustion_uses_factual_error_not_oversize(tmp_path: Path):
    store, aid = _seed_store(tmp_path/"db.sqlite3")
    assert store.requeue_quality_rewrite(
        aid, error_code="PREPUBLISH_SOURCE_SAFETY",
        detail="MONITORING_SOURCE_POLARITY_FLIP", max_attempts=2,
    ) == "QUALITY_REWRITE_QUEUED"
    assert store.requeue_quality_rewrite(
        aid, error_code="PREPUBLISH_SOURCE_SAFETY",
        detail="MONITORING_SOURCE_POLARITY_FLIP", max_attempts=2,
    ) == "QUALITY_BLOCKED"
    assert store.get_article(aid)["last_error_code"] == "SOURCE_FACT_QA_BLOCKED"


def test_specialist_scaledown_models_not_general_chat_while_manual_other_models_preserved(tmp_path: Path):
    assert not _chat_compatible_id("scaledown/summarize")
    assert not _chat_compatible_id("scaledown/extract")
    assert _chat_compatible_id("openai/gpt-oss-120b")
    assert _chat_compatible_id("custom/summarize-tools-chat")
    gateway = AIGateway(V2Store(tmp_path/"router.sqlite3"))
    cfg = SecretConfig(
        ai_mode="openrouter", openrouter_enabled=True,
        openrouter_api_key="sk-or-test",
        openrouter_models=["scaledown/summarize", "openai/gpt-oss-120b", "scaledown/extract"],
    )
    slots = gateway._openrouter_task_slots(cfg, purpose="monitoring_selector", prompt_chars=2800, max_output_tokens=300)
    assert [slot.model for slot in slots] == ["openai/gpt-oss-120b"]
    items = _parse({"data": [
        {"id":"scaledown/summarize","name":"ScaleDown","architecture":{"output_modalities":["text"]},"pricing":{"prompt":"0","completion":"0"},"context_length":64000},
        {"id":"vendor/general-chat","name":"General Chat","architecture":{"output_modalities":["text"]},"pricing":{"prompt":"0","completion":"0"},"context_length":64000},
    ]})
    assert [x.id for x in items] == ["vendor/general-chat"]
