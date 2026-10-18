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


# A path segment that only carries rendering instructions for an image CDN, e.g.
# ``t:0,l:420,cw:1080,ch:1080,q:80,w:1080`` or ``w_800,c_fill,q_auto`` or ``1200x630``.
_TRANSFORM_PAIR = r"[a-z]{1,8}[:_=][a-z0-9.\-]{1,20}"
_TRANSFORM_SEGMENT_RE = re.compile(rf"^(?:{_TRANSFORM_PAIR})(?:,{_TRANSFORM_PAIR})*$|^\d{{2,5}}x\d{{2,5}}$")
_TRANSFORM_WORDS = {"fit-in", "resize", "resized", "crop", "cropped", "thumbnail", "thumbnails", "filters"}
_RENDITION_SUFFIXES = (
    re.compile(r"-\d{2,5}x\d{2,5}$"),                # WordPress style -1200x675
    re.compile(r"-\d{3,4}-\d{2,3}$"),               # width-quality renditions -1920-80
    re.compile(r"[_-](?:w|width|h|height)[_-]?\d{2,5}$"),
    re.compile(r"@\d(?:\.\d)?x$"),                  # retina @2x
    re.compile(r"-scaled$"),
)
_OPAQUE_ID_RE = re.compile(r"^(?=.*\d)(?=.*[a-z])[a-z0-9]{12,64}$", re.I)


def canonical_asset_key(url: str) -> str:
    """Return one key for every rendition of the same uploaded image asset.

    Universal source-level rule (no per-site code): CDN transform segments and
    rendition suffixes describe how an asset is drawn, not which asset it is.
    Opaque upload identifiers (long random tokens) are unique per host, so their
    renditions match even when the CDN serves them from different directories.
    Readable file names keep their directory, so ``/2026/09/photo.jpg`` and
    ``/2026/10/photo.jpg`` remain different assets.
    """
    raw = str(url or "").strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.casefold()
    host = (parts.hostname or "").casefold()
    segments = [s for s in unquote(parts.path or "").split("/") if s]
    if not segments:
        return f"{host}/"
    name = segments[-1]
    directories = [
        s for s in segments[:-1]
        if not _TRANSFORM_SEGMENT_RE.match(s.casefold()) and s.casefold() not in _TRANSFORM_WORDS
    ]
    stem = name
    while "." in stem and len(stem.rsplit(".", 1)[1]) <= 5:
        stem = stem.rsplit(".", 1)[0]   # also strips double extensions such as .jpg.webp
    changed = True
    while changed:
        changed = False
        for pattern in _RENDITION_SUFFIXES:
            shorter = pattern.sub("", stem)
            if shorter != stem and shorter:
                stem, changed = shorter, True
    if _OPAQUE_ID_RE.match(stem):
        return f"{host}/~{stem}"
    return f"{host}/{'/'.join(d.casefold() for d in directories)}/{stem.casefold()}"
