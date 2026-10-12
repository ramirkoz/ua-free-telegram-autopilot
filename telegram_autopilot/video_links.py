"""Trusted, article-scoped video embed normalization for 2.1.2.

Only URLs discovered in article/main media blocks or source-bound JSON-LD
may be passed to publication. No page-wide search or related-story scraping.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit


def canonical_video_url(url: str) -> str:
    try:
        p = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if p.scheme not in {"https", "http"} or p.username or p.password:
        return ""
    host = (p.hostname or "").casefold().rstrip(".")
    path = p.path.strip("/")
    video_id = ""
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}:
        chunks = path.split("/")
        if chunks[0] in {"embed", "shorts", "live", "v"} and len(chunks) > 1:
            video_id = chunks[1]
        elif chunks[0] == "watch":
            video_id = parse_qs(p.query).get("v", [""])[0]
    elif host in {"youtu.be", "www.youtu.be"}:
        video_id = path.split("/")[0]
    if video_id and len(video_id) == 11 and all(c.isalnum() or c in "_-" for c in video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    if host in {"player.vimeo.com", "vimeo.com", "www.vimeo.com"}:
        parts = path.split("/")
        ident = parts[-1] if parts else ""
        if ident.isdigit() and len(ident) <= 20:
            return f"https://vimeo.com/{ident}"
    return ""


def scoped_video_links(layout: dict, max_items: int = 10) -> list[str]:
    result: list[str] = []
    for block in layout.get("blocks", []):
        if not isinstance(block, dict) or block.get("type") != "media":
            continue
        if block.get("kind") not in {"iframe", "video"}:
            continue
        url = canonical_video_url(str(block.get("url") or ""))
        if url and url not in result:
            result.append(url)
        if len(result) >= max_items:
            break
    return result
