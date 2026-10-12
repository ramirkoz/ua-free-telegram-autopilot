"""Optional, bounded source-owned article reader for the 2.1.1 pipeline.

Never invoked automatically. A calling channel/source adapter must opt in explicitly.
Reader text remains untrusted source material and still passes normal editorial QA.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlsplit
import ipaddress
import re

from .network import fetch_url, NetworkError


@dataclass(frozen=True)
class ReaderResult:
    text: str
    original_url: str
    reader: str
    reader_url: str


def eligible_article_url(url: str) -> bool:
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    host = (p.hostname or "").casefold().rstrip(".")
    if p.scheme not in {"http", "https"} or not host or p.username or p.password:
        return False
    if p.port not in {None, 80, 443}:
        return False
    if host in {"localhost", "t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return False
    if host.endswith((".local", ".internal", ".localhost", ".onion")):
        return False
    try:
        ipaddress.ip_address(host)
        return False  # Never send raw IP targets to the external reader.
    except ValueError:
        pass
    if not ("." in host and len(host) <= 253):
        return False
    return True


def jina_reader_url(original_url: str) -> str:
    if not eligible_article_url(original_url):
        raise ValueError("Unsupported or unsafe source URL")
    return "https://r.jina.ai/" + quote(original_url, safe=":/?&=%+-._~")


def read_with_jina(
    original_url: str, *, enabled: bool = False, min_chars: int = 250, timeout: float = 12.0
) -> ReaderResult | None:
    """Explicit opt-in only; no feed discovery, login or publication side effects.

    Bounded response, HTTPS endpoint, no private URL access. The returned content
    must be treated as unverified and may not establish source identity by itself.
    """
    if not enabled:
        return None
    reader_url = jina_reader_url(original_url)
    response = fetch_url(
        reader_url,
        max_bytes=512 * 1024,
        timeout=max(3.0, min(15.0, float(timeout))),
        headers={"Accept": "text/plain", "X-Return-Format": "markdown"},
        allowed_content_types={"text/plain", "text/markdown", "text/x-markdown"},
    )
    value = response.body.decode("utf-8", "replace").strip()
    if len(value) < max(120, int(min_chars)):
        return None
    # Do not trust Jina metadata as an article/source URL. Keep original binding.
    value = re.sub(r"(?m)^(?:Title|URL Source|Markdown Content):\s*", "", value).strip()
    return ReaderResult(
        text=value[:30000], original_url=original_url,
        reader="jina", reader_url=reader_url,
    )
