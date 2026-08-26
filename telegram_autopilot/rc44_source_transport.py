from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .network import HttpResponse, NetworkError, resolve_public

_ACCESS_HTTP_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 429")
_INSTALLED = False


def _is_access_error(error: BaseException | str) -> bool:
    text = str(error)
    return any(marker in text for marker in _ACCESS_HTTP_MARKERS)


def _content_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().casefold()


def _parse_headers(raw: bytes) -> tuple[int, dict[str, str]]:
    """Parse the final HTTP response block written by curl -D."""
    text = raw.decode("iso-8859-1", errors="replace").replace("\r\n", "\n")
    blocks = [block for block in re.split(r"\n\n+", text) if block.lstrip().startswith("HTTP/")]
    if not blocks:
        raise NetworkError("System HTTP fallback returned no HTTP response headers.")
    block = blocks[-1]
    lines = block.splitlines()
    status_match = re.match(r"HTTP/\S+\s+(\d{3})", lines[0].strip())
    if not status_match:
        raise NetworkError("System HTTP fallback returned malformed response status.")
    status = int(status_match.group(1))
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().casefold()] = value.strip()
    return status, headers


def _curl_executable() -> str:
    return shutil.which("curl.exe") or shutil.which("curl") or ""


def _pinned_resolve(host: str, port: int, timeout: float) -> str:
    addresses = resolve_public(host, port)
    if not addresses:
        raise NetworkError(f"No usable public address for {host}.")
    address = next((value for value in addresses if ":" not in value), addresses[0])
    if ":" in address:
        address = f"[{address}]"
    return f"{host}:{port}:{address}"


def curl_public_fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_bytes: int = 5 * 1024 * 1024,
    allowed_content_types=None,
    max_redirects: int = 4,
) -> HttpResponse:
    """Fetch a public editorial URL through the OS curl transport.

    This is only a fallback for public source GETs that returned HTTP 401/403/429
    through the pinned Python transport. Every redirect target is resolved and
    checked as public before curl is allowed to connect, and curl itself is pinned
    to the already validated IP via --resolve. This keeps the existing SSRF guard
    while avoiding false bot blocks caused by Python's TLS/HTTP fingerprint.
    """
    executable = _curl_executable()
    if not executable:
        raise NetworkError("System curl fallback is not available.")

    current = str(url)
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
            "text/xml;q=0.9, text/html;q=0.8, application/xhtml+xml;q=0.8, */*;q=0.5"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    }
    base_headers.update(dict(headers or {}))

    for redirect_index in range(max_redirects + 1):
        try:
            parts = urlsplit(current)
        except ValueError as exc:
            raise NetworkError("Invalid URL.") from exc
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise NetworkError("Only absolute HTTP/HTTPS URLs are allowed.")
        if parts.username or parts.password or parts.fragment:
            raise NetworkError("URL credentials and fragments are not allowed.")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in {80, 443}:
            raise NetworkError("Only ports 80 and 443 are allowed.")
        host = parts.hostname.casefold().rstrip(".")
        pinned = _pinned_resolve(host, port, timeout)
        referer = f"{parts.scheme}://{host}/"

        with tempfile.TemporaryDirectory(prefix="ua-free-feed-") as tmp:
            body_path = Path(tmp) / "body.bin"
            header_path = Path(tmp) / "headers.txt"
            command = [
                executable,
                "--silent",
                "--show-error",
                "--request",
                "GET",
                "--connect-timeout",
                str(max(2, min(int(timeout), 12))),
                "--max-time",
                str(max(3, int(timeout))),
                "--max-filesize",
                str(int(max_bytes)),
                "--proto",
                "=http,https",
                "--resolve",
                pinned,
                "--output",
                str(body_path),
                "--dump-header",
                str(header_path),
                "--referer",
                referer,
                "--header",
                "Sec-Fetch-Dest: document",
                "--header",
                "Sec-Fetch-Mode: navigate",
                "--header",
                "Sec-Fetch-Site: same-origin",
            ]
            for key, value in base_headers.items():
                if key.casefold() in {"host", "connection", "accept-encoding"}:
                    continue
                command.extend(["--header", f"{key}: {value}"])
            command.append(current)

            try:
                completed = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=max(5.0, float(timeout) + 3.0),
                    check=False,
                    creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise NetworkError("System HTTP fallback failed to run.") from exc
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", errors="replace").strip()
                raise NetworkError(f"System HTTP fallback failed: {detail or 'curl error'}")
            if not header_path.exists():
                raise NetworkError("System HTTP fallback returned no headers.")
            status, response_headers = _parse_headers(header_path.read_bytes())
            body = body_path.read_bytes() if body_path.exists() else b""
            if len(body) > max_bytes:
                raise NetworkError("Remote response exceeds the configured size limit.")

        if status in {301, 302, 303, 307, 308}:
            location = response_headers.get("location", "")
            if not location:
                raise NetworkError("Redirect response has no Location header.")
            if redirect_index >= max_redirects:
                raise NetworkError("Too many redirects.")
            current = urljoin(current, location)
            continue
        if status >= 400:
            raise NetworkError(f"Remote request failed with HTTP {status}: {current}")
        if allowed_content_types:
            actual = _content_type(response_headers)
            normalized = {str(value).casefold() for value in allowed_content_types}
            if actual not in normalized:
                raise NetworkError(f"Unexpected content type: {actual or '<missing>'}.")
        return HttpResponse(status, response_headers, body, current)

    raise NetworkError("Unreachable redirect state.")


def install_rc44_source_transport() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import collector as collector_module

    previous_source_fetch = collector_module._source_fetch

    def source_fetch(url: str, **kwargs):
        try:
            return previous_source_fetch(url, **kwargs)
        except collector_module.NetworkError as exc:
            if not _is_access_error(exc):
                raise
            fallback_kwargs = dict(kwargs)
            return curl_public_fetch(
                url,
                headers=fallback_kwargs.pop("headers", None),
                timeout=float(fallback_kwargs.pop("timeout", 30.0)),
                max_bytes=int(fallback_kwargs.pop("max_bytes", 5 * 1024 * 1024)),
                allowed_content_types=fallback_kwargs.pop("allowed_content_types", None),
                max_redirects=int(fallback_kwargs.pop("max_redirects", 4)),
            )

    collector_module._source_fetch = source_fetch
    _INSTALLED = True
