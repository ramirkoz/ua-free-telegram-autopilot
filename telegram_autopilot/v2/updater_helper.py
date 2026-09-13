from __future__ import annotations

import argparse
import json
import os
import shutil
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


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_parent(pid: int, timeout: float = 180.0) -> bool:
    deadline = time.monotonic() + max(5.0, timeout)
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.5)
    return not _pid_alive(pid)


def _download(request: UpdateRequest, target: Path) -> None:
    req = urllib.request.Request(
        request.release_url,
        headers={"User-Agent": "UA-FREE-Telegram-Autopilot-Updater/2", "Accept": "application/octet-stream"},
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
    # The canonical remote-maintenance path is the user's Google Drive Desktop
    # supervisor feed. The remote agent drops an exact, SHA-pinned overlay there.
    # This also works for a private GitHub repository without ever storing a GitHub
    # token inside the portable application.
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
            if rel.parts and rel.parts[0].casefold() == "data":
                raise RuntimeError("UPDATE_BUNDLE_CONTAINS_DATA")
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
        (backup / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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


def _wait_healthy(protocol: UpdateProtocol, target_version: str, child: subprocess.Popen[Any], timeout: float = 120.0) -> bool:
    deadline = time.monotonic() + max(30.0, timeout)
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return False
        try:
            data = json.loads(protocol.health_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("healthy") is True and str(data.get("version")) == target_version:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    args = parser.parse_args(argv)

    protocol = UpdateProtocol()
    runtime = runtime_dir()
    request = protocol.load_request(Path(args.request))
    if request is None:
        protocol.write_result("FAILED", detail="UPDATE_REQUEST_MISSING")
        return 2
    if not protocol.request_is_newer(request):
        protocol.write_result("REJECTED", request=request, detail=f"Target {request.target_version} is not newer than {V2_VERSION}")
        return 3

    work = protocol.root / "work" / request.request_id
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    archive = work / request.asset_name
    stage = work / "stage"
    backup = protocol.root / "backups" / f"{V2_VERSION}_before_{request.target_version}_{request.request_id}"

    parent_gone = False
    try:
        protocol.write_state("DOWNLOADING", request=request, url=request.release_url)
        source = _obtain_archive(request, archive)
        actual = protocol.sha256(archive)
        if actual.casefold() != request.sha256.casefold():
            raise RuntimeError(f"UPDATE_SHA256_MISMATCH expected={request.sha256} actual={actual}")
        protocol.write_state("VERIFIED", request=request, sha256=actual, artifact_source=source)
        _safe_extract(archive, stage)
        _validate_stage(stage, request, runtime)
        if not _wait_parent(int(args.parent_pid)):
            raise RuntimeError("PARENT_DID_NOT_EXIT")
        parent_gone = True
        protocol.write_state("APPLYING", request=request)
        result = _apply(stage, runtime, backup)
        protocol.clear_health_marker()
        protocol.write_result("APPLIED", request=request, detail="Files replaced; starting target", files=result["files"], backup=str(backup))
        protocol.write_state("STARTING_NEW_VERSION", request=request, backup=str(backup))
        child = _launch_app(runtime)
        if _wait_healthy(protocol, request.target_version, child):
            protocol.write_result("HEALTHY", request=request, detail="Target version started and reported healthy", pid=child.pid, backup=str(backup))
            try:
                protocol.request_path.unlink()
            except FileNotFoundError:
                pass
            return 0

        try:
            child.terminate()
            child.wait(timeout=10)
        except Exception:
            pass
        protocol.write_state("ROLLING_BACK", request=request, backup=str(backup))
        _rollback(runtime, backup, result["manifest"])
        _restore_database(protocol, request)
        old_child = _launch_app(runtime)
        protocol.write_result("ROLLBACK_OK", request=request, detail="Target failed startup health gate; previous version restored", pid=old_child.pid, backup=str(backup))
        return 5
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if parent_gone:
            try:
                protocol.write_state("ROLLING_BACK", request=request, backup=str(backup), failure=detail)
                if (backup / "manifest.json").is_file():
                    _rollback(runtime, backup)
                _restore_database(protocol, request)
                old_child = _launch_app(runtime)
                protocol.write_result(
                    "ROLLBACK_OK", request=request,
                    detail=f"Update failed after shutdown; previous version restored: {detail}",
                    pid=old_child.pid, backup=str(backup),
                )
                return 6
            except Exception as rollback_exc:
                detail += f"; ROLLBACK_FAILED: {type(rollback_exc).__name__}: {rollback_exc}"
        protocol.write_result("FAILED", request=request, detail=detail, backup=str(backup))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
