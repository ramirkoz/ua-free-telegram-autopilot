from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..secrets_store import load_secrets
from ..telegram import TelegramError, _request, send_text
from .advanced_supervisor import AdvancedSupervisorService
from .agent_feed import AgentFeed
from .agent_report_format import format_agent_report
from .fileio import atomic_copy, atomic_write_json
from .loghub import event
from .supervisor import SupervisorConfig
from .update_protocol import UpdateProtocol


CANONICAL_LIVE_FEED_NAME = "UA_FREE_AUTOPILOT_LIVE_CURRENT"
LEGACY_LIVE_FEED_NAMES = (
    "SUPERVISOR FEED — Autopilot V2 LIVE",
    "SUPERVISOR FEED - Autopilot V2 LIVE",
)
LIVE_FEED_NAMES = (CANONICAL_LIVE_FEED_NAME, *LEGACY_LIVE_FEED_NAMES)


class _ProductionAgentFeed(AgentFeed):
    """Agent feed using unique temp files and lock-tolerant atomic replacement.

    RC37 consumes one Drive-side ``agent_telegram_report.json`` at a time and
    forwards a compact Ukrainian status to Telegram. Delivery is replay-safe: the
    local state and ``agent_telegram_ack.json`` both key off ``report_id``. Reports
    may carry a legacy preformatted ``message`` or the structured agent contract.
    """

    REPORT_NAME = "agent_telegram_report.json"
    ACK_NAME = "agent_telegram_ack.json"
    TARGET_NAME = "agent_telegram_target.json"
    BRIDGE_STATE_NAME = "agent_telegram_bridge_state.json"
    RETRY_SECONDS = 300.0

    def __init__(self, *, root: Path, store: Any, config_getter) -> None:
        super().__init__(root=root, store=store, config_getter=config_getter)
        self.telegram_ack_path = self.root / self.ACK_NAME
        self.telegram_target_path = self.root / self.TARGET_NAME
        self.telegram_bridge_state_path = self.root / self.BRIDGE_STATE_NAME
        self._telegram_bridge_state = self._read_json(self.telegram_bridge_state_path)

    @staticmethod
    def _atomic(path: Path, value: dict[str, Any]) -> None:
        atomic_write_json(path, value)

    def _mirror(self, path: Path) -> None:
        raw = str(getattr(self.config_getter(), "mirror_dir", "") or "").strip()
        if not raw:
            return
        try:
            root = Path(raw).expanduser()
            root.mkdir(parents=True, exist_ok=True)
            atomic_copy(path, root / path.name)
        except OSError:
            pass

    @staticmethod
    def _choose_bot_token(secrets: Any) -> str:
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
            if not isinstance(message, dict):
                continue
            chat = message.get("chat")
            if not isinstance(chat, dict) or str(chat.get("type") or "") != "private":
                continue
            chat_id = str(chat.get("id") or "").strip()
            if chat_id and chat_id not in seen:
                seen.add(chat_id)
                chats.append(chat_id)
        return chats

    def _read_target_file(self, path: Path) -> str:
        data = self._read_json(path)
        return str(data.get("chat_id") or "").strip()

    def _resolve_chat_id(self, report: dict[str, Any], token: str, mirror_dir: Path) -> str:
        explicit = str(report.get("chat_id") or "").strip()
        if explicit:
            return explicit

        env = str(os.environ.get("AUTOPILOT_AGENT_TELEGRAM_CHAT_ID") or "").strip()
        if env:
            return env

        local = self._read_target_file(self.telegram_target_path)
        if local:
            return local

        remote = self._read_target_file(mirror_dir / self.TARGET_NAME)
        if remote:
            self._atomic(self.telegram_target_path, {"chat_id": remote, "source": "drive"})
            return remote

        cached = str(self._telegram_bridge_state.get("resolved_chat_id") or "").strip()
        if cached:
            return cached

        chats = self._private_chat_candidates(token)
        if len(chats) == 1:
            resolved = chats[0]
            self._telegram_bridge_state["resolved_chat_id"] = resolved
            self._telegram_bridge_state["resolved_chat_source"] = "bot_getUpdates_single_private_chat"
            self._atomic(self.telegram_bridge_state_path, self._telegram_bridge_state)
            return resolved
        return ""

    def _bridge_retry_due(self, report_id: str) -> bool:
        previous_id = str(self._telegram_bridge_state.get("last_attempt_report_id") or "")
        previous_at = float(self._telegram_bridge_state.get("last_attempt_epoch") or 0.0)
        if previous_id != report_id:
            return True
        return time.time() - previous_at >= self.RETRY_SECONDS

    def _record_bridge_attempt(self, report_id: str, *, status: str, detail: str = "") -> None:
        self._telegram_bridge_state.update(
            {
                "last_attempt_report_id": report_id,
                "last_attempt_epoch": time.time(),
                "last_attempt_status": status,
                "last_attempt_detail": str(detail or "")[:800],
            }
        )
        self._atomic(self.telegram_bridge_state_path, self._telegram_bridge_state)

    def _consume_telegram_report(self) -> str:
        raw = str(getattr(self.config_getter(), "mirror_dir", "") or "").strip()
        if not raw:
            return "NO_MIRROR"
        mirror_dir = Path(raw).expanduser()
        report_path = mirror_dir / self.REPORT_NAME
        if not report_path.is_file():
            return "NO_REPORT"

        report = self._read_json(report_path)
        report_id = str(report.get("report_id") or "").strip()
        message = str(report.get("message") or "").strip()
        if not message and report_id:
            message = format_agent_report(report).strip()
        if not report_id or not message:
            return "INVALID_REPORT"
        if len(message) > 3900:
            self._record_bridge_attempt(report_id, status="INVALID_REPORT", detail="message exceeds Telegram safe limit")
            return "INVALID_REPORT"

        last_sent = str(self._telegram_bridge_state.get("last_sent_report_id") or "")
        if last_sent == report_id:
            if self.telegram_ack_path.is_file():
                self._mirror(self.telegram_ack_path)
            return "ALREADY_SENT"

        remote_ack = self._read_json(mirror_dir / self.ACK_NAME)
        if str(remote_ack.get("report_id") or "") == report_id and str(remote_ack.get("status") or "") == "sent":
            self._telegram_bridge_state["last_sent_report_id"] = report_id
            self._telegram_bridge_state["last_sent_at"] = str(remote_ack.get("sent_at") or "")
            self._atomic(self.telegram_bridge_state_path, self._telegram_bridge_state)
            return "ALREADY_ACKED"

        if not self._bridge_retry_due(report_id):
            return "RETRY_COOLDOWN"

        try:
            secrets = load_secrets()
        except Exception as exc:
            self._record_bridge_attempt(report_id, status="SECRETS_ERROR", detail=str(exc))
            return "SECRETS_ERROR"

        token = self._choose_bot_token(secrets)
        if not token:
            self._record_bridge_attempt(report_id, status="BOT_TOKEN_MISSING")
            return "BOT_TOKEN_MISSING"

        try:
            chat_id = self._resolve_chat_id(report, token, mirror_dir)
        except TelegramError as exc:
            self._record_bridge_attempt(report_id, status="TARGET_DISCOVERY_ERROR", detail=str(exc))
            return "TARGET_DISCOVERY_ERROR"
        except Exception as exc:
            self._record_bridge_attempt(report_id, status="TARGET_DISCOVERY_ERROR", detail=str(exc))
            return "TARGET_DISCOVERY_ERROR"

        if not chat_id:
            self._record_bridge_attempt(
                report_id,
                status="TARGET_MISSING",
                detail="Set AUTOPILOT_AGENT_TELEGRAM_CHAT_ID, agent_telegram_target.json, report.chat_id, or message the bot from one private chat.",
            )
            return "TARGET_MISSING"

        self._record_bridge_attempt(report_id, status="SENDING")
        try:
            result = send_text(token, chat_id, message, timeout=30.0)
        except TelegramError as exc:
            self._record_bridge_attempt(report_id, status="SEND_ERROR", detail=str(exc))
            return "SEND_ERROR"
        except Exception as exc:
            self._record_bridge_attempt(report_id, status="SEND_ERROR", detail=str(exc))
            return "SEND_ERROR"

        ack = {
            "report_id": report_id,
            "status": "sent",
            "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "message_id": str(getattr(result, "message_id", "") or ""),
            "version": str(report.get("version") or ""),
            "md_report_name": str(report.get("md_report_name") or ""),
        }
        self._atomic(self.telegram_ack_path, ack)
        self._mirror(self.telegram_ack_path)
        self._telegram_bridge_state.update(
            {
                "last_sent_report_id": report_id,
                "last_sent_at": ack["sent_at"],
                "last_attempt_report_id": report_id,
                "last_attempt_epoch": time.time(),
                "last_attempt_status": "SENT",
                "last_attempt_detail": "",
                "resolved_chat_id": chat_id,
            }
        )
        self._atomic(self.telegram_bridge_state_path, self._telegram_bridge_state)
        event("supervisor", "agent telegram report sent", report_id=report_id, message_id=ack["message_id"])
        return "SENT"

    def observe(self, snapshot: dict[str, Any], incidents: list[Any], update_status: dict[str, Any] | None = None) -> dict[str, Any]:
        result = super().observe(snapshot, incidents, update_status)
        try:
            result["telegram_report_bridge"] = self._consume_telegram_report()
        except Exception as exc:
            event("supervisor", "agent telegram bridge tick failed", level=30, detail=str(exc)[:800])
            result["telegram_report_bridge"] = "ERROR"
        return result


class _ProductionUpdateProtocol(UpdateProtocol):
    """Update status writer hardened for Windows and synced folders."""

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, payload)

    def mirror_status(self, mirror_dir: str) -> None:
        raw = str(mirror_dir or "").strip()
        if not raw:
            return
        root = Path(raw)
        try:
            root.mkdir(parents=True, exist_ok=True)
            for source, name in (
                (self.state_path, "update_status.json"),
                (self.result_path, "update_result.json"),
                (self.ready_path, "update_ready.json"),
            ):
                if source.is_file():
                    atomic_copy(source, root / name)
        except Exception:
            # Remote mirror failure must never take down the local runtime.
            return


class ProductionSupervisorService(AdvancedSupervisorService):
    """Production supervisor with one LIVE feed and Windows-safe status writes."""

    def __init__(self, store, runtime, logs_dir):
        super().__init__(store, runtime, logs_dir)

        # AdvancedSupervisor constructs these before its worker thread starts.
        # Replace them now so all production writes use the hardened primitives.
        self.update_protocol = _ProductionUpdateProtocol()
        self.agent = _ProductionAgentFeed(
            root=self.root,
            store=self.store,
            config_getter=lambda: self.config,
        )

        live = self._discover_live_mirror_dir()
        if live and str(self.config.mirror_dir or "").strip() != live:
            cfg = SupervisorConfig(**{**asdict(self.config), "mirror_dir": live}).normalized()
            self.save_config(cfg)
        self._status_sequence = 0

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        atomic_write_json(path, value)

    def _mirror_file(self, source: Path, name: str) -> None:
        raw = self.config.mirror_dir.strip()
        if not raw:
            return
        try:
            target_dir = Path(raw).expanduser()
            target_dir.mkdir(parents=True, exist_ok=True)
            atomic_copy(source, target_dir / name)
            from .storage import now_iso
            self._mirror_last_ok_at = now_iso()
            self._mirror_last_error = ""
        except Exception as exc:
            self._mirror_last_error = f"{type(exc).__name__}: {exc}"[:800]

    @staticmethod
    def _discover_live_mirror_dir() -> str:
        env = str(os.environ.get("AUTOPILOT_SUPERVISOR_MIRROR") or "").strip()
        if env:
            path = Path(env).expanduser()
            if path.is_dir() and path.name in LIVE_FEED_NAMES:
                return str(path)

        home = Path.home()
        roots = [home, home / "Google Drive", home / "GoogleDrive"]
        if os.name == "nt":
            roots.extend(Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ")

        canonical: list[Path] = []
        legacy: list[Path] = []
        for root in roots:
            try:
                if not root.exists():
                    continue
            except OSError:
                continue
            for drive_root in (root, root / "My Drive", root / "Мій диск"):
                canonical.append(drive_root / CANONICAL_LIVE_FEED_NAME)
                for name in LEGACY_LIVE_FEED_NAMES:
                    legacy.append(drive_root / name)

        def existing(paths: list[Path]) -> list[Path]:
            out: list[Path] = []
            for path in paths:
                try:
                    if path.is_dir():
                        out.append(path)
                except OSError:
                    pass
            out.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0.0, reverse=True)
            return out

        # RC63: one canonical telemetry folder wins unconditionally.  Legacy
        # folders are migration fallback only; stale duplicate folders must never
        # outrank the canonical target merely because they contain old status files.
        primary = existing(canonical)
        if primary:
            return str(primary[0])
        fallback = existing(legacy)
        return str(fallback[0]) if fallback else ""

    def build_snapshot(self) -> dict[str, Any]:
        snapshot = super().build_snapshot()
        runtime_running = bool(snapshot.get("runtime_running"))
        stop_requested = bool(snapshot.get("runtime_stop_requested"))
        live_threads = int(snapshot.get("live_workers") or 0) + int(snapshot.get("live_collectors") or 0)

        if runtime_running and live_threads > 0 and not stop_requested:
            snapshot["expected_running"] = True
            lifecycle = "RUNNING"
        elif stop_requested and live_threads > 0:
            lifecycle = "STOPPING"
        elif live_threads <= 0:
            lifecycle = "STOPPED"
        else:
            lifecycle = "STARTING"
        snapshot["lifecycle_state"] = lifecycle

        self._status_sequence += 1
        snapshot["transport"] = {
            "feed": CANONICAL_LIVE_FEED_NAME,
            "sequence": self._status_sequence,
            "local_mirror_configured": bool(str(self.config.mirror_dir or "").strip()),
            "local_mirror_last_ok_at": self._mirror_last_ok_at,
            "local_mirror_last_error": self._mirror_last_error,
        }
        return snapshot
