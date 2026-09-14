from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import telegram_autopilot.v2.production_supervisor as production_supervisor
from telegram_autopilot.v2.production_supervisor import _ProductionAgentFeed


def _feed(tmp_path: Path, mirror: Path) -> _ProductionAgentFeed:
    cfg = SimpleNamespace(mirror_dir=str(mirror))
    return _ProductionAgentFeed(root=tmp_path / "supervisor", store=object(), config_getter=lambda: cfg)


def _write_report(mirror: Path, report_id: str = "r-1", message: str = "Перевірка агента\nСтатус: OK") -> None:
    (mirror / "agent_telegram_report.json").write_text(
        json.dumps(
            {
                "report_id": report_id,
                "generated_at": "2026-09-14T18:45:00+03:00",
                "version": "2.0.0-rc30",
                "severity": "INFO",
                "status": "OK",
                "message": message,
                "md_report_name": f"{report_id}.md",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_agent_report_is_sent_once_and_acknowledged(tmp_path, monkeypatch) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    _write_report(mirror)
    feed = _feed(tmp_path, mirror)

    monkeypatch.setenv("AUTOPILOT_AGENT_TELEGRAM_CHAT_ID", "123456")
    monkeypatch.setattr(
        production_supervisor,
        "load_secrets",
        lambda: SimpleNamespace(default_telegram_bot_token="token", channel_bot_tokens={}),
    )
    calls: list[tuple[str, str, str]] = []

    def fake_send(token: str, chat_id: str, text: str, **_kwargs):
        calls.append((token, chat_id, text))
        return SimpleNamespace(message_id="77")

    monkeypatch.setattr(production_supervisor, "send_text", fake_send)

    assert feed._consume_telegram_report() == "SENT"
    assert feed._consume_telegram_report() == "ALREADY_SENT"
    assert len(calls) == 1
    assert calls[0][0] == "token"
    assert calls[0][1] == "123456"

    ack = json.loads((mirror / "agent_telegram_ack.json").read_text(encoding="utf-8"))
    assert ack["report_id"] == "r-1"
    assert ack["status"] == "sent"
    assert ack["message_id"] == "77"

    restarted = _feed(tmp_path, mirror)
    monkeypatch.setattr(production_supervisor, "send_text", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("duplicate send")))
    assert restarted._consume_telegram_report() in {"ALREADY_SENT", "ALREADY_ACKED"}


def test_single_private_bot_chat_is_auto_discovered(tmp_path, monkeypatch) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    _write_report(mirror, report_id="r-2")
    feed = _feed(tmp_path, mirror)

    monkeypatch.delenv("AUTOPILOT_AGENT_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(
        production_supervisor,
        "load_secrets",
        lambda: SimpleNamespace(default_telegram_bot_token="token", channel_bot_tokens={}),
    )
    monkeypatch.setattr(
        production_supervisor,
        "_request",
        lambda *_a, **_k: [
            {"update_id": 1, "message": {"chat": {"id": 9001, "type": "private"}}},
            {"update_id": 2, "message": {"chat": {"id": 9001, "type": "private"}}},
        ],
    )
    sent: list[str] = []
    monkeypatch.setattr(
        production_supervisor,
        "send_text",
        lambda _token, chat_id, _text, **_kwargs: (sent.append(str(chat_id)) or SimpleNamespace(message_id="88")),
    )

    assert feed._consume_telegram_report() == "SENT"
    assert sent == ["9001"]


def test_multiple_private_chats_do_not_guess_target(tmp_path, monkeypatch) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    _write_report(mirror, report_id="r-3")
    feed = _feed(tmp_path, mirror)

    monkeypatch.delenv("AUTOPILOT_AGENT_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(
        production_supervisor,
        "load_secrets",
        lambda: SimpleNamespace(default_telegram_bot_token="token", channel_bot_tokens={}),
    )
    monkeypatch.setattr(
        production_supervisor,
        "_request",
        lambda *_a, **_k: [
            {"update_id": 1, "message": {"chat": {"id": 100, "type": "private"}}},
            {"update_id": 2, "message": {"chat": {"id": 200, "type": "private"}}},
        ],
    )
    monkeypatch.setattr(
        production_supervisor,
        "send_text",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not guess chat target")),
    )

    assert feed._consume_telegram_report() == "TARGET_MISSING"
    assert not (mirror / "agent_telegram_ack.json").exists()


def test_single_unique_channel_token_can_be_used_as_bridge_token(tmp_path) -> None:
    feed = _feed(tmp_path, tmp_path)
    secrets = SimpleNamespace(default_telegram_bot_token="", channel_bot_tokens={"1": "same", "2": "same"})
    assert feed._choose_bot_token(secrets) == "same"
    ambiguous = SimpleNamespace(default_telegram_bot_token="", channel_bot_tokens={"1": "a", "2": "b"})
    assert feed._choose_bot_token(ambiguous) == ""
