from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from ..paths import data_dir, runtime_dir
from . import V2_VERSION
from .update_protocol import UPDATE_RUNTIME_ABI, UpdateProtocol, UpdateRequest


_MAX_LAUNCH_ATTEMPTS = 3
_HEALTH_TIMEOUT_SECONDS = 90.0
_ROLLBACK_HEALTH_TIMEOUT_SECONDS = 90.0
_PARENT_GRACE_SECONDS = 5.0
_PARENT_KILL_TIMEOUT_SECONDS = 15.0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(exit_code)):
                return False
            return int(exit_code.value) == still_active
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_pid_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.5, float(timeout))
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.25)
    return not _pid_alive(pid)


def _kill_pid_only(pid: int) -> None:
    """Terminate only the application parent, never the detached updater tree."""
    if pid <= 0 or not _pid_alive(pid):
        return
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/F"],
            capture_output=True,
            check=False,
            creationflags=creationflags,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return


def _ensure_parent_stopped(pid: int) -> bool:
    # Give a naturally closing parent a very small grace period.  RC37 no longer
    # depends on graceful worker shutdown; after package preflight the detached
    # transaction is authoritative and may terminate this exact PID.
    if _wait_pid_gone(pid, _PARENT_GRACE_SECONDS):
        return True
    _kill_pid_only(pid)
    if _wait_pid_gone(pid, _PARENT_KILL_TIMEOUT_SECONDS):
        return True
    if os.name != "nt" and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        return _wait_pid_gone(pid, 5.0)
    return not _pid_alive(pid)


def _download(request: UpdateRequest, target: Path) -> None:
    req = urllib.request.Request(
        request.release_url,
        headers={"User-Agent": "UA-FREE-Telegram-Autopilot-Updater/3", "Accept": "application/octet-stream"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)


def _configured_mirror_dir() -> Path | None:
    config = data_dir() / "supervisor" / "config.json"
    try:
        value = json.loads(config.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    raw = str(value.get("mirror_dir") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _obtain_archive(request: UpdateRequest, target: Path) -> str:
    # Prefer the exact SHA-pinned Drive overlay when it has already synced.  The
    # fixed GitHub release URL is the safe fallback; the remote agent cannot supply
    # an arbitrary executable URL.
    mirror = _configured_mirror_dir()
    if mirror is not None:
        candidate = mirror / request.asset_name
        if candidate.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            return "drive-mirror"
    _download(request, target)
    return "github-release"


def _safe_extract(zip_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise RuntimeError(f"UNSAFE_UPDATE_PATH: {name}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode & 0o170000 == 0o120000:
                raise RuntimeError(f"UNSAFE_UPDATE_SYMLINK: {name}")
            destination = target.joinpath(*pure.parts)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _validate_stage(stage: Path, request: UpdateRequest, runtime: Path) -> None:
    version_file = stage / "VERSION.txt"
    if not version_file.is_file() or version_file.read_text(encoding="utf-8").strip() != request.target_version:
        raise RuntimeError("UPDATE_VERSION_MISMATCH")
    abi_file = stage / "UPDATE_RUNTIME_ABI.txt"
    if not abi_file.is_file() or abi_file.read_text(encoding="utf-8").strip() != UPDATE_RUNTIME_ABI:
        raise RuntimeError("UPDATE_RUNTIME_ABI_MISMATCH")
    for required in (
        "telegram_autopilot/v2/main.py",
        "telegram_autopilot/v2/storage.py",
        "telegram_autopilot/v2/update_protocol.py",
        "telegram_autopilot/v2/updater_helper.py",
        "app_v2.py",
        "PUBLIC_VERSION.txt",
        "V2_VERSION.txt",
    ):
        if not (stage / required).is_file():
            raise RuntimeError(f"UPDATE_MISSING_FILE: {required}")
    old_req = runtime / "requirements.txt"
    new_req = stage / "requirements.txt"
    if old_req.is_file() and new_req.is_file() and old_req.read_bytes() != new_req.read_bytes():
        raise RuntimeError("UPDATE_REQUIRES_NEW_RUNTIME_DEPENDENCIES")


def _apply(stage: Path, runtime: Path, backup: Path) -> dict[str, Any]:
    backup.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    applied: list[Path] = []
    try:
        for source in _files(stage):
            rel = source.relative_to(stage)
            if rel.parts and rel.parts[0].casefold() in {"data", "tools"}:
                raise RuntimeError("UPDATE_BUNDLE_CONTAINS_PERSISTENT_STATE")
            destination = runtime / rel
            old_exists = destination.is_file()
            if old_exists:
                old_backup = backup / rel
                old_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, old_backup)
            manifest.append({"path": rel.as_posix(), "old_exists": old_exists})
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(destination.name + ".update.tmp")
            shutil.copy2(source, temp)
            os.replace(temp, destination)
            applied.append(rel)
        (backup / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"files": len(applied), "manifest": manifest}
    except Exception:
        _rollback(runtime, backup, manifest)
        raise


def _rollback(runtime: Path, backup: Path, manifest: list[dict[str, Any]] | None = None) -> None:
    if manifest is None:
        try:
            manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            manifest = []
    for item in reversed(list(manifest or [])):
        rel = Path(str(item.get("path") or ""))
        if not rel.parts:
            continue
        destination = runtime / rel
        old_exists = bool(item.get("old_exists"))
        old_backup = backup / rel
        try:
            if old_exists and old_backup.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp = destination.with_name(destination.name + ".rollback.tmp")
                shutil.copy2(old_backup, temp)
                os.replace(temp, destination)
            elif not old_exists:
                destination.unlink(missing_ok=True)
        except Exception:
            pass


def _restore_database(protocol: UpdateProtocol, request: UpdateRequest) -> None:
    backup = protocol.database_backup_path(request)
    if not backup.is_file():
        raise RuntimeError("UPDATE_DB_BACKUP_MISSING")
    current = data_dir() / "telegram_autopilot_v2.sqlite3"
    current.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("-wal", "-shm"):
        try:
            Path(str(current) + suffix).unlink()
        except FileNotFoundError:
            pass
    temp = current.with_name(current.name + ".restore.tmp")
    shutil.copy2(backup, temp)
    os.replace(temp, current)


def _launch_app(runtime: Path) -> subprocess.Popen[Any]:
    gui = runtime / "UA_FREE_Telegram_Autopilot.exe"
    if gui.is_file():
        return subprocess.Popen([str(gui)], cwd=str(runtime))
    return subprocess.Popen([sys.executable, str(runtime / "app_v2.py")], cwd=str(runtime))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, dict) else {}
    except Exception:
        return {}


def _fresh_supervisor_healthy(expected_version: str, launched_at: float) -> tuple[bool, str]:
    path = data_dir() / "supervisor" / "status.json"
    if not path.is_file():
        return False, "supervisor status missing"
    try:
        if path.stat().st_mtime < launched_at - 1.0:
            return False, "supervisor status is stale"
    except OSError:
        return False, "supervisor status unreadable"

    status = _read_json(path)
    if str(status.get("version") or "") != expected_version:
        return False, f"version={status.get('version') or '?'}"
    database = status.get("database")
    if not isinstance(database, dict) or database.get("ok") is not True:
        return False, "database not healthy"

    enabled = status.get("enabled_channels")
    enabled_count = len(enabled) if isinstance(enabled, dict) else 0
    if enabled_count <= 0:
        # An empty freshly initialized installation has no workers by design.
        return True, "fresh supervisor + DB OK; no enabled channels"

    if status.get("expected_running") is False:
        return False, "runtime not expected to run"
    if status.get("runtime_running") is not True:
        return False, "runtime_running=false"
    lifecycle = str(status.get("lifecycle_state") or "").upper()
    if lifecycle and lifecycle != "RUNNING":
        return False, f"lifecycle={lifecycle}"
    workers = int(status.get("live_workers") or 0)
    collectors = int(status.get("live_collectors") or 0)
    if workers < enabled_count:
        return False, f"workers={workers}/{enabled_count}"
    if collectors < enabled_count:
        return False, f"collectors={collectors}/{enabled_count}"
    return True, f"RUNNING workers={workers}/{enabled_count} collectors={collectors}/{enabled_count} DB=OK"


def _startup_marker_healthy(protocol: UpdateProtocol, expected_version: str) -> bool:
    marker = _read_json(protocol.health_path)
    return bool(marker.get("healthy") is True and str(marker.get("version") or "") == expected_version)


def _wait_healthy(
    protocol: UpdateProtocol,
    target_version: str,
    child: subprocess.Popen[Any],
    launched_at: float,
    timeout: float,
) -> tuple[bool, str]:
    deadline = time.monotonic() + max(30.0, float(timeout))
    last_detail = "waiting for startup"
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return False, f"process exited code={child.returncode}"
        marker_ok = _startup_marker_healthy(protocol, target_version)
        supervisor_ok, detail = _fresh_supervisor_healthy(target_version, launched_at)
        last_detail = detail
        if marker_ok and supervisor_ok:
            return True, detail
        time.sleep(1.0)
    return False, last_detail


def _stop_child(child: subprocess.Popen[Any]) -> None:
    pid = int(getattr(child, "pid", 0) or 0)
    if pid <= 0:
        return
    try:
        child.terminate()
        child.wait(timeout=8)
        return
    except Exception:
        pass
    _kill_pid_only(pid)
    _wait_pid_gone(pid, 8.0)


def _launch_and_verify(
    protocol: UpdateProtocol,
    runtime: Path,
    expected_version: str,
    *,
    attempts: int,
    timeout: float,
    phase_prefix: str,
) -> tuple[bool, int | None, str]:
    last_pid: int | None = None
    last_detail = "not launched"
    for attempt in range(1, max(1, int(attempts)) + 1):
        protocol.clear_health_marker()
        launched_at = time.time()
        protocol.write_state(
            f"{phase_prefix}_STARTING", detail=f"version={expected_version}; attempt={attempt}"
        )
        try:
            child = _launch_app(runtime)
        except OSError as exc:
            last_detail = f"launch failed: {type(exc).__name__}: {exc}"
            continue
        last_pid = int(child.pid)
        ok, detail = _wait_healthy(protocol, expected_version, child, launched_at, timeout)
        if ok:
            return True, last_pid, detail
        last_detail = detail
        _stop_child(child)
    return False, last_pid, last_detail


def _rollback_and_verify(
    protocol: UpdateProtocol,
    request: UpdateRequest,
    runtime: Path,
    backup: Path,
    previous_version: str,
    *,
    reason: str,
) -> int:
    protocol.write_state("ROLLING_BACK", request=request, backup=str(backup), failure=reason)
    if (backup / "manifest.json").is_file():
        _rollback(runtime, backup)
    _restore_database(protocol, request)
    ok, pid, detail = _launch_and_verify(
        protocol,
        runtime,
        previous_version,
        attempts=_MAX_LAUNCH_ATTEMPTS,
        timeout=_ROLLBACK_HEALTH_TIMEOUT_SECONDS,
        phase_prefix="ROLLBACK",
    )
    if ok:
        protocol.write_result(
            "ROLLBACK_OK", request=request,
            detail=f"Previous version restored and verified: {detail}; update failure: {reason}",
            pid=pid, backup=str(backup), rollback_runtime_verified=True,
        )
        return 6
    protocol.write_result(
        "ROLLBACK_FAILED", request=request,
        detail=f"Rollback files/DB restored but runtime verification failed: {detail}; update failure: {reason}",
        pid=pid, backup=str(backup), rollback_runtime_verified=False,
    )
    return 7


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    args = parser.parse_args(argv)

    protocol = UpdateProtocol()
    runtime = runtime_dir()
    previous_version = V2_VERSION
    request = protocol.load_request(Path(args.request))
    if request is None:
        protocol.write_result("FAILED", detail="UPDATE_REQUEST_MISSING")
        return 2
    if not protocol.request_is_newer(request):
        protocol.write_result(
            "REJECTED", request=request,
            detail=f"Target {request.target_version} is not newer than {previous_version}",
        )
        return 3

    work = protocol.root / "work" / request.request_id
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    archive = work / request.asset_name
    stage = work / "stage"
    backup = protocol.root / "backups" / f"{previous_version}_before_{request.target_version}_{request.request_id}"

    parent_gone = False
    applied = False
    try:
        # PRE-FLIGHT WHILE THE CURRENT VERSION IS STILL RUNNING.
        protocol.write_state("DOWNLOADING", request=request, url=request.release_url)
        source = _obtain_archive(request, archive)
        actual = protocol.sha256(archive)
        if actual.casefold() != request.sha256.casefold():
            raise RuntimeError(f"UPDATE_SHA256_MISMATCH expected={request.sha256} actual={actual}")
        protocol.write_state("VERIFIED", request=request, sha256=actual, artifact_source=source)
        _safe_extract(archive, stage)
        _validate_stage(stage, request, runtime)
        protocol.write_state(
            "PREFLIGHT_OK", request=request,
            detail=f"artifact={source}; sha256={actual}; parent_pid={args.parent_pid}",
        )

        # The approved transaction now owns shutdown.  Do not wait for collector
        # threads forever.  Kill this exact parent PID only, never the updater tree.
        protocol.write_state("STOPPING_PARENT", request=request, parent_pid=int(args.parent_pid))
        if not _ensure_parent_stopped(int(args.parent_pid)):
            raise RuntimeError("PARENT_DID_NOT_EXIT")
        parent_gone = True

        protocol.write_state("APPLYING", request=request)
        result = _apply(stage, runtime, backup)
        applied = True
        protocol.clear_health_marker()
        protocol.write_result(
            "APPLIED", request=request,
            detail="Files replaced; starting target under supervisor health gate",
            files=result["files"], backup=str(backup),
        )

        ok, pid, detail = _launch_and_verify(
            protocol,
            runtime,
            request.target_version,
            attempts=_MAX_LAUNCH_ATTEMPTS,
            timeout=_HEALTH_TIMEOUT_SECONDS,
            phase_prefix="TARGET",
        )
        if ok:
            protocol.write_result(
                "HEALTHY", request=request,
                detail=f"Target version verified by fresh Supervisor status: {detail}",
                pid=pid, backup=str(backup), runtime_verified=True,
            )
            try:
                protocol.request_path.unlink()
            except FileNotFoundError:
                pass
            return 0

        reason = f"TARGET_HEALTH_GATE_FAILED: {detail}"
        return _rollback_and_verify(
            protocol, request, runtime, backup, previous_version, reason=reason
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        if parent_gone:
            try:
                # Even if overlay application itself failed, _apply has already
                # attempted a local rollback.  Restore the DB snapshot and then
                # prove that the previous runtime is genuinely alive.
                return _rollback_and_verify(
                    protocol, request, runtime, backup, previous_version, reason=reason
                )
            except Exception as rollback_exc:
                reason += f"; ROLLBACK_EXCEPTION: {type(rollback_exc).__name__}: {rollback_exc}"
                protocol.write_result(
                    "ROLLBACK_FAILED", request=request, detail=reason,
                    backup=str(backup), rollback_runtime_verified=False,
                )
                return 7

        # Preflight failed before shutdown.  The known-good parent is deliberately
        # left untouched and keeps running.
        protocol.write_result(
            "FAILED", request=request,
            detail=f"PREFLIGHT_FAILED_WITH_PARENT_RUNNING: {reason}",
            backup=str(backup), parent_preserved=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
