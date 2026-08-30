from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Channel, Decision
from .secrets_store import load_secrets

LOG = logging.getLogger("telegram_autopilot.rc53")
_INSTALLED = False

_TRACKING_PREFIXES = (
    "utm_", "itm_", "pk_", "vero_", "oly_", "mc_",
)
_TRACKING_KEYS = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "gbraid", "wbraid",
    "igshid", "mkt_tok", "ref_src", "ref_url", "spm", "campaignid",
}
_PENDING_STATUSES = {"new", "retry", "processing"}
_LT_REPEAT_SECONDS = 10 * 60

_PUBLISHED_META_KEYS = {
    "article:published_time", "article:published", "datepublished", "date_published",
    "publishdate", "publish_date", "pubdate", "date", "dc.date", "dcterms.date",
    "parsely-pub-date", "sailthru.date",
}

_CTRL_UA_HARD_TITLE_PATTERNS = (
    r"\btim curry\b", r"\bplay-?offs?\b", r"\b(nba|nfl|mlb|nhl|premier league)\b",
    r"\b(actor|actress|celebrity|movie|tv show|streaming guide)\b",
    r"\b(recipe|fashion|beauty|horoscope|travel deals?)\b",
    r"\b(opinion|commentary|community guidelines?|rules for posting|how to comment)\b",
)
_MARKETING_HR_TITLE_PATTERNS = (
    r"\bappoint(?:s|ed|ment)?\b", r"\bhires?\b", r"\bpromot(?:es|ed|ion)\b",
    r"\bjoins?\b.{0,45}\bas\b", r"\bnames?\b.{0,45}\bas\b",
    r"\bsteps? down\b", r"\bresigns?\b", r"\bleaves?\b.{0,35}\b(company|agency|brand|role)\b",
    r"\b(new|incoming)\s+(chief|cmo|cco|ceo|cfo|coo|president|director|vp|vice president)\b",
    r"\bchief (marketing|creative|brand|growth|communications?) officer\b",
    r"\bexecutive (hire|appointment|shuffle|move)\b", r"\bleadership (change|shuffle|appointment)\b",
)

_BAD_OUTPUT_PATTERNS = (
    (re.compile(r"\bплей-оф\s+ного\b", re.I), "зламана форма «плей-оф ного»"),
    (re.compile(r"\bструктурн\w*\s+діоксид\w*\b", re.I), "підозріла калька «структурні діоксиди»"),
    (re.compile(r"\b(?:плей-оф|плейоф)\s+\w{0,8}ного\b", re.I), "зламана відмінкова конструкція після «плей-оф»"),
)


@dataclass(frozen=True, slots=True)
class ReactionHealth:
    state: str
    ready: bool
    message: str


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else str(value)


def normalize_url_rc53(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw[:2000]
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        low = key.casefold()
        if low in _TRACKING_KEYS or any(low.startswith(prefix) for prefix in _TRACKING_PREFIXES):
            continue
        query.append((key, val))
    query.sort(key=lambda item: (item[0].casefold(), item[1]))
    host = (parts.hostname or "").casefold().rstrip(".")
    netloc = host
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and not (
        (parts.scheme.casefold() == "http" and port == 80)
        or (parts.scheme.casefold() == "https" and port == 443)
    ):
        netloc += f":{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), netloc, path, urlencode(query, doseq=True), ""))[:2000]


def _parse_source_date(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if "," in text or "GMT" in text.upper():
            dt = parsedate_to_datetime(text)
        else:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if dt.year < 2000 or dt.year > 2100:
        return None
    return dt


def infer_date_from_url(url: str) -> str:
    try:
        path = urlsplit(str(url or "")).path
    except ValueError:
        return ""
    patterns = (
        r"/(20\d{2})/([01]?\d)/([0-3]?\d)(?:/|$)",
        r"/(20\d{2})-([01]\d)-([0-3]\d)(?:/|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, path)
        if not match:
            continue
        try:
            dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt <= datetime.now(timezone.utc) + timedelta(days=1):
            return dt.isoformat()
    return ""


class _PublishedDateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(k).casefold(): str(v or "").strip() for k, v in attrs}
        if tag.casefold() == "meta":
            key = (
                values.get("property") or values.get("name") or values.get("itemprop")
                or values.get("http-equiv") or ""
            ).casefold()
            content = values.get("content", "")
            if content and (key in _PUBLISHED_META_KEYS or ("publish" in key and "date" in key)):
                self.candidates.append((100 if "published" in key else 90, content))
        elif tag.casefold() == "time":
            value = values.get("datetime", "")
            context = " ".join((values.get("itemprop", ""), values.get("class", ""), values.get("id", ""))).casefold()
            if value and ("publish" in context or "date" in context or "time" in context):
                self.candidates.append((70, value))


def extract_page_published_at(html: str, url: str = "") -> str:
    parser = _PublishedDateParser()
    try:
        parser.feed(str(html or ""))
        parser.close()
    except Exception:
        pass
    for match in re.finditer(
        r'(?is)"datePublished"\s*:\s*"([^"]+)"|"dateCreated"\s*:\s*"([^"]+)"',
        str(html or ""),
    ):
        value = next((group for group in match.groups() if group), "")
        if value:
            parser.candidates.append((95 if "datePublished" in match.group(0) else 60, value))
    for _priority, value in sorted(parser.candidates, key=lambda item: -item[0]):
        dt = _parse_source_date(value)
        if dt is not None and dt <= datetime.now(timezone.utc) + timedelta(days=1):
            return dt.isoformat()
    return infer_date_from_url(url)


def operator_reaction_breakdown(message: Any) -> tuple[int, int, int, int, int, int, int]:
    """Read only reactions chosen by the connected operator account.

    Aggregate audience reaction counts are deliberately ignored. The operator's
    own 👍/👎/🔥 are editorial labels, and Telegram Premium may mark two or more
    ReactionCount rows as chosen on the same message.
    """
    from . import rc51_feedback as rc51

    views = max(0, int(getattr(message, "views", 0) or 0))
    forwards = max(0, int(getattr(message, "forwards", 0) or 0))
    replies_box = getattr(message, "replies", None)
    replies = max(0, int(getattr(replies_box, "replies", 0) or 0))
    likes = dislikes = fires = other = 0
    box = getattr(message, "reactions", None)
    for item in (getattr(box, "results", None) or []):
        chosen_order = getattr(item, "chosen_order", None)
        chosen = bool(getattr(item, "chosen", False)) or chosen_order is not None
        if not chosen:
            continue
        emoji = rc51._reaction_emoji(getattr(item, "reaction", None))
        if emoji == "👍":
            likes = 1
        elif emoji == "👎":
            dislikes = 1
        elif emoji == "🔥":
            fires = 1
        else:
            other += 1
    return views, forwards, replies, likes, dislikes, fires, other


def reaction_health() -> ReactionHealth:
    try:
        secret = load_secrets()
    except Exception as exc:
        return ReactionHealth("secrets_error", False, f"Сховище Telegram-секретів недоступне: {exc}")
    api_id = int(getattr(secret, "telegram_api_id", 0) or 0)
    api_hash = str(getattr(secret, "telegram_api_hash", "") or "").strip()
    phone = str(getattr(secret, "telegram_phone", "") or "").strip()
    session = str(getattr(secret, "telegram_user_session", "") or "").strip()
    if not api_id or not api_hash or not phone:
        return ReactionHealth(
            "credentials_missing", False,
            "Потрібні Telegram API ID, API Hash і телефон. Без MTProto реакції не читаються.",
        )
    if not session:
        return ReactionHealth(
            "authorization_required", False,
            "Telegram user-session не авторизована. 👍/👎/🔥 зараз НЕ впливають на навчання.",
        )
    try:
        import telethon  # noqa: F401
    except Exception:
        return ReactionHealth("telethon_missing", False, "Telethon відсутній у runtime; реакції не читаються.")
    return ReactionHealth("ready", True, "MTProto user-session збережена; реакційний контур готовий до читання.")


def semantic_output_blockers(source_text: str, output: str) -> tuple[str, ...]:
    text = str(output or "")
    issues: list[str] = []
    for pattern, label in _BAD_OUTPUT_PATTERNS:
        if pattern.search(text):
            issues.append(label)
    source = str(source_text or "").casefold()
    low = text.casefold()
    if ("epoxy" in source or "epoxies" in source) and "діоксид" in low:
        issues.append("epoxy/epoxies помилково перетворено на «діоксид»")
    return tuple(dict.fromkeys(issues))


def _channel_kind(channel: Channel) -> str:
    text = f"{getattr(channel, 'name', '')} {getattr(channel, 'editorial_profile', '')}".casefold()
    if "продано" in text or "marketing" in text or "реклам" in text or "brand" in text:
        return "marketing"
    if "ctrl+ua" in text or "ctrl ua" in text:
        return "ctrlua"
    return "generic"


def editorial_hard_reject(channel: Channel, article: Mapping[str, Any] | Any) -> str:
    title = " ".join(_row_value(article, "title").split()).casefold()
    if not title:
        return ""
    kind = _channel_kind(channel)
    if kind == "marketing":
        if any(re.search(pattern, title, flags=re.I) for pattern in _MARKETING_HR_TITLE_PATTERNS):
            return "RC53 HARD VETO: кадрова перестановка/призначення не є матеріалом для ПРОДАНО!."
    elif kind == "ctrlua":
        if any(re.search(pattern, title, flags=re.I) for pattern in _CTRL_UA_HARD_TITLE_PATTERNS):
            return "RC53 HARD VETO: матеріал явно поза технологічним/науковим профілем CTRL+UA."
    return ""


def _is_quality_prompt(prompt: str) -> bool:
    text = str(prompt or "").lstrip()
    return (
        text.startswith("Ты выпускающий редактор Telegram.")
        or text.startswith("Ти пишеш ФІНАЛЬНИЙ пост для Telegram")
        or text.startswith("Ты выпускающий редактор Telegram-канала.")
        or text.startswith("Ти автор українського Telegram-каналу.")
    )


def _install_database_hardening() -> None:
    from . import database as database_module
    from .database import Database

    database_module.normalize_url = normalize_url_rc53
    old_init = Database._init
    old_insert = Database.insert_collected
    old_pending = Database.pending_articles
    old_recent_audit = Database.recent_audit

    def init_rc53(self):
        old_init(self)
        with self.connect() as con:
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_channel_published "
                "ON articles(channel_id,status,published_at DESC)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_channel_normalized "
                "ON articles(channel_id,normalized_url,status)"
            )
            rows = con.execute(
                "SELECT id,channel_id,url,normalized_url,status FROM articles WHERE url<>''"
            ).fetchall()
            for row in rows:
                canonical = normalize_url_rc53(str(row["url"] or ""))
                if canonical and canonical != str(row["normalized_url"] or ""):
                    con.execute("UPDATE articles SET normalized_url=? WHERE id=?", (canonical, int(row["id"])))

            pending_missing = con.execute(
                "SELECT id,url FROM articles WHERE status IN ('new','retry','processing') "
                "AND (source_published_at IS NULL OR trim(source_published_at)='')"
            ).fetchall()
            for row in pending_missing:
                inferred = infer_date_from_url(str(row["url"] or ""))
                if inferred:
                    con.execute("UPDATE articles SET source_published_at=? WHERE id=?", (inferred, int(row["id"])))

            groups = con.execute(
                "SELECT channel_id,normalized_url,COUNT(*) AS n FROM articles "
                "WHERE normalized_url<>'' GROUP BY channel_id,normalized_url HAVING COUNT(*)>1"
            ).fetchall()
            for group in groups:
                dupes = con.execute(
                    "SELECT id,status FROM articles WHERE channel_id=? AND normalized_url=? "
                    "ORDER BY CASE WHEN status='published' THEN 0 ELSE 1 END,id DESC",
                    (int(group["channel_id"]), str(group["normalized_url"])),
                ).fetchall()
                if not dupes:
                    continue
                keeper = int(dupes[0]["id"])
                for row in dupes[1:]:
                    if str(row["status"]) in _PENDING_STATUSES:
                        con.execute(
                            "UPDATE articles SET status='duplicate',duplicate_of=?,reject_reason=? WHERE id=?",
                            (keeper, f"RC53 canonical URL duplicate #{keeper}.", int(row["id"])),
                        )
            con.execute("DELETE FROM audit_log WHERE datetime(created_at) < datetime('now','-7 days')")
            con.execute("PRAGMA optimize")

    def insert_collected_rc53(self, source, item, *, baseline: bool):
        canonical = normalize_url_rc53(str(getattr(item, "url", "") or ""))
        if canonical:
            with self.connect() as con:
                existing = con.execute(
                    "SELECT id FROM articles WHERE channel_id=? AND normalized_url=? "
                    "AND status NOT IN ('error') ORDER BY "
                    "CASE WHEN status='published' THEN 0 ELSE 1 END,id DESC LIMIT 1",
                    (int(source.channel_id), canonical),
                ).fetchone()
            if existing:
                return None
        return old_insert(self, source, item, baseline=baseline)

    def pending_rc53(self, channel_id: int, limit: int = 20):
        rows = list(old_pending(self, channel_id, limit=max(int(limit) * 2, int(limit))))
        ready = []
        for row in rows:
            raw_date = _row_value(row, "source_published_at")
            parsed = _parse_source_date(raw_date)
            if parsed is None:
                inferred = infer_date_from_url(_row_value(row, "url"))
                parsed = _parse_source_date(inferred)
                if inferred and parsed is not None:
                    with self.connect() as con:
                        con.execute(
                            "UPDATE articles SET source_published_at=? WHERE id=?",
                            (inferred, int(row["id"])),
                        )
                    refreshed = self.get_article(int(row["id"]))
                    if refreshed is not None:
                        row = refreshed
                else:
                    reason = "RC53 FRESHNESS: дату публікації не підтверджено; fail-closed, матеріал не публікується."
                    self.update_article(int(row["id"]), status="rejected", reject_reason=reason)
                    continue
            ready.append(row)
            if len(ready) >= max(1, int(limit)):
                break
        return ready

    def recent_audit_rc53(self, channel_id: int | None = None, limit: int = 300):
        return old_recent_audit(self, channel_id=channel_id, limit=min(500, max(1, int(limit))))

    Database._init = init_rc53
    Database.insert_collected = insert_collected_rc53
    Database.pending_articles = pending_rc53
    Database.recent_audit = recent_audit_rc53


def _install_collector_hardening() -> None:
    from . import collector as collector_module
    from .article_extractor import extract_article_content

    def enrich_rc53(item):
        if not item.url:
            return item
        try:
            response = collector_module._source_fetch(
                item.url,
                max_bytes=6 * 1024 * 1024,
                allowed_content_types={"text/html", "application/xhtml+xml"},
                timeout=25,
            )
            html = response.body.decode("utf-8", errors="replace")
            extracted = extract_article_content(html, item.url)
            if len(extracted.text) > len(item.raw_text):
                item.raw_text = extracted.text
            if extracted.layout_json:
                item.article_layout_json = extracted.layout_json
            if (not item.title or item.title == "Без заголовка") and extracted.title:
                item.title = extracted.title
            preferred_media = extracted.media_urls if extracted.media_urls else item.media_urls
            item.media_urls = list(dict.fromkeys(preferred_media))[:24]
            if not _parse_source_date(item.published_at):
                item.published_at = extract_page_published_at(html, item.url) or None
        except Exception:
            if not _parse_source_date(item.published_at):
                item.published_at = infer_date_from_url(item.url) or None
        return item

    collector_module._enrich_article = enrich_rc53


def _install_reaction_hardening() -> None:
    from . import rc48_learning as rc48
    from . import rc51_feedback as rc51

    previous_refresh = rc51.refresh_feedback_metrics
    rc51.reaction_breakdown = operator_reaction_breakdown

    def refresh_rc53(db, channel, *, force: bool = False):
        health = reaction_health()
        if not health.ready:
            return {
                "configured": False, "checked": 0, "saved": 0,
                "error": health.message, "policy_warning": "", "state": health.state,
            }
        result = dict(previous_refresh(db, channel, force=force))
        result["state"] = "session_error" if result.get("error") else "ready"
        return result

    rc51.refresh_feedback_metrics = refresh_rc53
    rc48.refresh_channel_metrics = refresh_rc53


def _install_pipeline_hardening() -> None:
    from . import production_pipeline as production
    from . import rewrite_verifier
    from . import service as service_module

    previous_run_ai = production.run_ai
    previous_decide = production.decide
    previous_assess = rewrite_verifier.assess_rewrite
    previous_audit = service_module.AutopilotService._audit
    previous_emit = service_module.AutopilotService._emit

    def run_ai_rc53(prompt, *args, **kwargs):
        text = str(prompt or "")
        original_allowed = set(kwargs.get("allowed_providers") or set())
        if _is_quality_prompt(text):
            if original_allowed and original_allowed <= {"groq", "nvidia", "cloudflare", "local"}:
                raise production.AIRouterError(
                    "RC53: low-yield fallback disabled for final newsroom writing."
                )
            kwargs = dict(kwargs)
            kwargs["allowed_providers"] = {"codex", "gemini"}
            skipped = set(kwargs.get("skip_providers") or set())
            skipped.discard("codex")
            skipped.discard("gemini")
            skipped.update({"local", "groq", "nvidia", "cloudflare"})
            kwargs["skip_providers"] = skipped
            kwargs["suppress_provider_on_quota"] = False
        return previous_run_ai(prompt, *args, **kwargs)

    def assess_rc53(body: str, *, hard_limit: int):
        base = previous_assess(body, hard_limit=hard_limit)
        issues = list(base.issues)
        for pattern, label in _BAD_OUTPUT_PATTERNS:
            if pattern.search(str(body or "")):
                issues.append(label)
        if len(issues) == len(base.issues):
            return base
        return rewrite_verifier.QualityAssessment(min(base.score, 20), tuple(dict.fromkeys(issues)))

    def decide_rc53(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        hard_reason = editorial_hard_reject(channel, article)
        if hard_reason:
            return Decision(
                decision="reject", duplicate_of=None, reason=hard_reason,
                event_key="rc53-hard-veto", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=1.0, provider="local-rule", model="rc53-editorial-veto",
            )
        result = previous_decide(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )
        if result.decision != "publish":
            return result
        source = _row_value(article, "title") + "\n" + _row_value(article, "raw_text")
        blockers = semantic_output_blockers(source, result.telegram_teaser)
        if blockers:
            return Decision(
                decision="reject", duplicate_of=None,
                reason="RC53 FINAL SEMANTIC QA: " + "; ".join(blockers),
                event_key="rc53-semantic-reject",
                event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=1.0, provider="local-rule", model="rc53-semantic-qa",
            )
        return result

    def is_too_old_rc53(self, published: str | None, hours: int) -> bool:
        parsed = _parse_source_date(published)
        if parsed is None:
            return True
        return parsed < datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))

    def audit_rc53(self, stage: str, outcome: str, detail: str = "", **refs):
        if stage == "languagetool" and outcome in {"degraded", "starting"}:
            now = time.monotonic()
            last = float(getattr(self, "_rc53_lt_last_audit", 0.0) or 0.0)
            if now - last < _LT_REPEAT_SECONDS:
                return
            self._rc53_lt_last_audit = now
        return previous_audit(self, stage, outcome, detail, **refs)

    def emit_rc53(self, kind: str, text: str):
        if kind == "languagetool":
            now = time.monotonic()
            last = float(getattr(self, "_rc53_lt_last_emit", 0.0) or 0.0)
            if now - last < _LT_REPEAT_SECONDS:
                return
            self._rc53_lt_last_emit = now
        return previous_emit(self, kind, text)

    production.run_ai = run_ai_rc53
    production.assess_rewrite = assess_rc53
    rewrite_verifier.assess_rewrite = assess_rc53
    production.decide = decide_rc53
    service_module.decide = decide_rc53
    service_module.AutopilotService._is_too_old = is_too_old_rc53
    service_module.AutopilotService._audit = audit_rc53
    service_module.AutopilotService._emit = emit_rc53
    production.POST_FORMAT_PREFIX = "telegram-post-v34:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v34:"


def install_rc53_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_database_hardening()
    _install_collector_hardening()
    _install_reaction_hardening()
    _install_pipeline_hardening()
    _INSTALLED = True
    LOG.info(
        "RC53 installed: operator-only reactions, MTProto health, strict freshness, canonical URL dedupe, "
        "channel hard vetoes, trusted writer routing, semantic QA and LT throttling"
    )
