from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

from .paths import data_dir

_DEFAULT_URL = "http://127.0.0.1:8081/v2/check"
_LT_SNAPSHOT_URL = "https://languagetool.org/download/snapshots/LanguageTool-latest-snapshot.zip"
_ADOPTIUM_ASSETS_URL = (
    "https://api.adoptium.net/v3/assets/latest/17/hotspot"
    "?architecture=x64&image_type=jre&os=windows&vendor=eclipse"
)
_ALLOWED_ISSUE_TYPES = {"misspelling", "typographical", "grammar"}
_NUMBER_RE = re.compile(r"\d")
_LATIN_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9._+-]{2,}|[A-Z]{2,}[A-Z0-9._+-]*)\b")
_JAVA_VERSION_RE = re.compile(r'version\s+"(?P<major>\d+)(?:[._-][^\"]*)?"', re.I)
_INSTALL_LOCK = threading.RLock()
_INSTALL_THREAD: threading.Thread | None = None
_SERVER_PROCESS: subprocess.Popen | None = None
_SERVER_LOCK = threading.RLock()
_NEXT_INSTALL_AT = 0.0


class LanguageToolUnavailable(RuntimeError):
    """Mandatory local Ukrainian proofreader is not ready yet."""


@dataclass(frozen=True, slots=True)
class LanguageToolEditResult:
    text: str
    changes: int
    details: tuple[str, ...] = ()


def languagetool_status() -> dict[str, object]:
    """Cheap operator-facing status snapshot. No external network call."""
    ready = _probe_server(timeout=0.25)
    with _INSTALL_LOCK:
        installing = bool(_INSTALL_THREAD and _INSTALL_THREAD.is_alive())
    retry_seconds = max(0, int(_NEXT_INSTALL_AT - time.monotonic())) if _NEXT_INSTALL_AT else 0
    jar = _find_server_jar()
    root = _java_root()
    bundled_java = (root / "bin" / "java.exe").is_file() or (root / "bin" / "java").is_file()
    if ready:
        state, text = "ready", "✓ LanguageTool працює локально · 127.0.0.1:8081"
    elif installing:
        state, text = "installing", "… LanguageTool встановлюється/запускається у фоні"
    elif retry_seconds:
        state, text = "retry_wait", f"⚠ LanguageTool недоступний · повтор приблизно через {retry_seconds} с"
    elif jar:
        state, text = "installed_stopped", "⚠ LanguageTool встановлений, але локальний сервер не відповідає"
    else:
        state, text = "missing", "⚠ LanguageTool ще не встановлений"
    return {
        "ready": ready, "installing": installing, "state": state, "text": text,
        "endpoint": _endpoint(), "installed": bool(jar), "bundled_java": bundled_java,
        "retry_seconds": retry_seconds,
    }


def _is_windows() -> bool:
    return os.name == "nt"


def _endpoint() -> str:
    return str(os.environ.get("UA_FREE_LANGUAGETOOL_URL") or _DEFAULT_URL).strip()


def _tools_dir() -> Path:
    path = data_dir() / "Tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _lt_root() -> Path:
    return _tools_dir() / "LanguageTool"


def _java_root() -> Path:
    return _tools_dir() / "Java17"


def _state_path() -> Path:
    return _tools_dir() / "languagetool_install.json"


def _emit(callback: Callable[[str, str], None] | None, kind: str, text: str) -> None:
    if callback is None:
        return
    try:
        callback(kind, text)
    except Exception:
        pass


def _safe_replacement(old: str, new: str) -> bool:
    if not old or not new or old == new:
        return False
    # LanguageTool is only a language checker here, never a factual editor.
    if _NUMBER_RE.search(old) or _NUMBER_RE.search(new):
        return False
    if _LATIN_ENTITY_RE.search(old) or _LATIN_ENTITY_RE.search(new):
        return False
    if abs(len(new) - len(old)) > max(18, len(old) * 2):
        return False
    return True


def _probe_server(*, timeout: float = 0.45) -> bool:
    url = _endpoint()
    if not url.startswith(("http://127.0.0.1", "http://localhost")):
        return False
    payload = urllib.parse.urlencode({"language": "uk-UA", "text": "Це коротка перевірка."}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "UAFreeTelegramAutopilot/0.1.0-rc25"},
    )
    try:
        with urllib.request.urlopen(req, timeout=max(0.1, float(timeout))) as response:
            if int(getattr(response, "status", 200) or 200) >= 400:
                return False
            raw = response.read(64_000)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        return isinstance(data, dict) and isinstance(data.get("matches"), list)
    except Exception:
        return False


def _java_major(java_exe: Path | str) -> int:
    try:
        flags = 0
        if _is_windows():
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [str(java_exe), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
            check=False,
            creationflags=flags,
            text=True,
            errors="replace",
        )
        match = _JAVA_VERSION_RE.search(proc.stdout or "")
        return int(match.group("major")) if match else 0
    except Exception:
        return 0


def _bundled_java() -> Path | None:
    root = _java_root()
    candidates = [root / "bin" / "java.exe", root / "bin" / "java"]
    if root.exists():
        candidates.extend(root.glob("**/bin/java.exe"))
        candidates.extend(root.glob("**/bin/java"))
    for path in candidates:
        if path.is_file() and _java_major(path) >= 17:
            return path
    return None


def _system_java() -> Path | None:
    java = shutil.which("java")
    if java and _java_major(java) >= 17:
        return Path(java)
    return None


def _find_server_jar() -> Path | None:
    root = _lt_root()
    if not root.exists():
        return None
    direct = root / "languagetool-server.jar"
    if direct.is_file():
        return direct
    for candidate in root.glob("**/languagetool-server.jar"):
        if candidate.is_file():
            return candidate
    return None


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"Пошкоджений ZIP: {bad}")
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                raise RuntimeError("Небезпечний шлях у ZIP")
            parts = [part for part in name.split("/") if part not in {"", "."}]
            if any(part == ".." for part in parts):
                raise RuntimeError("Небезпечний шлях у ZIP")
            # Reject Unix-style symlink entries too.
            mode = (info.external_attr >> 16) & 0xFFFF
            if (mode & 0o170000) == 0o120000:
                raise RuntimeError("ZIP містить символічне посилання")
            target = (destination / Path(*parts)).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise RuntimeError("Небезпечний шлях у ZIP") from exc
        zf.extractall(destination)


def _download(url: str, target: Path, *, max_bytes: int, expected_sha256: str | None = None) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    req = urllib.request.Request(url, headers={"User-Agent": "UAFreeTelegramAutopilot/0.1.0-rc25", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response, open(part, "wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError("Завантаження перевищило безпечний ліміт")
                out.write(chunk)
                digest.update(chunk)
        actual = digest.hexdigest().lower()
        if expected_sha256 and actual != expected_sha256.strip().lower():
            raise RuntimeError("SHA-256 завантаженого Java не збігається з даними Adoptium")
        os.replace(part, target)
        return actual
    finally:
        try:
            part.unlink(missing_ok=True)
        except Exception:
            pass


def _adoptium_package() -> tuple[str, str]:
    req = urllib.request.Request(_ADOPTIUM_ASSETS_URL, headers={"User-Agent": "UAFreeTelegramAutopilot/0.1.0-rc25", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(2 * 1024 * 1024)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, list) or not data:
        raise RuntimeError("Adoptium не повернув Java 17 JRE")
    package = ((data[0] or {}).get("binary") or {}).get("package") or {}
    link = str(package.get("link") or "").strip()
    checksum = str(package.get("checksum") or "").strip().lower()
    if not link.startswith("https://") or len(checksum) != 64 or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise RuntimeError("Adoptium повернув неповні метадані Java")
    return link, checksum


def _install_java(callback: Callable[[str, str], None] | None) -> Path:
    existing = _bundled_java() or _system_java()
    if existing:
        return existing
    if not _is_windows():
        raise RuntimeError("Автоматичне встановлення Java підтримується у Windows Portable")
    _emit(callback, "languagetool", "Java 17 не знайдено. Завантажую портативний Eclipse Temurin JRE 17…")
    link, checksum = _adoptium_package()
    tools = _tools_dir()
    archive = tools / "temurin17-jre.zip"
    _download(link, archive, max_bytes=180 * 1024 * 1024, expected_sha256=checksum)
    temp = Path(tempfile.mkdtemp(prefix="java17-", dir=str(tools)))
    try:
        _safe_extract_zip(archive, temp)
        java_candidates = list(temp.glob("**/bin/java.exe"))
        if not java_candidates:
            raise RuntimeError("У завантаженому JRE немає bin/java.exe")
        source_root = java_candidates[0].parent.parent
        target = _java_root()
        backup = tools / "Java17.old"
        shutil.rmtree(backup, ignore_errors=True)
        if target.exists():
            os.replace(target, backup)
        shutil.copytree(source_root, target)
        shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        archive.unlink(missing_ok=True)
    java = _bundled_java()
    if not java:
        raise RuntimeError("Портативний Java 17 завантажено, але перевірка java -version не пройшла")
    _emit(callback, "languagetool", "Портативний Java 17 встановлено в Data/Tools/Java17.")
    return java


def _install_languagetool(callback: Callable[[str, str], None] | None) -> Path:
    existing = _find_server_jar()
    if existing:
        return existing
    _emit(callback, "languagetool", "LanguageTool не знайдено. Завантажую офіційний локальний snapshot…")
    tools = _tools_dir()
    archive = tools / "LanguageTool-latest-snapshot.zip"
    snapshot_sha = _download(_LT_SNAPSHOT_URL, archive, max_bytes=500 * 1024 * 1024)
    temp = Path(tempfile.mkdtemp(prefix="languagetool-", dir=str(tools)))
    try:
        _safe_extract_zip(archive, temp)
        jars = list(temp.glob("**/languagetool-server.jar"))
        if not jars:
            raise RuntimeError("У snapshot LanguageTool немає languagetool-server.jar")
        source_root = jars[0].parent
        target = _lt_root()
        backup = tools / "LanguageTool.old"
        shutil.rmtree(backup, ignore_errors=True)
        if target.exists():
            os.replace(target, backup)
        shutil.copytree(source_root, target)
        shutil.rmtree(backup, ignore_errors=True)
        state = {
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "snapshot_sha256": snapshot_sha,
            "source": _LT_SNAPSHOT_URL,
        }
        _state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        shutil.rmtree(temp, ignore_errors=True)
        archive.unlink(missing_ok=True)
    jar = _find_server_jar()
    if not jar:
        raise RuntimeError("LanguageTool розпаковано, але серверний JAR не знайдено")
    _emit(callback, "languagetool", "LanguageTool встановлено в Data/Tools/LanguageTool.")
    return jar


def _stop_owned_server() -> None:
    global _SERVER_PROCESS
    with _SERVER_LOCK:
        proc = _SERVER_PROCESS
        _SERVER_PROCESS = None
    if not proc:
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


atexit.register(_stop_owned_server)


def _start_server(java: Path, jar: Path, callback: Callable[[str, str], None] | None) -> bool:
    global _SERVER_PROCESS
    if _probe_server(timeout=0.35):
        return True
    root = jar.parent
    config = root / "server.properties"
    if not config.exists():
        config.write_text("", encoding="utf-8")
    cmd = [
        str(java), "-Xms64m", "-Xmx768m", "-cp", str(jar),
        "org.languagetool.server.HTTPServer",
        "--config", str(config), "--port", "8081",
    ]
    kwargs: dict[str, object] = {
        "cwd": str(root),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if _is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with _SERVER_LOCK:
        if _SERVER_PROCESS and _SERVER_PROCESS.poll() is None:
            proc = _SERVER_PROCESS
        else:
            proc = subprocess.Popen(cmd, **kwargs)  # type: ignore[arg-type]
            _SERVER_PROCESS = proc
    for _ in range(30):
        if proc.poll() is not None:
            break
        if _probe_server(timeout=0.35):
            _emit(callback, "languagetool", "LanguageTool локальний сервер готовий (127.0.0.1:8081).")
            return True
        time.sleep(0.4)
    return False


def ensure_languagetool(callback: Callable[[str, str], None] | None = None) -> bool:
    """Ensure a private local LanguageTool server is available.

    Installation is portable: LanguageTool and, if needed, Temurin JRE 17 are
    stored under Data/Tools. No admin rights, registry changes or public cloud
    LanguageTool API are used.
    """
    global _NEXT_INSTALL_AT
    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL") == "1":
        return False
    if os.environ.get("UA_FREE_LANGUAGETOOL_URL"):
        return _probe_server(timeout=0.7)
    if _probe_server(timeout=0.35):
        return True
    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL_INSTALL") == "1":
        return False
    with _INSTALL_LOCK:
        if _probe_server(timeout=0.35):
            return True
        try:
            java = _bundled_java() or _system_java()
            if not java:
                java = _install_java(callback)
            jar = _find_server_jar()
            if not jar:
                jar = _install_languagetool(callback)
            if not _start_server(java, jar, callback):
                raise RuntimeError("LanguageTool встановлено, але локальний сервер не запустився")
            _NEXT_INSTALL_AT = 0.0
            return True
        except Exception as exc:
            _NEXT_INSTALL_AT = time.monotonic() + 300.0
            _emit(callback, "error", f"LanguageTool: автоматичне встановлення/запуск не вдалося: {exc}. Повтор через 5 хв.")
            return False


def _ensure_worker(callback: Callable[[str, str], None] | None) -> None:
    global _INSTALL_THREAD
    try:
        ensure_languagetool(callback)
    finally:
        with _INSTALL_LOCK:
            _INSTALL_THREAD = None


def ensure_languagetool_async(callback: Callable[[str, str], None] | None = None) -> bool:
    """Start a non-blocking installation/startup check; return current readiness."""
    global _INSTALL_THREAD
    global _NEXT_INSTALL_AT
    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL") == "1":
        return False
    if _probe_server(timeout=0.2):
        _NEXT_INSTALL_AT = 0.0
        return True
    if _NEXT_INSTALL_AT and time.monotonic() < _NEXT_INSTALL_AT:
        return False
    if os.environ.get("UA_FREE_LANGUAGETOOL_URL"):
        return False
    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL_INSTALL") == "1":
        return False
    with _INSTALL_LOCK:
        if _INSTALL_THREAD and _INSTALL_THREAD.is_alive():
            return False
        _INSTALL_THREAD = threading.Thread(
            target=_ensure_worker,
            args=(callback,),
            name="LanguageToolInstaller",
            daemon=True,
        )
        _INSTALL_THREAD.start()
    return False


def apply_local_languagetool_detailed(
    value: str, *, timeout: float = 0.75, max_changes: int = 12, require_ready: bool = False
) -> LanguageToolEditResult:
    """Apply conservative local LanguageTool suggestions and report the edits.

    In RC25 ``require_ready=True`` is used by the final publication gate. If the
    local proofreader is still installing/starting, the article is delayed rather
    than published without the promised Ukrainian check.
    """
    text = str(value or "").strip()
    if not text:
        return LanguageToolEditResult(text, 0, ())
    if os.environ.get("UA_FREE_DISABLE_LANGUAGETOOL") == "1":
        if require_ready and os.environ.get("UA_FREE_ALLOW_WITHOUT_LANGUAGETOOL") != "1":
            raise LanguageToolUnavailable("LanguageTool вимкнений змінною UA_FREE_DISABLE_LANGUAGETOOL.")
        return LanguageToolEditResult(text, 0, ())
    url = _endpoint()
    if not url.startswith(("http://127.0.0.1", "http://localhost")) and not os.environ.get("UA_FREE_LANGUAGETOOL_URL"):
        if require_ready:
            raise LanguageToolUnavailable("LanguageTool має працювати локально або через явно заданий UA_FREE_LANGUAGETOOL_URL.")
        return LanguageToolEditResult(text, 0, ())
    if not _probe_server(timeout=min(0.35, max(0.1, float(timeout)))):
        ensure_languagetool_async()
        if require_ready and os.environ.get("UA_FREE_ALLOW_WITHOUT_LANGUAGETOOL") != "1":
            raise LanguageToolUnavailable(
                "LanguageTool ще не готовий. Автовстановлення/запуск триває; публікацію відкладено, щоб не випустити неперевірений український текст."
            )
        return LanguageToolEditResult(text, 0, ())
    payload = urllib.parse.urlencode({"language": "uk-UA", "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "UAFreeTelegramAutopilot/0.1.0-rc25"},
    )
    try:
        with urllib.request.urlopen(req, timeout=max(0.2, float(timeout))) as response:
            raw = response.read(512_000)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        ensure_languagetool_async()
        if require_ready and os.environ.get("UA_FREE_ALLOW_WITHOUT_LANGUAGETOOL") != "1":
            raise LanguageToolUnavailable(f"LanguageTool перестав відповідати: {exc}") from exc
        return LanguageToolEditResult(text, 0, ())

    edits: list[tuple[int, int, str]] = []
    for match in list(data.get("matches") or []):
        if len(edits) >= max_changes:
            break
        rule = match.get("rule") or {}
        issue_type = str(rule.get("issueType") or "").casefold()
        if issue_type not in _ALLOWED_ISSUE_TYPES:
            continue
        replacements = match.get("replacements") or []
        if not replacements:
            continue
        try:
            offset = int(match.get("offset"))
            length = int(match.get("length"))
        except Exception:
            continue
        if offset < 0 or length <= 0 or offset + length > len(text):
            continue
        old = text[offset: offset + length]
        new = str(replacements[0].get("value") or "").strip()
        if not _safe_replacement(old, new):
            continue
        edits.append((offset, offset + length, new))

    if not edits:
        return LanguageToolEditResult(text, 0, ())
    out = text
    applied = 0
    details: list[str] = []
    last_start = len(text) + 1
    for start, end, replacement in sorted(edits, reverse=True):
        if end > last_start:
            continue
        old = out[start:end]
        out = out[:start] + replacement + out[end:]
        last_start = start
        applied += 1
        if len(details) < 8:
            details.append(f"{old} → {replacement}")
    return LanguageToolEditResult(out.strip(), applied, tuple(details))


def apply_local_languagetool(
    value: str, *, timeout: float = 0.75, max_changes: int = 12, require_ready: bool = False
) -> tuple[str, int]:
    result = apply_local_languagetool_detailed(
        value, timeout=timeout, max_changes=max_changes, require_ready=require_ready
    )
    return result.text, result.changes
