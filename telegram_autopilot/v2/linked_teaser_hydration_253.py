"""2.2.53: bounded exact-link hydration of incomplete Telegram news teasers.

Only explicit author-supplied "Детальніше: https://..." links in a post
already rejected by the 2.2.52 core-facts rule are eligible. This is
a TEXT-ONLY evidence enrichment. It never borrows media, changes canonical
Telegram identity or overrides the original message provenance.
"""
from __future__ import annotations

import ipaddress
import json
import re
from urllib.parse import urlsplit

from ..article_extractor import extract_article_content
from ..models import CollectedArticle
from ..network import HttpResponse, NetworkError, fetch_url
from .editorial_reader_contract_252 import source_completeness_issue

_EXPLICIT_TARGET = re.compile(r"(?iu)\bдетальніше\s*:\s*(https://[^\s<>\"'«»\]\[]+)")
_END_PUNCT = ".,;!?)»"
_TEXT_LIMIT = 5200


def teaser_page_target(item: CollectedArticle) -> str:
    """A single explicit HTTPS link, never a guessed related/preview URL."""
    if not source_completeness_issue(item):
        return ""
    raw = str(item.raw_text or "")
    matches = _EXPLICIT_TARGET.findall(raw)
    if len(matches) != 1:
        return ""
    url = matches[0].rstrip(_END_PUNCT)
    if len(url) > 1400:
        return ""
    try:
        parts = urlsplit(url)
        host = str(parts.hostname or "").lower().rstrip(".")
        if (
            parts.scheme != "https"
            or parts.username or parts.password or parts.fragment
            or parts.port not in (None, 443)
            or not host or len(host) > 250 or "." not in host
            or host.startswith("www.") and host.count(".") < 2
            or host.endswith((".local", ".internal", ".localhost", ".onion", ".test", ".invalid", ".example"))
            or host in {"t.me", "telegram.me", "telegram.org", "www.t.me"}
            or not re.fullmatch(r"[a-z0-9.-]+", host)
        ):
            return ""
        try:
            ipaddress.ip_address(host)
            return ""  # no IP literals; network layer pins DNS to global IPs
        except ValueError:
            pass
        if any(not part or part.startswith("-") or part.endswith("-") for part in host.split(".")):
            return ""
        return url
    except ValueError:
        return ""


def _title_related(teaser: str, web_title: str) -> bool:
    """Conservative Ukrainian headline relation, not a semantic entailment."""
    def tokens(text: str) -> set[str]:
        stop = {"через", "нові", "назви", "які", "повний", "перелік",
                "стало", "зараз", "сьогодні", "детальніше", "адрес",
                "запоріжжі", "запоріжжя", "октобра", "жовтня"}
        return {
            word[:6] for word in re.findall(r"(?iu)[а-яіїєґa-z]{5,}", text[:300])
            if word not in stop
        }
    left, right = tokens(teaser), tokens(web_title)
    return bool(len(left & right) >= 2)


def hydrate_linked_teaser(
    item: CollectedArticle,
    *,
    fetcher=fetch_url,
) -> tuple[CollectedArticle, str]:
    """Return (possibly-enriched item, machine status); no exceptions escape.

    Network.fetch_url does public-IP-only DNS pinning for each redirect and
    rejects nonpublic endpoints/ports, URL credentials and non-HTML content.
    We additionally reject cross-site final redirects and unrelated articles.
    """
    target = teaser_page_target(item)
    if not target:
        return item, "not_eligible"
    try:
        response: HttpResponse = fetcher(
            target,
            timeout=8.0,
            max_bytes=800_000,
            allowed_content_types={"text/html", "application/xhtml+xml"},
            max_redirects=1,
            headers={"Accept": "text/html,application/xhtml+xml;q=0.9",
                     "Accept-Language": "uk-UA,uk;q=0.9"},
        )
        if response.status != 200 or urlsplit(response.final_url).hostname != urlsplit(target).hostname:
            return item, "redirect_or_http_mismatch"
        extracted = extract_article_content(
            response.body.decode("utf-8", errors="replace"), response.final_url
        )
        page_title = extracted.title.strip()
        if not page_title or not _title_related(item.title, page_title):
            return item, "article_identity_unverified"
        body = str(extracted.text or "").strip()
        if len(body) < 190:
            return item, "article_body_insufficient"
        original = str(item.raw_text or "")
        # Re-check 2.2.52's actual promise from the original source after
        # adding the exact linked page text: if it still lacks the answer,
        # fail closed rather than turn a naked teaser into a full news post.
        candidate = original + (
            "\n\nПОВНИЙ ТЕКСТ СТАТТІ З ПРЯМОГО ПОСИЛАННЯ "
            "(зовнішнє джерело, не текст Telegram-поста):\n"
            + body[:_TEXT_LIMIT]
        )
        from ..models import CollectedArticle as _Article
        shadow = _Article(
            external_id=item.external_id,
            title=item.title,
            url=item.url,
            raw_text=candidate,
            published_at=item.published_at,
            media_urls=list(item.media_urls or []),
        )
        if source_completeness_issue(shadow):
            return item, "promised_facts_still_missing"
        try:
            layout = json.loads(str(item.article_layout_json or "{}"))
            if not isinstance(layout, dict):
                layout = {}
        except (TypeError, ValueError):
            layout = {}
        layout["explicit_linked_article_253"] = {
            "status": "verified_source_link_text",
            "original_telegram_post": item.url,
            "linked_page_url": response.final_url,
            "linked_page_title": page_title[:250],
            "text_chars": min(len(body), _TEXT_LIMIT),
            "author_supplied_link": True,
            "imported_media": False,
            "identity_check": "two_distinctive_title_stems",
            "source_text_boundary": "explicit_linked_page_not_telegram_author",
        }
        item.raw_text = candidate
        item.article_layout_json = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
        # Never alter article.title, URL, published_at, source identity or media.
        return item, "hydrated"
    except (NetworkError, OSError, ValueError, UnicodeError):
        return item, "fetch_or_extract_unavailable"
    except Exception:
        # Even a malformed site cannot degrade the Telegram source collector.
        return item, "fetch_or_extract_unavailable"
