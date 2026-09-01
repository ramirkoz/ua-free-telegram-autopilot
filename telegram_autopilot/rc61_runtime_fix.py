from __future__ import annotations

import hashlib
import html as html_module
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

LOG = logging.getLogger("telegram_autopilot.rc61")
_INSTALLED = False

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_REJECT_PATH_PREFIXES = {
    "people", "person", "agencies", "agency", "brands", "brand", "companies", "company", "jobs", "job",
    "about", "advertise", "contact", "login", "register", "signup", "privacy", "terms", "search", "authors", "author",
}
_STRONG_EDITORIAL_PREFIXES = {"news", "campaigns", "campaign", "work", "works", "creative", "article", "articles", "story", "stories", "insights"}


def _same_host(a: str, b: str) -> bool:
    try:
        return (urlsplit(a).hostname or "").casefold().removeprefix("www.") == (urlsplit(b).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return False


def editorial_link_score(source_url: str, candidate_url: str, anchor_text: str) -> int:
    """Rank article-like links and reject profile/directory noise from page sources."""
    if not _same_host(source_url, candidate_url):
        return -1000
    try:
        path = urlsplit(candidate_url).path.strip("/")
    except ValueError:
        return -1000
    if not path:
        return -1000
    parts = [part.casefold() for part in path.split("/") if part]
    if not parts or parts[0] in _REJECT_PATH_PREFIXES:
        return -1000
    if any(part in {"tag", "tags", "category", "categories", "channel", "channels"} for part in parts[:2]):
        return -300
    text = " ".join(str(anchor_text or "").split())
    if len(text) < 18:
        return -200

    score = 0
    first = parts[0]
    if first in _STRONG_EDITORIAL_PREFIXES:
        score += 80
    if first == "campaigns" and len(parts) >= 2:
        score += 45
    if len(parts) >= 3 and parts[:2] == ["news", "view"]:
        score += 55
    elif first == "news" and len(parts) >= 2 and parts[1] not in {"channels", "channel", "latest"}:
        score += 40
    if len(parts) >= 2:
        score += 12
    if 25 <= len(text) <= 220:
        score += 8
    low = text.casefold()
    if low.startswith(("agency:", "brand:", "company:")):
        score -= 120
    return score


def _parse_textual_date(value: str) -> str:
    text = " ".join(str(value or "").split())
    month_names = "|".join(_MONTHS)
    patterns = (
        rf"(?i)\b(?:published|posted|updated)\s*(?:on)?\s*[:,-]?\s*(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{month_names})\s+20\d{{2}})\b",
        rf"(?i)\bby\s+[^\n<>]{{1,140}}?\s+on\s+(\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{month_names})\s+20\d{{2}})\b",
    )
    candidate = ""
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1)
            break
    if candidate:
        cleaned = re.sub(r"(?i)(\d)(st|nd|rd|th)\b", r"\1", candidate)
        match = re.fullmatch(rf"(?i)(\d{{1,2}})\s+({month_names})\s+(20\d{{2}})", cleaned)
        if match:
            try:
                dt = datetime(int(match.group(3)), _MONTHS[match.group(2).casefold()], int(match.group(1)), tzinfo=timezone.utc)
                if dt <= datetime.now(timezone.utc) + timedelta(days=1):
                    return dt.isoformat()
            except ValueError:
                pass
    return ""


def extract_page_published_at_rc61(html: str, url: str = "", *, previous=None) -> str:
    """Extend RC53 freshness extraction without weakening fail-closed semantics."""
    if previous is not None:
        try:
            existing = str(previous(html, url) or "")
        except Exception:
            existing = ""
        if existing:
            return existing

    raw = str(html or "")
    # Common JSON-LD variants beyond the exact double-quoted form handled by RC53.
    for pattern in (
        r"(?is)['\"]datePublished['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        r"(?is)['\"]dateCreated['\"]\s*:\s*['\"]([^'\"]+)['\"]",
    ):
        match = re.search(pattern, raw)
        if match:
            from . import rc53_hardening as rc53
            dt = rc53._parse_source_date(html_module.unescape(match.group(1)))
            if dt is not None and dt <= datetime.now(timezone.utc) + timedelta(days=1):
                return dt.isoformat()

    # shots.net and several creative-industry sites render the date as a human byline
    # rather than useful metadata, e.g. "by … on 1st September 2026".
    visible = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", raw)
    visible = html_module.unescape(re.sub(r"(?s)<[^>]+>", " ", visible))
    textual = _parse_textual_date(visible[:12000])
    if textual:
        return textual

    from . import rc53_hardening as rc53
    return rc53.infer_date_from_url(url)


def _safe_photo_bytes(item):
    """Return JPEG/PNG-safe PreparedMedia for Telegram sendPhoto.

    Imgix and similar CDNs can honor auto=format and return AVIF/WebP. Telegram's
    photo upload path is much less forgiving, so normalize unsupported image bytes
    locally instead of letting a perfectly good post die at the final API call.
    """
    mime = str(getattr(item, "mime_type", "") or "").casefold()
    if mime in {"image/jpeg", "image/png"}:
        return item
    data = bytes(getattr(item, "data", b"") or b"")
    if not data or not mime.startswith("image/"):
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGB")
            max_side = max(image.size or (0, 0))
            if max_side > 4096:
                scale = 4096.0 / float(max_side)
                image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
            payload = b""
            for quality in (90, 82, 72):
                out = io.BytesIO()
                image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
                payload = out.getvalue()
                if len(payload) <= 9_500_000:
                    break
            if not payload or len(payload) > 9_500_000:
                return None
            item.data = payload
            item.mime_type = "image/jpeg"
            item.width, item.height = image.size
            item.digest = hashlib.sha256(payload).hexdigest()
            return item
    except Exception as exc:
        LOG.debug("RC61 image normalization skipped url=%s: %s", getattr(item, "url", ""), exc)
        return None


def _collect_page_rc61(source):
    from . import collector
    from .models import CollectedArticle

    response = collector._source_fetch(
        source.url,
        max_bytes=5 * 1024 * 1024,
        allowed_content_types={"text/html", "application/xhtml+xml"},
        timeout=35,
    )
    html = response.body.decode("utf-8", errors="replace")
    parser = collector._LinkParser(response.final_url or source.url)
    parser.feed(html)
    base = response.final_url or source.url
    seen: set[str] = set()
    ranked: list[tuple[int, int, str, str]] = []
    for index, (url, text) in enumerate(parser.links):
        if url in seen:
            continue
        seen.add(url)
        score = editorial_link_score(base, url, text)
        if score <= 0:
            continue
        ranked.append((score, -index, url, text))
    ranked.sort(reverse=True)

    result = []
    for _score, _neg_index, url, text in ranked[:36]:
        item = collector._enrich_article(
            CollectedArticle(hashlib.sha256(url.encode("utf-8")).hexdigest(), text[:500], url, "", None, [])
        )
        if len(item.raw_text) < 250:
            continue
        result.append(item)
        if len(result) >= 24:
            break
    return result


def _requeue_recent_freshness_rejects(db, channel_id: int) -> int:
    marker = f"rc61_freshness_recovery_done:{int(channel_id)}"
    if db.get_state(marker, "0") == "1":
        return 0
    rescued = 0
    with db.connect() as con:
        rows = con.execute(
            """SELECT a.id,a.source_id,a.url,s.url AS source_url,s.kind,s.priority
               FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.status='rejected'
                 AND a.reject_reason LIKE 'RC53 FRESHNESS:%'
                 AND datetime(a.discovered_at) >= datetime('now','-48 hours')
               ORDER BY s.priority DESC,a.id DESC LIMIT 160""",
            (int(channel_id),),
        ).fetchall()
        per_source: dict[int, int] = {}
        for row in rows:
            if str(row["kind"] or "") != "page":
                continue
            source_id = int(row["source_id"]) if "source_id" in row.keys() else 0
            if per_source.get(source_id, 0) >= 3:
                continue
            if editorial_link_score(str(row["source_url"] or ""), str(row["url"] or ""), "Recovered editorial article") <= 0:
                continue
            con.execute(
                """UPDATE articles SET status='new',reject_reason=NULL,last_error=NULL,
                          processing_started_at=NULL,article_layout_json=''
                   WHERE id=?""",
                (int(row["id"]),),
            )
            per_source[source_id] = per_source.get(source_id, 0) + 1
            rescued += 1
    db.set_state(marker, "1")
    return rescued


def install_rc61_runtime_fix() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import collector, media_pipeline, rc53_hardening as rc53, service as service_module
    from .database import Database

    previous_date = rc53.extract_page_published_at
    rc53.extract_page_published_at = lambda html, url="": extract_page_published_at_rc61(html, url, previous=previous_date)

    previous_collect = collector.collect_source

    def collect_source_rc61(source):
        if str(getattr(source, "kind", "")) == "page":
            try:
                return _collect_page_rc61(source)
            except Exception:
                # Preserve RC60 fallback/error semantics for sites where ranking cannot run.
                return previous_collect(source)
        return previous_collect(source)

    collector.collect_source = collect_source_rc61
    service_module.collect_source = collect_source_rc61

    previous_probe = media_pipeline._probe_image

    def probe_rc61(item, *, marketing_context: bool = False):
        resolved = previous_probe(item, marketing_context=marketing_context)
        if resolved is None:
            return None
        return _safe_photo_bytes(resolved)

    media_pipeline._probe_image = probe_rc61

    def pending_rc61(self, channel_id: int, limit: int = 20):
        rescued = _requeue_recent_freshness_rejects(self, int(channel_id))
        if rescued:
            LOG.info("RC61 freshness recovery channel_id=%s rescued=%s", channel_id, rescued)
        scan_limit = max(240, min(800, int(limit) * 16))
        with self.connect() as con:
            rows = con.execute(
                """SELECT a.*,s.name AS source_name,s.priority AS source_priority,c.max_age_hours AS channel_max_age
                   FROM articles a
                   JOIN sources s ON s.id=a.source_id
                   JOIN channels c ON c.id=a.channel_id
                   WHERE a.channel_id=? AND (
                     a.status='new' OR (
                       a.status='retry' AND (
                         a.next_retry_at IS NULL OR a.next_retry_at='' OR datetime(a.next_retry_at) <= datetime('now')
                       )
                     )
                   )
                   ORDER BY
                     CASE WHEN a.status='new' THEN 0 ELSE 1 END,
                     s.priority DESC,
                     CASE WHEN a.status='new' THEN a.id END DESC,
                     CASE WHEN a.status='retry' THEN datetime(COALESCE(NULLIF(a.next_retry_at,''),a.discovered_at)) END ASC,
                     a.id DESC
                   LIMIT ?""",
                (int(channel_id), scan_limit),
            ).fetchall()

        ready = []
        now = datetime.now(timezone.utc)
        for row in rows:
            parsed = rc53._parse_source_date(str(row["source_published_at"] or ""))
            if parsed is not None:
                max_age = max(1, int(row["channel_max_age"] or 24))
                if parsed < now - timedelta(hours=max_age):
                    self.update_article(
                        int(row["id"]), status="rejected",
                        reject_reason=f"RC61 FRESHNESS PREFILTER: матеріал старіший за {max_age} год.; AI/медіа не запускаються.",
                    )
                    continue
            # Missing dates are allowed through once so service can re-fetch the actual
            # article page with the stronger RC61 date extractor. If still unknown,
            # strict fail-closed remains in service.
            ready.append(row)
            if len(ready) >= max(1, int(limit)):
                break
        return ready

    Database.pending_articles = pending_rc61
    _INSTALLED = True
    LOG.info(
        "RC61 installed: stale prefilter, freshness recovery, editorial page-link ranking, "
        "stronger published-date extraction and Telegram-safe image normalization"
    )
