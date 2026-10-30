"""2.2.62: date only from the exact fetched article page, never from discovery time.

Page listings previously produced CollectedArticle(..., published_at=None, ...)
even after a successful per-article fetch; strict day/start fence then discarded
every page item as SOURCE_DATE_UNVERIFIED. Only an exact article's own
structured publication metadata may supply a date. No timezone = no date;
unrelated JSON-LD cards, meta updates, site homepage and redirects never count.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit


_ARTICLE_TYPES = {"article", "newsarticle", "blogposting", "reportagenewsarticle", "analysisnewsarticle"}


def _identity(url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(str(url or ""))
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return "", ""
        host = parts.hostname.lower().removeprefix("www.")
        path = (parts.path or "/").rstrip("/") or "/"
        return host, path
    except ValueError:
        return "", ""


def _aware_date(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError, OverflowError):
            return ""
    if date.tzinfo is None:
        return ""  # never assume a publisher's timezone
    return date.isoformat()


def _nodes(value):
    if isinstance(value, list):
        for child in value[:100]:
            yield from _nodes(child)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, (list, dict)):
            yield from _nodes(graph)


def _article_url(node: dict) -> str:
    for key in ("url", "mainEntityOfPage"):
        value = node.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for field in ("@id", "url"):
                if isinstance(value.get(field), str):
                    return value[field]
    return ""


class _ExactArticleDateHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta_dates: list[str] = []
        self.canonical = ""
        self.script_depth = 0
        self.script_content: list[str] = []
        self.script_values: list[str] = []

    def handle_starttag(self, tag, attrs):
        pairs = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag == "meta":
            kind = (pairs.get("property") or pairs.get("name") or "").lower()
            if kind in {"article:published_time", "datepublished", "citation_publication_date"}:
                value = pairs.get("content") or ""
                if value:
                    self.meta_dates.append(value)
        elif tag == "link" and "canonical" in (pairs.get("rel") or "").lower().split():
            self.canonical = pairs.get("href") or self.canonical
        elif tag == "script" and pairs.get("type", "").split(";", 1)[0].strip().lower() == "application/ld+json":
            self.script_depth = 1
            self.script_content = []

    def handle_data(self, data):
        if self.script_depth and sum(map(len, self.script_content)) + len(data) <= 160_000:
            self.script_content.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script_depth:
            self.script_depth = 0
            if self.script_content:
                self.script_values.append("".join(self.script_content))
            self.script_content = []


def published_date_from_article_html(html: str, requested_article_url: str) -> str:
    """Fail closed unless the publisher supplied a timezone-aware publication date.

    Listing timestamps, updated dates and the current fetch time are forbidden.
    A canonical link to a different article invalidates the metadata.
    """
    target = _identity(requested_article_url)
    if not target[0] or target[1] == "/":
        return ""
    parser = _ExactArticleDateHTML()
    try:
        parser.feed(str(html or "")[:1_800_000])
        parser.close()
    except (ValueError, TypeError):
        return ""
    if parser.canonical and _identity(parser.canonical) != target:
        return ""
    values: list[str] = [_aware_date(x) for x in parser.meta_dates]
    candidates: list[tuple[str, str]] = []
    for script in parser.script_values[:12]:
        try:
            structure = json.loads(script)
        except (ValueError, TypeError):
            continue
        for item in _nodes(structure):
            types = item.get("@type")
            kinds = types if isinstance(types, list) else [types]
            if not any(str(kind or "").lower() in _ARTICLE_TYPES for kind in kinds):
                continue
            owned = _article_url(item)
            if owned and _identity(owned) != target:
                continue
            date = _aware_date(item.get("datePublished", ""))
            if date:
                candidates.append((owned, date))
    # When JSON-LD lacks URL, require exactly one article node to avoid
    # adopting timestamps from a list of related stories.
    explicit = [date for owner, date in candidates if owner]
    implicit = [date for owner, date in candidates if not owner]
    values.extend(explicit or (implicit if len(implicit) == 1 else []))
    aware = [datetime.fromisoformat(x) for x in values if x]
    if not aware:
        return ""
    earliest, latest = min(aware), max(aware)
    if abs((latest.astimezone(timezone.utc) - earliest.astimezone(timezone.utc)).total_seconds()) > 300:
        return ""  # conflicting source metadata
    return earliest.isoformat()
