from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..paths import data_dir, runtime_dir
from . import V2_VERSION
from .loghub import event

_REPO = "ramirkoz/ua-free-telegram-autopilot"
_VERSION_RE = re.compile(r"^2\.0\.0-rc(?P<rc>[1-9]\d*)$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
UPDATE_RUNTIME_ABI = "py312-v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _rc_number(version: str) -> int:
    match = _VERSION_RE.fullmatch(str(version or "").strip())
    return int(match.group("rc")) if match else -1


@dataclass(frozen=True, slots=True)
class UpdateRequest:
    request_id: str
    target_version: str
    sha256: str
    created_at: str
    source: str = "agent"

    @property
    def asset_name(self) -> str:
        return f"UA_FREE_Telegram_Autopilot_v{self.target_version}_Update.zip"

    @property
    def release_url(self) -> str:
        return (
            f"https://github.com/{_REPO}/releases/download/"
            f"v{self.target_version}/{self.asset_name}"
        )


class UpdateProtocol:
    """Deterministic file protocol between an external agent and the local updater.

    The agent may request only a version + SHA256. It cannot submit shell commands,
    file paths or executable URLs. The local updater constructs the GitHub URL from
    a fixed repository, verifies the hash, stops cleanly and applies the bundle.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or (data_dir() / "updates"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.request_path = self.root / "request.json"
        self.ready_path = self.root / "ready.json"
        self.result_path = self.root / "result.json"
        self.health_path = self.root / "startup_healthy.json"
        self.state_path = self.root / "state.json"
        self._lock = threading.RLock()

    @staticmethod
    def validate_request(data: dict[str, Any]) -> UpdateRequest:
        target = str(data.get("target_version") or "").strip()
        sha256 = str(data.get("sha256") or "").strip().casefold()
        request_id = str(data.get("request_id") or "").strip() or uuid.uuid4().hex
        created_at = str(data.get("created_at") or "").strip() or _now_iso()
        source = str(data.get("source") or "agent").strip()[:80] or "agent"
        if _rc_number(target) < 0:
            raise ValueError("UPDATE_VERSION_INVALID")
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError("UPDATE_SHA256_INVALID")
        if not re.fullmatch(r"[A-Za-z0-9._-]{8,96}", request_id):
            raise ValueError("UPDATE_REQUEST_ID_INVALID")
        return UpdateRequest(request_id, target, sha256, created_at, source)

    def load_request(self, path: Path | None = None) -> UpdateRequest | None:
        target = Path(path or self.request_path)
        try:
            data = json.loads(target.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return None
        except Exception as exc:
            raise ValueError(f"UPDATE_REQUEST_JSON_INVALID: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("UPDATE_REQUEST_JSON_INVALID")
        return self.validate_request(data)

    def request_already_terminal(self, request: UpdateRequest) -> bool:
        try:
            previous = json.loads(self.result_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return bool(
            isinstance(previous, dict)
            and previous.get("request_id") == request.request_id
            and str(previous.get("state") or "") in {"HEALTHY", "ROLLBACK_OK", "REJECTED", "FAILED"}
        )

    def _mirror_request_candidates(self, mirror: Path) -> list[tuple[UpdateRequest, Path, float]]:
        """Read every synced request variant and keep only valid non-terminal ones.

        Google Drive can preserve two cloud files with the same display name and the
        desktop client may materialize one of them as ``update_request (1).json`` or
        another suffix.  The updater must not depend on whichever duplicate wins the
        filename lottery.  Validation still applies to every candidate.
        """
        candidates: list[tuple[UpdateRequest, Path, float]] = []
        try:
            paths = sorted(mirror.glob("update_request*.json"), key=lambda item: item.name.casefold())
        except OSError:
            return candidates
        for source in paths:
            if not source.is_file():
                continue
            try:
                request = self.load_request(source)
            except ValueError as exc:
                event("update", "ignored invalid mirror update request", level=30, path=str(source), detail=str(exc)[:500])
                continue
            if request is None or self.request_already_terminal(request):
                continue
            # RC54: stale Drive requests must stay invisible after a newer runtime is
            # installed. The single result.json only remembers the latest request, so
            # request_already_terminal() alone cannot suppress older duplicates forever.
            if _rc_number(request.target_version) <= _rc_number(V2_VERSION):
                continue
            try:
                mtime = float(source.stat().st_mtime)
            except OSError:
                mtime = 0.0
            candidates.append((request, source, mtime))
        return candidates

    def accept_mirror_request(self, mirror_dir: str) -> UpdateRequest | None:
        raw = str(mirror_dir or "").strip()
        if not raw:
            return None
        mirror = Path(raw)
        candidates = self._mirror_request_candidates(mirror)
        if not candidates:
            return None

        # Highest target version wins.  For equal targets prefer the newest
        # created_at/mtime, then the canonical filename.  Thus a stale RC34 exact
        # file can never hide a newer RC39 duplicate synced under another suffix.
        request, source, _mtime = max(
            candidates,
            key=lambda item: (
                _rc_number(item[0].target_version),
                str(item[0].created_at or ""),
                float(item[2]),
                1 if item[1].name.casefold() == "update_request.json" else 0,
            ),
        )
        with self._lock:
            current = self.load_request()
            if current and current.request_id == request.request_id:
                return current
            self._atomic_json(self.request_path, asdict(request))
            detail = f"mirror={source.name}"
            self.write_state("REQUESTED", request=request, detail=detail)
            if source.name.casefold() != "update_request.json":
                event("update", "accepted noncanonical Drive request duplicate", target_version=request.target_version, path=str(source))
        return request

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
                if not source.is_file():
                    continue
                target = root / name
                temp = target.with_name(target.name + ".tmp")
                shutil.copy2(source, temp)
                os.replace(temp, target)
        except Exception as exc:
            event("update", "update mirror failed", level=30, path=raw, detail=str(exc)[:800])

    def request_is_newer(self, request: UpdateRequest) -> bool:
        return _rc_number(request.target_version) > _rc_number(V2_VERSION)

    def write_ready(self, request: UpdateRequest, *, pid: int, detail: str = "") -> None:
        self._atomic_json(
            self.ready_path,
            {
                "state": "READY_FOR_UPDATE",
                "request_id": request.request_id,
                "from_version": V2_VERSION,
                "target_version": request.target_version,
                "pid": int(pid),
                "generated_at": _now_iso(),
                "detail": str(detail)[:1200],
            },
        )
        self.write_state("READY_FOR_UPDATE", request=request, detail=detail)

    def write_result(self, state: str, *, request: UpdateRequest | None = None, detail: str = "", **extra: Any) -> None:
        payload: dict[str, Any] = {
            "state": str(state),
            "generated_at": _now_iso(),
            "detail": str(detail)[:2400],
        }
        if request is not None:
            payload.update({
                "request_id": request.request_id,
                "from_version": V2_VERSION,
                "target_version": request.target_version,
            })
        payload.update(extra)
        self._atomic_json(self.result_path, payload)
        self.write_state(str(state), request=request, detail=detail, **extra)

    def write_state(self, state: str, *, request: UpdateRequest | None = None, detail: str = "", **extra: Any) -> None:
        payload: dict[str, Any] = {
            "state": str(state),
            "version": V2_VERSION,
            "generated_at": _now_iso(),
            "detail": str(detail)[:1200],
        }
        if request is not None:
            payload["request_id"] = request.request_id
            payload["target_version"] = request.target_version
        payload.update(extra)
        self._atomic_json(self.state_path, payload)

    def mark_startup_healthy(self, version: str = V2_VERSION) -> None:
        self._atomic_json(
            self.health_path,
            {"version": str(version), "pid": os.getpid(), "generated_at": _now_iso(), "healthy": True},
        )
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        if isinstance(state, dict) and state.get("state") in {"APPLIED", "STARTING_NEW_VERSION"}:
            state.update({"state": "HEALTHY", "version": str(version), "generated_at": _now_iso()})
            self._atomic_json(self.state_path, state)

    def clear_health_marker(self) -> None:
        try:
            self.health_path.unlink()
        except FileNotFoundError:
            pass

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"current_version": V2_VERSION}
        for key, path in (("state", self.state_path), ("request", self.request_path), ("result", self.result_path)):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(value, dict):
                out[key] = value
        return out

    def database_backup_path(self, request: UpdateRequest) -> Path:
        return self.root / "db_backups" / request.request_id / "telegram_autopilot_v2.sqlite3"

    def backup_database(self, store: Any, request: UpdateRequest) -> Path:
        target = self.database_backup_path(request)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        with store.connect() as source:
            destination = sqlite3.connect(str(tmp), timeout=30)
            try:
                source.backup(destination)
                row = destination.execute("PRAGMA quick_check").fetchone()
                if not row or str(row[0]).casefold() != "ok":
                    raise RuntimeError(f"UPDATE_DB_BACKUP_INVALID: {row}")
            finally:
                destination.close()
        os.replace(tmp, target)
        return target

    def launch_helper(self, request: UpdateRequest, *, parent_pid: int) -> subprocess.Popen[Any]:
        root = runtime_dir()
        console = root / "_runtime_console.exe"
        if console.is_file():
            executable = str(console)
            args = [executable, "-I", "-m", "telegram_autopilot.v2.updater_helper"]
        else:
            executable = sys.executable
            args = [executable, "-m", "telegram_autopilot.v2.updater_helper"]
        args += ["--request", str(self.request_path), "--parent-pid", str(int(parent_pid))]
        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(getattr(subprocess, "DETACHED_PROCESS", 0))
        self.write_state("UPDATER_LAUNCHED", request=request, helper=Path(executable).name)
        return subprocess.Popen(
            args,
            cwd=str(root),
            close_fds=(os.name != "nt"),
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def checkpoint_database(store: Any) -> str:
    try:
        with store.connect() as con:
            row = con.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
        return f"wal_checkpoint={tuple(row) if row is not None else 'ok'}"
    except Exception as exc:
        event("update", "database checkpoint failed", level=40, detail=str(exc)[:1000])
        raise
