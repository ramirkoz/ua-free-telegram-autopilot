from __future__ import annotations

from urllib.parse import urlsplit

KINDS = {"image", "video", "iframe"}


def encode_media(kind: str, url: str) -> str:
    kind = kind.strip().lower()
    value = url.strip()
    if kind not in KINDS:
        kind = "image"
    if kind == "image":
        return value
    return f"{kind}|{value}"


def decode_media(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if "|" in raw:
        prefix, url = raw.split("|", 1)
        if prefix in KINDS:
            return prefix, url.strip()
    return "image", raw


def valid_public_media(value: str) -> tuple[str, str] | None:
    kind, url = decode_media(value)
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    return kind, url
