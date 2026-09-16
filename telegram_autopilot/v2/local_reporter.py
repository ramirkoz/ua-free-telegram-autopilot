from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..secrets_store import load_secrets
from ..telegram import TelegramError, _request, send_text
from . import V2_VERSION
from .fileio import atomic_write_json


class LocalTelegramReporter:
    """Periodic local status reporting without a remote supervisor agent.

    The reporter only reads the live snapshot produced by the local Supervisor and
    sends a compact status message to the already configured private Telegram chat.
    It never reads remote agent reports, never creates review requests and never
    consumes remote commands. The separate signed updater remains unchanged.
    """

    TARGET_NAME = "telegram_target.json"
    STATE_NAME = "state.json"
    LATEST_NAME = "latest.json"

    def __init__(self, *, root: Path, interval_seconds: int = 3600) -> None:
        self.root = Path(root) / "local_reports"
        self.root.mkdir(parents=True, exist_ok=True)
        self.interval_seconds = max(300, int(interval_seconds))
        self.state_path = self.root / self.STATE_NAME
        self.latest_path = self.root / self.LATEST_NAME
        self.target_path = self.root / self.TARGET_NAME
        self.legacy_target_path = Path(root) / "agent" / "agent_telegram_target.json"
        self.legacy_bridge_state_path = Path(root) / "agent" / "agent_telegram_bridge_state.json"
        self._state = self._read_json(self.state_path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return dict(value) if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _atomic(path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, payload)

    @staticmethod
    def _choose_bot_token() -> str:
        try:
            secrets = load_secrets()
        except Exception:
            return ""
        default = str(getattr(secrets, "default_telegram_bot_token", "") or "").strip()
        if default:
            return default
        tokens = {
            str(value or "").strip()
            for value in dict(getattr(secrets, "channel_bot_tokens", {}) or {}).values()
            if str(value or "").strip()
        }
        return next(iter(tokens)) if len(tokens) == 1 else ""

    @staticmethod
    def _private_chat_candidates(token: str) -> list[str]:
        result = _request(
            token,
            "getUpdates",
            {
                "limit": "100",
                "timeout": "0",
                "allowed_updates": json.dumps(["message"], ensure_ascii=False, separators=(",", ":")),
            },
            timeout=20.0,
        )
        chats: list[str] = []
        seen: set[str] = set()
        for update in result if isinstance(result, list) else []:
            if not isinstance(update, dict):
                continue
            message = update.get("message")
            chat = message.get("chat") if isinstance(message, dict) else None
            if not isinstance(chat, dict) or str(chat.get("type") or "") != "private":
                continue
            chat_id = str(chat.get("id") or "").strip()
            if chat_id and chat_id not in seen:
                seen.add(chat_id)
                chats.append(chat_id)
        return chats

    def _resolve_chat_id(self, token: str) -> str:
        for env_name in ("AUTOPILOT_LOCAL_TELEGRAM_CHAT_ID", "AUTOPILOT_AGENT_TELEGRAM_CHAT_ID"):
            value = str(os.environ.get(env_name) or "").strip()
            if value:
                return value

        for path in (self.target_path, self.legacy_target_path):
            value = str(self._read_json(path).get("chat_id") or "").strip()
            if value:
                if path != self.target_path:
                    self._atomic(self.target_path, {"chat_id": value, "source": "legacy_local_target"})
                return value

        cached = str(self._state.get("resolved_chat_id") or "").strip()
        if cached:
            return cached
        legacy_cached = str(self._read_json(self.legacy_bridge_state_path).get("resolved_chat_id") or "").strip()
        if legacy_cached:
            self._state["resolved_chat_id"] = legacy_cached
            self._atomic(self.state_path, self._state)
            return legacy_cached

        chats = self._private_chat_candidates(token)
        if len(chats) == 1:
            resolved = chats[0]
            self._state["resolved_chat_id"] = resolved
            self._atomic(self.target_path, {"chat_id": resolved, "source": "bot_getUpdates_single_private_chat"})
            self._atomic(self.state_path, self._state)
            return resolved
        return ""

    @staticmethod
    def build_report(snapshot: dict[str, Any], incidents: list[Any]) -> dict[str, Any]:
        queue = dict(snapshot.get("queue") or {})
        ai = dict(snapshot.get("ai") or {})
        database = dict(snapshot.get("database") or {})
        channel_stats = dict(snapshot.get("channel_stats") or {})
        incident_codes = [str(getattr(item, "code", "UNKNOWN")) for item in incidents]
        published_60m = sum(int(dict(row or {}).get("published_60m") or 0) for row in channel_stats.values())
        jobs_done_30m = sum(int(dict(row or {}).get("jobs_done_30m") or 0) for row in channel_stats.values())
        oldest_due_age_seconds = max(
            [int(dict(row or {}).get("oldest_due_age_seconds") or 0) for row in channel_stats.values()] or [0]
        )
        slow_sources: list[dict[str, Any]] = []
        channel_lines: list[dict[str, Any]] = []
        for row in channel_stats.values():
            item = dict(row or {})
            channel_lines.append({
                "name": str(item.get("name") or "?"),
                "due": int(item.get("due_jobs") or 0),
                "done_30m": int(item.get("jobs_done_30m") or 0),
                "published_60m": int(item.get("published_60m") or 0),
            })
            for source in list(item.get("slow_sources") or []):
                value = dict(source or {})
                value["channel"] = str(item.get("name") or "?")
                slow_sources.append(value)
        slow_sources.sort(key=lambda item: int(item.get("duration_ms") or 0), reverse=True)
        provider_states = [
            f"{str(item.get('provider') or '?')}={str(item.get('state') or '?')}"
            for item in list(snapshot.get("providers") or [])
        ]
        return {
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "version": str(snapshot.get("version") or V2_VERSION),
            "lifecycle": str(snapshot.get("lifecycle_state") or "UNKNOWN"),
            "runtime_running": bool(snapshot.get("runtime_running")),
            "workers_alive": int(snapshot.get("live_workers") or 0),
            "collectors_alive": int(snapshot.get("live_collectors") or 0),
            "database_ok": bool(database.get("ok")),
            "ai_state": str(ai.get("state") or "UNKNOWN"),
            "ai_healthy": int(ai.get("healthy") or 0),
            "ai_total": int(ai.get("total") or 0),
            "ai_blocked": int(ai.get("blocked_jobs") or 0),
            "provider_states": provider_states,
            "queue_active": int(queue.get("active") or 0),
            "queue_due": int(queue.get("due") or 0),
            "oldest_due_age_minutes": oldest_due_age_seconds // 60,
            "jobs_done_30m": jobs_done_30m,
            "published_today": int(queue.get("published_today") or 0),
            "published_60m": published_60m,
            "channels": channel_lines,
            "slow_sources": slow_sources[:3],
            "incidents": incident_codes,
        }

    @staticmethod
    def format_message(report: dict[str, Any]) -> str:
        incidents = list(report.get("incidents") or [])
        status = "ПРОБЛЕМА" if incidents else "OK"
        channels = "; ".join(
            f"{row.get('name')}: due {row.get('due')}, done/30 {row.get('done_30m')}, pub/60 {row.get('published_60m')}"
            for row in list(report.get("channels") or [])
        ) or "немає"
        slow = ", ".join(
            f"{item.get('name') or '?'} {int(item.get('duration_ms') or 0)//1000}s"
            for item in list(report.get("slow_sources") or [])
            if int(item.get("duration_ms") or 0) >= 30000
        ) or "0"
        providers = ", ".join(list(report.get("provider_states") or [])) or "немає"
        return (
            "Autopilot · локальний звіт\n"
            f"Статус: {status} · {report.get('version')}\n"
            f"Runtime: {report.get('lifecycle')}; workers {report.get('workers_alive')}/3; "
            f"collectors {report.get('collectors_alive')}/3; БД={'OK' if report.get('database_ok') else 'ПОМИЛКА'}\n"
            f"AI: {report.get('ai_state')} · {report.get('ai_healthy')}/{report.get('ai_total')} healthy; "
            f"blocked {report.get('ai_blocked')} · {providers}\n"
            f"Черга: active {report.get('queue_active')}; due {report.get('queue_due')}; "
            f"oldest {report.get('oldest_due_age_minutes')} хв; done/30 {report.get('jobs_done_30m')}\n"
            f"Публікації: сьогодні {report.get('published_today')}; за 60 хв {report.get('published_60m')}\n"
            f"Канали: {channels}\n"
            f"Повільні джерела: {slow}\n"
            f"Інциденти: {', '.join(incidents) if incidents else '0'}"
        )[:4096]

    def observe(self, snapshot: dict[str, Any], incidents: list[Any], *, force: bool = False) -> dict[str, Any]:
        now = time.time()
        report = self.build_report(snapshot, incidents)
        self._atomic(self.latest_path, report)

        current_incidents = list(report.get("incidents") or [])
        previous_incidents = list(self._state.get("last_incidents") or [])
        incident_changed = current_incidents != previous_incidents
        last_sent = float(self._state.get("last_sent_epoch") or 0.0)
        due = not last_sent or now - last_sent >= self.interval_seconds
        if not force and not due and not incident_changed:
            return {"status": "not_due", "last_sent_at": self._state.get("last_sent_at")}

        token = self._choose_bot_token()
        if not token:
            return {"status": "bot_token_missing"}
        try:
            chat_id = self._resolve_chat_id(token)
        except TelegramError as exc:
            return {"status": "target_discovery_error", "error": str(exc)[:240]}
        except Exception as exc:
            return {"status": "target_discovery_error", "error": f"{type(exc).__name__}: {exc}"[:240]}
        if not chat_id:
            return {"status": "target_missing"}

        try:
            result = send_text(token, chat_id, self.format_message(report), timeout=30.0)
        except TelegramError as exc:
            return {"status": "send_error", "error": str(exc)[:240]}
        except Exception as exc:
            return {"status": "send_error", "error": f"{type(exc).__name__}: {exc}"[:240]}

        sent_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        self._state.update(
            {
                "last_sent_epoch": now,
                "last_sent_at": sent_at,
                "last_incidents": current_incidents,
                "resolved_chat_id": chat_id,
                "last_message_id": str(getattr(result, "message_id", "") or ""),
            }
        )
        self._atomic(self.state_path, self._state)
        return {"status": "sent", "last_sent_at": sent_at, "message_id": self._state["last_message_id"]}

    def status(self) -> dict[str, Any]:
        return {
            "mode": "local_only",
            "interval_seconds": self.interval_seconds,
            "last_sent_at": self._state.get("last_sent_at"),
            "remote_agent": False,
            "remote_commands": False,
            "latest_path": str(self.latest_path),
        }
