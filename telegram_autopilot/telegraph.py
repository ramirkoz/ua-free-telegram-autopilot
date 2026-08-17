from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

from .network import NetworkError, fetch_url
from .media import valid_public_media
from .media_pipeline import PreparedArticleMedia, PreparedMedia


class TelegraphError(RuntimeError):
    def __init__(self, message: str, *, outcome_unknown: bool = False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


@dataclass(frozen=True, slots=True)
class TelegraphPage:
    path: str
    url: str
    title: str
    media_count: int


_MEDIA_MARKER_RE = re.compile(r"\[\[MEDIA_(\d+)\]\]")


def _post(method: str, fields: dict[str, str], *, write_is_irreversible: bool = False, timeout: float = 45.0) -> dict[str, object]:
    body = urlencode(fields).encode("utf-8")
    try:
        response = fetch_url(
            f"https://api.telegra.ph/{method}", method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body=body, max_bytes=2 * 1024 * 1024,
            allowed_content_types={"application/json", "text/javascript"}, timeout=timeout,
            max_redirects=0, allow_http_errors=True,
        )
    except NetworkError as exc:
        raise TelegraphError(f"Telegraph network error: {exc}", outcome_unknown=write_is_irreversible) from exc
    payload = response.json() if response.body else {}
    if not isinstance(payload, dict):
        raise TelegraphError("Telegraph повернув неправильний JSON.", outcome_unknown=write_is_irreversible)
    if response.status >= 400 or payload.get("ok") is not True:
        raise TelegraphError(f"Telegraph: {payload.get('error') or f'HTTP {response.status}'}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise TelegraphError("Telegraph не повернув result.", outcome_unknown=write_is_irreversible)
    return result


def create_account(short_name: str = "ua_free_autopilot") -> str:
    result = _post("createAccount", {"short_name": (short_name.strip() or "ua_free_autopilot")[:32], "author_name": ""})
    token = str(result.get("access_token") or "").strip()
    if not token:
        raise TelegraphError("Telegraph створив акаунт без access_token.")
    return token


def test_account(access_token: str) -> str:
    token = access_token.strip()
    if not token:
        raise TelegraphError("Telegraph token ще не створено.")
    result = _post("getAccountInfo", {"access_token": token, "fields": '["short_name","page_count"]'}, timeout=20)
    return str(result.get("short_name") or "Telegraph")


def _source_label(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "джерело").removeprefix("www.")
    except ValueError:
        return "джерело"


def _legacy_prepared(media_urls: list[str]) -> PreparedArticleMedia:
    body: list[PreparedMedia] = []
    for idx, raw in enumerate(media_urls[:12], start=1):
        parsed = valid_public_media(str(raw))
        if parsed:
            kind, url = parsed
            body.append(PreparedMedia(idx, kind, url, position=min(.95, .75 + idx * .03)))
    return PreparedArticleMedia(None, body)


def _media_node(item: PreparedMedia, caption: str = "") -> dict[str, object]:
    tag = "img" if item.kind == "image" else "video" if item.kind == "video" else "iframe"
    children: list[object] = [{"tag": tag, "attrs": {"src": item.url[:1800]}}]
    clean_caption = " ".join(caption.split()).strip()
    if clean_caption:
        children.append({"tag": "figcaption", "children": [clean_caption[:1000]]})
    return {"tag": "figure", "children": children}


def _paragraphs(full_text: str) -> list[str]:
    return [" ".join(part.split()) for part in full_text.split("\n") if part.strip()]


def _build_nodes(
    full_text: str,
    prepared_media: PreparedArticleMedia | list[str],
    source_url: str,
    media_captions: dict[int, str] | None = None,
) -> tuple[list[object], int]:
    captions = media_captions or {}
    if isinstance(prepared_media, list):
        prepared_media = _legacy_prepared(prepared_media)
    body_map = {item.index: item for item in prepared_media.body}
    nodes: list[object] = []
    used: set[int] = set()
    marker_seen = False

    for paragraph in _paragraphs(full_text):
        cursor = 0
        matches = list(_MEDIA_MARKER_RE.finditer(paragraph))
        if not matches:
            nodes.append({"tag": "p", "children": [paragraph]})
            continue
        marker_seen = True
        for match in matches:
            before = paragraph[cursor:match.start()].strip()
            if before:
                nodes.append({"tag": "p", "children": [before]})
            idx = int(match.group(1))
            item = body_map.get(idx)
            if item and idx not in used:
                nodes.append(_media_node(item, captions.get(idx, "")))
                used.add(idx)
            cursor = match.end()
        after = paragraph[cursor:].strip()
        if after:
            nodes.append({"tag": "p", "children": [after]})

    if not marker_seen and prepared_media.body:
        # Legacy/retry AI text has no markers. Rebuild using each media item's
        # original relative position instead of RC6's arbitrary every-3-paragraph rule.
        paras = [node for node in nodes if isinstance(node, dict) and node.get("tag") == "p"]
        if paras:
            rebuilt: list[object] = []
            buckets: dict[int, list[PreparedMedia]] = {}
            for item in prepared_media.body:
                pos = max(0, min(len(paras), round(item.position * len(paras))))
                buckets.setdefault(pos, []).append(item)
            for idx, node in enumerate(paras):
                for item in buckets.get(idx, []):
                    rebuilt.append(_media_node(item, captions.get(item.index, "")))
                    used.add(item.index)
                rebuilt.append(node)
            for item in buckets.get(len(paras), []):
                rebuilt.append(_media_node(item, captions.get(item.index, "")))
                used.add(item.index)
            nodes = rebuilt

    # Featured image is Telegraph fallback only when the source exposed no body
    # editorial figures. This prevents the common og:image + same inline image duplicate.
    if not prepared_media.body and prepared_media.featured:
        nodes.insert(0, _media_node(prepared_media.featured, ""))

    # Any validated body media that AI accidentally omitted is appended in original
    # order rather than silently lost. Normally the marker validator prevents this.
    for item in prepared_media.body:
        if item.index not in used:
            nodes.append(_media_node(item, captions.get(item.index, "")))
            used.add(item.index)

    if source_url:
        nodes.append({"tag": "hr"})
        nodes.append({
            "tag": "p",
            "children": [
                {"tag": "strong", "children": ["Джерело: "]},
                {"tag": "a", "attrs": {"href": source_url[:2000]}, "children": [_source_label(source_url)]},
            ],
        })

    encoded = json.dumps(nodes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 60 * 1024:
        while len(encoded) > 60 * 1024:
            media_positions = [i for i, node in enumerate(nodes) if isinstance(node, dict) and node.get("tag") == "figure"]
            if not media_positions:
                raise TelegraphError("Telegraph-стаття перевищує ліміт 64 KB.")
            del nodes[media_positions[-1]]
            encoded = json.dumps(nodes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    media_count = sum(1 for node in nodes if isinstance(node, dict) and node.get("tag") == "figure")
    return nodes, media_count


def create_page(
    access_token: str,
    *,
    title: str,
    full_text: str,
    media_urls: list[str] | None = None,
    prepared_media: PreparedArticleMedia | None = None,
    media_captions: dict[int, str] | None = None,
    source_url: str,
    author_name: str,
    author_url: str = "",
) -> TelegraphPage:
    token = access_token.strip()
    if not token:
        raise TelegraphError("Telegraph access token відсутній.")
    clean_title = " ".join(title.split()).strip()[:256]
    if not clean_title:
        raise TelegraphError("Порожній заголовок Telegraph.")
    prepared = prepared_media or _legacy_prepared(media_urls or [])
    nodes, media_count = _build_nodes(full_text, prepared, source_url, media_captions)
    fields = {
        "access_token": token,
        "title": clean_title,
        "author_name": " ".join(author_name.split())[:128],
        "content": json.dumps(nodes, ensure_ascii=False, separators=(",", ":")),
        "return_content": "false",
    }
    if author_url:
        fields["author_url"] = author_url[:512]
    result = _post("createPage", fields, write_is_irreversible=True, timeout=50)
    path, url = str(result.get("path") or "").strip(), str(result.get("url") or "").strip()
    if not path or not url:
        raise TelegraphError("Telegraph створив сторінку, але не повернув URL.", outcome_unknown=True)
    return TelegraphPage(path=path, url=url, title=clean_title, media_count=media_count)
