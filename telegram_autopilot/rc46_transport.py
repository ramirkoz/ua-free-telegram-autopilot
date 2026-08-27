from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from .network import HttpResponse, NetworkError, resolve_public

_INSTALLED = False


def _cleanup_tree_best_effort(path: str | Path) -> None:
    """Remove a browser temp profile without turning a successful fetch into failure.

    Edge/Chrome can keep Crashpad files open for a fraction of a second after the
    headless process exits on Windows. TemporaryDirectory propagated WinError 145
    from that cleanup and made an otherwise successful source collection look
    broken. Cleanup is hygiene, not a publication gate.
    """
    target = Path(path)
    for delay in (0.0, 0.12, 0.30, 0.65):
        if delay:
            time.sleep(delay)
        try:
            shutil.rmtree(target)
            return
        except FileNotFoundError:
            return
        except OSError:
            continue
    shutil.rmtree(target, ignore_errors=True)


def browser_public_fetch_rc46(
    url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = 5 * 1024 * 1024,
    allowed_content_types=None,
) -> HttpResponse:
    from . import rc44_source_transport as rc44

    executable = rc44._browser_executable()
    if not executable:
        raise NetworkError("Browser source fallback is not available.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise NetworkError("Only absolute public HTTP/HTTPS URLs are allowed.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in {80, 443}:
        raise NetworkError("Only ports 80 and 443 are allowed.")
    host = parts.hostname.casefold().rstrip(".")
    addresses = resolve_public(host, port)
    address = next((value for value in addresses if ":" not in value), addresses[0])
    resolver_rules = f"MAP {host} {address}, MAP * ~NOTFOUND, EXCLUDE localhost"

    tmp = tempfile.mkdtemp(prefix="ua-free-browser-")
    profile = Path(tmp) / "profile"
    command = [
        executable,
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        f"--host-resolver-rules={resolver_rules}",
        "--dump-dom",
        url,
    ]
    try:
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(8.0, float(timeout) + 5.0),
                check=False,
                creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise NetworkError("Browser source fallback failed to run.") from exc
        returncode = completed.returncode
        stderr = bytes(completed.stderr or b"")
        body = bytes(completed.stdout or b"")
    finally:
        _cleanup_tree_best_effort(tmp)

    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise NetworkError(f"Browser source fallback failed: {detail or 'browser error'}")
    if len(body) > max_bytes:
        raise NetworkError("Remote response exceeds the configured size limit.")
    sample = body[:8192].lstrip().lower()
    if b"just a moment" in sample or b"cf-chl" in sample or b"challenge-platform" in sample:
        raise NetworkError(f"Remote request failed with HTTP 403: {url}")
    if sample.startswith(b"<?xml") or b"<rss" in sample:
        content_type = "application/rss+xml"
    elif b"<feed" in sample:
        content_type = "application/atom+xml"
    else:
        content_type = "text/html"
    headers = {"content-type": content_type}
    if allowed_content_types:
        normalized = {str(value).casefold() for value in allowed_content_types}
        if content_type.casefold() not in normalized:
            raise NetworkError(f"Unexpected content type: {content_type}.")
    return HttpResponse(200, headers, body, url)


def install_rc46_transport() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import rc44_source_transport as rc44

    rc44.browser_public_fetch = browser_public_fetch_rc46
    _INSTALLED = True
