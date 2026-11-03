"""2.3.3: bounded exact-article full-text recovery for thin commercial RSS.

Original publisher publication date, canonical URL, media and identity are
untouched. No cross-site/nearby article guessing or AI-created evidence.
"""
from __future__ import annotations
import re
from urllib.parse import urlsplit
from typing import Callable, Any
from ..article_extractor import extract_article_content
from ..network import fetch_url
from .editorial_hard_floor import facts

_STOP = {'with','that','this','from','over','into','more','news','about','their','could','would','what','when','where','launch','launches','says','will','brand','brands','advertising','marketing'}


def _title_agrees(a: str, b: str) -> bool:
    def stems(value):
        return {w[:6] for w in re.findall(r'[a-z]{5,}', value.casefold()) if w not in _STOP}
    left, right = stems(a), stems(b)
    return bool(len(left & right) >= 2 or (len(left) == 1 and left == right))


def enrich_exact_commercial_article_233(item: Any, source_url: str, *, fetcher: Callable = fetch_url) -> tuple[Any,str]:
    """No mutation unless publisher page identity and adequate text verified."""
    if len(facts(str(item.raw_text or ''))) >= 2:
        return item, 'already_sufficient'
    url = str(item.url or '').strip()
    try:
        p, s = urlsplit(url), urlsplit(str(source_url or ''))
        # Keep existing network global-IP-only SSRF protection as second layer.
        host = str(p.hostname or '').casefold().removeprefix('www.')
        source_host = str(s.hostname or '').casefold().removeprefix('www.')
        if (p.scheme != 'https' or p.username or p.password or p.port not in (None,443)
                or not host or host != source_host or not re.fullmatch(r'[a-z0-9.-]+',host)
                or len(url)>1400 or not p.path or p.path in {'/',''}):
            return item,'unsafe_or_unrelated_url'
        response = fetcher(url, timeout=7.0, max_bytes=900000,
                           allowed_content_types={'text/html','application/xhtml+xml'},
                           max_redirects=1, headers={'Accept':'text/html'})
        final = urlsplit(str(response.final_url or ''))
        if (response.status != 200 or final.scheme != 'https' or
                str(final.hostname or '').casefold().removeprefix('www.') != host or
                final.path.rstrip('/') != p.path.rstrip('/')):
            return item,'publisher_identity_mismatch'
        article = extract_article_content(response.body.decode('utf8','replace'),str(response.final_url))
        if not _title_agrees(str(item.title or ''), str(article.title or '')):
            return item,'title_identity_unverified'
        text = str(article.text or '').strip()
        if len(text) < 240 or len(facts(text)) < 2:
            return item,'fulltext_insufficient'
        item.raw_text = (str(item.raw_text or '').strip()+ '\n\n'
                         + 'ПОВНИЙ ТЕКСТ ТОГО САМОГО ВИДАВЦЯ (2.3.3):\n' + text[:5800])
        return item,'exact_publisher_fulltext_verified'
    except Exception:
        return item,'publisher_article_unavailable'
