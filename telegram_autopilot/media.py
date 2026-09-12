from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

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


def media_identity(kind: str, url: str) -> str:
    """Return a conservative identity used only for de-duplicating media variants.

    The same source image is often exposed several times with cache/signature/size
    parameters or WordPress-style ``-300x200`` filenames.  Exact-URL de-duplication
    therefore produced galleries made from several visual copies of one picture.

    We keep semantic query parameters (id/file/photo/video/media/url/src) but ignore
    presentation/cache parameters.  Distinct paths remain distinct media items.
    """
    raw_kind = str(kind or "image").strip().casefold()
    raw_url = str(url or "").strip()
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return f"{raw_kind}|{raw_url.casefold()}"

    host = (parts.hostname or "").casefold()
    path = unquote(parts.path or "").casefold()
    # Common resized variants of the same source image.
    path = re.sub(r"-(?:\d{2,5})x(?:\d{2,5})(?=\.[a-z0-9]{2,6}$)", "", path)
    path = re.sub(r"[_-](?:w|width|h|height)[_-]?\d{2,5}(?=\.[a-z0-9]{2,6}$)", "", path)

    semantic_keys = {"id", "file", "photo", "video", "media", "url", "src"}
    semantic: list[tuple[str, str]] = []
    try:
        for key, value in parse_qsl(parts.query, keep_blank_values=False):
            k = str(key).casefold()
            if k in semantic_keys:
                semantic.append((k, str(value).strip()))
    except Exception:
        semantic = []
    semantic.sort()
    query = "&".join(f"{k}={v}" for k, v in semantic)
    normalized = urlunsplit((parts.scheme.casefold(), host, path, query, ""))
    return f"{raw_kind}|{normalized}"
