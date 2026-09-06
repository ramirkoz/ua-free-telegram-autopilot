from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any

LOG = logging.getLogger("telegram_autopilot.rc74")
_INSTALLED = False
_PREV: dict[str, Any] = {}

# Only technical/non-editorial media noise is hard-rejected globally. Editorial
# concepts such as "advertisement", "promotion" or "commercial" are NOT hidden
# channel rules and must be decided by the channel policy, not by the engine.
_MEDIA_NOISE = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "amazon-adsystem.com",
    "outbrain.com", "taboola.com", "adservice.google", "adserver", "ad-server", "ad-unit", "ad_slot",
    "tracking", "pixel.gif", "1x1.gif", "favicon", "sprite", "avatar", "headshot", "profile-photo",
    "social-share", "share-icon", "analytics", "newsletter-widget", "subscribe-widget",
)
_LOGO_WORDS = ("logo", "wordmark", "brandmark", "app-icon", "site-icon", "badge")


def _v(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


@contextmanager
def channel_context(channel: Any):
    """Install ONLY the explicit per-channel language direction in this thread."""
    from . import rc45_policy as rc45

    direction = rc45.content_direction(channel)
    token = rc45._CURRENT_DIRECTION.set(direction)
    try:
        yield direction
    finally:
        rc45._CURRENT_DIRECTION.reset(token)


def _english_output() -> bool:
    from . import rc45_policy as rc45

    return rc45._CURRENT_DIRECTION.get() == rc45.DIRECTION_UKRU_TO_EN


def source_labels() -> tuple[str, str]:
    return ("Source", "Sources") if _english_output() else ("Джерело", "Джерела")


def universal_media_hard_reject(item: Any, *, marketing_context: bool = False) -> bool:
    """Channel-neutral media safety gate.

    ``marketing_context`` remains only for ABI compatibility and is deliberately
    ignored. The same media rules apply to every channel.
    """
    url = str(getattr(item, "url", "") or "")
    context = str(getattr(item, "context", "") or "")
    low = (url + " " + context).casefold().replace("_", "-")
    if any(term in low for term in _MEDIA_NOISE):
        return True
    if any(term in low for term in _LOGO_WORDS):
        return True
    return False


def _build_post_text_rc74(
    text_or_internal_headline: str,
    body: str | None = None,
    *,
    source_url: str = "",
    include_source_link: bool = False,
    hard_limit: int = 900,
) -> str:
    from .telegram import TelegramError, _clean_paragraphs

    clean = _clean_paragraphs(body if body is not None else text_or_internal_headline)
    if not clean:
        raise TelegramError("Порожній текст Telegram-поста.", retryable=False)
    if include_source_link and source_url.strip():
        clean += "\n\n" + source_labels()[0]
    if len(clean) > hard_limit:
        raise TelegramError(f"Telegram-пост перевищує ліміт {hard_limit} символів.", retryable=False)
    return clean


def _source_link_entities_rc74(text: str, source_url: str) -> str:
    from .telegram import _utf16_units

    url = str(source_url or "").strip()
    value = str(text or "")
    if not url:
        return ""
    label = next((x for x in ("Джерело", "Source") if value.rstrip().endswith(x)), "")
    if not label:
        return ""
    start = value.rfind(label)
    return json.dumps([{
        "type": "text_link",
        "offset": _utf16_units(value[:start]),
        "length": _utf16_units(label),
        "url": url,
    }], ensure_ascii=False, separators=(",", ":"))


def _caption_rc74(body: str, urls: list[str], *, video_link: str = "", hard_limit: int = 900) -> tuple[str, str]:
    from .telegram import build_post_text

    body = str(body or "").strip() + (f"\n\n🎬 {'Video' if _english_output() else 'Відео'}: {video_link}" if video_link else "")
    if len(urls) <= 1:
        url = urls[0] if urls else ""
        return build_post_text(body, source_url=url, include_source_link=bool(url), hard_limit=hard_limit), url
    footer = f"\n\n{source_labels()[1]}:\n" + "\n".join(f"{i}. {url}" for i, url in enumerate(urls, 1))
    if len(body) + len(footer) > hard_limit:
        allowance = max(260, hard_limit - len(footer))
        trimmed = body[:allowance].rstrip()
        cut = max(trimmed.rfind(". "), trimmed.rfind("! "), trimmed.rfind("? "), trimmed.rfind("… "))
        body = trimmed[:cut + 1] if cut >= max(120, allowance // 2) else trimmed
    result = body.rstrip() + footer
    if len(result) > hard_limit:
        raise RuntimeError(f"RC74 multisource caption exceeds {hard_limit} chars")
    return result, ""


def _fast_cluster_one_rc74(service: Any, channel: Any, row: Any) -> str:
    """Non-blocking deterministic pre-cluster. No network/AI is allowed here."""
    from . import rc66_clusters as clusters
    from . import rc67_nonblocking_runtime as rc67
    from .rc66_tags import row_tags, strong_overlap

    db = service.db
    article_id = int(_v(row, "id", 0) or 0)
    if not article_id:
        return "skip"
    tags = row_tags(db, row, channel)
    ranked: list[tuple[int, int, Any, Any, set[str]]] = []
    for candidate in clusters._candidates(db, int(channel.id), article_id, int(getattr(channel, "dedupe_window_hours", 72) or 72)):
        ctags = row_tags(db, candidate, channel)
        overlap = strong_overlap(tags, ctags)
        if not rc67._worth_ai(overlap):
            continue
        status = str(_v(candidate, "status", "") or "")
        ranked.append((clusters._weight(overlap) + (8 if status == "published" else 0), int(_v(candidate, "id", 0) or 0), candidate, ctags, overlap))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    for _score, candidate_id, candidate, ctags, overlap in ranked[:4]:
        cached = clusters._cached(db, int(channel.id), article_id, candidate_id)
        if cached:
            relation, reason = cached
            via = "cache"
        else:
            relation, reason = clusters._fallback_relation(row, candidate, tags, ctags)
            via = "local"
            clusters._store(db, int(channel.id), article_id, candidate_id, relation, reason)
        service._audit("rc74_dedupe", relation.lower(), f"candidate={candidate_id}; via={via}; {reason}", channel_id=int(channel.id), article_id=article_id)
        fresh = db.get_article(candidate_id) or candidate
        status = str(_v(fresh, "status", "") or "")
        if status == "published" and relation == "DUPLICATE":
            db.update_article(article_id, status="duplicate", duplicate_of=candidate_id, reject_reason=f"RC74: дубль уже опублікованої події #{candidate_id}: {reason}", ai_provider="local-dedupe", ai_model="rc74-fast")
            return "duplicate"
        if status != "published" and relation in {"DUPLICATE", "UPDATE"}:
            cluster_id = int(_v(fresh, "event_cluster_id", 0) or 0) or clusters._ensure_cluster(db, int(channel.id), candidate_id, ctags)
            canonical_id, canonical_status = rc67._safe_attach(db, article_id, fresh, cluster_id)
            if canonical_status == "published":
                if relation == "DUPLICATE":
                    db.update_article(article_id, status="duplicate", duplicate_of=canonical_id, reject_reason=f"RC74: дубль опублікованої події #{canonical_id}: {reason}", ai_provider="local-dedupe", ai_model="rc74-fast")
                    return "duplicate"
                break
            return "clustered"
    clusters._ensure_cluster(db, int(channel.id), article_id, tags)
    return "single"


def _decide_rc74(channel: Any, article: Any, recent: list[Any], *, hard_limit: int, format_marker: str | None = None):
    """Honor explicit output language without bypassing the channel policy gate."""
    from . import production_pipeline as prod
    from . import rc45_policy as rc45
    from . import rc51_feedback as rc51
    from . import rc59_universal_policy as rc59

    if rc45.content_direction(channel) != rc45.DIRECTION_UKRU_TO_EN:
        return _PREV["decide"](channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)

    db = rc51._ACTIVE_DB
    policy = db.rc59_get_channel_policy(int(channel.id)) if db is not None else rc59.default_policy(channel)
    if not policy.enabled:
        return rc59._reject(article, "CHANNEL_POLICY_DISABLED: channel policy is disabled.", event_key="rc74-policy-disabled", model="rc74-policy")
    if not str(policy.purpose or "").strip() or not str(policy.selection_rules or "").strip():
        return rc59._reject(article, "CHANNEL_POLICY_INCOMPLETE: configure channel purpose and selection rules.", event_key="rc74-policy-incomplete", model="rc74-policy")

    duplicate_id = prod._title_duplicate(article, recent)
    if duplicate_id is not None:
        from .models import Decision
        return Decision(
            decision="duplicate", duplicate_of=duplicate_id, reason=f"Title duplicate of published material #{duplicate_id}.",
            event_key="title-duplicate", event_summary=str(_v(article, "title", ""))[:1000],
            headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
            confidence=0.99, provider="local-rule", model="title-dedupe",
        )

    verdict = rc59.score_against_feedback_rc59(article, rc59._feedback_rows(int(channel.id)))
    if verdict.hard_suppress:
        return rc59._reject(
            article,
            f"REACTION_FEEDBACK_SKIP: closely related topic suppressed after editor feedback; similarity={verdict.matched_similarity:.3f}.",
            event_key="rc74-reaction-suppress", model="rc74-reaction-feedback", confidence=0.98,
        )

    try:
        selector_result, selector = rc59._run_selector(policy, article, channel_id=int(channel.id))
    except Exception as exc:
        return rc59._reject(
            article, "SELECTOR_UNAVAILABLE: " + str(exc)[:350],
            event_key="rc74-selector-unavailable", model="rc74-selector-safe-fail", confidence=1.0,
        )
    if str(selector.get("decision") or "") != "publish":
        return rc59._reject(
            article, f"CHANNEL_POLICY_REJECT fit={int(selector.get('fit_score', 0) or 0)}%: {selector.get('reason', '')}",
            event_key="rc74-channel-policy-reject", model=f"rc74-selector/{selector_result.provider}", confidence=0.96,
        )

    # RC45 already contains the fact-safe English writer/QA route. It is called
    # only after the same channel-policy selector used by every editorial channel.
    return rc45._decide_english(channel, article, hard_limit=hard_limit, format_marker=format_marker)


def _invalidate_channel_drafts(db: Any, channel_id: int, reason: str) -> None:
    """Make saved per-channel settings effective immediately for queued work."""
    try:
        with db.connect() as con:
            con.execute(
                """UPDATE articles SET status=CASE WHEN status='ready' THEN 'new' ELSE status END,
                          ready_at=NULL,rewrite_text='',headline_uk='',teaser_text='',full_article_uk='',
                          event_key='',event_summary='',ai_provider='',ai_model='',last_error=NULL,
                          retry_count=0,next_retry_at=NULL,editorial_value_score=NULL,
                          editorial_value_json='',editorial_value_reason='',editorial_value_checked_at=NULL
                   WHERE channel_id=? AND status IN ('new','retry','ready')""",
                (int(channel_id),),
            )
        LOG.info("RC74 invalidated queued drafts channel_id=%s reason=%s", channel_id, reason)
    except Exception as exc:
        LOG.warning("RC74 draft invalidation skipped channel_id=%s: %s", channel_id, exc)


def _audit_config(service: Any, channel: Any) -> None:
    signatures = getattr(service, "_rc74_config_signatures", None)
    if signatures is None:
        signatures = {}
        setattr(service, "_rc74_config_signatures", signatures)
    try:
        policy = service.db.rc59_get_channel_policy(int(channel.id))
        policy_stamp = str(getattr(policy, "updated_at", "") or "")
        media_policy = str(getattr(policy, "media_policy", "") or "")
    except Exception:
        policy_stamp = media_policy = ""
    sig = (
        str(getattr(channel, "content_direction", "") or ""), str(getattr(channel, "channel_mode", "") or ""),
        int(getattr(channel, "poll_interval_minutes", 0) or 0), int(getattr(channel, "min_publish_interval_minutes", 0) or 0),
        bool(getattr(channel, "publish_24h", False)), str(getattr(channel, "publish_start", "") or ""), str(getattr(channel, "publish_end", "") or ""),
        bool(getattr(channel, "publish_immediately", False)), bool(getattr(channel, "topic_balance_enabled", False)),
        str(getattr(channel, "editorial_weights_json", "") or ""), policy_stamp, media_policy,
    )
    if signatures.get(int(channel.id)) == sig:
        return
    signatures[int(channel.id)] = sig
    service._audit(
        "rc74_channel_config", "active",
        f"direction={sig[0]}; mode={sig[1]}; poll={sig[2]}m; gap={sig[3]}m; window={'24h' if sig[4] else sig[5]+'-'+sig[6]}; immediate={int(sig[7])}; topic_balance={int(sig[8])}; media_policy={media_policy}; policy_updated={policy_stamp}",
        channel_id=int(channel.id),
    )


def install_rc74_universal_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import media_pipeline
    from . import production_pipeline as prod
    from . import rc66_editorial_queue as rc66
    from . import rc67_nonblocking_runtime as rc67
    from . import service as svc
    from . import telegram as tg
    from .database import Database

    _PREV.update(
        run_channel=svc.AutopilotService._run_channel,
        prepare_one=rc67._prepare_one,
        publish_one=rc66._publish_one,
        decide=prod.decide,
        set_direction=getattr(Database, "set_channel_content_direction", None),
        save_policy=getattr(Database, "rc59_save_channel_policy", None),
    )

    # Retire all name/profile-derived media behavior. Relevance belongs to the
    # channel policy. The engine keeps only universal technical media safety.
    svc._marketing_media_context = lambda _channel: False
    media_pipeline._hard_reject = universal_media_hard_reject

    # Source labels follow the explicit output-language direction.
    tg.build_post_text = _build_post_text_rc74
    tg._source_link_entities = _source_link_entities_rc74
    rc66._caption = _caption_rc74

    # The pre-queue dedupe may never block a channel on an AI provider.
    rc67._fast_cluster_one = _fast_cluster_one_rc74

    def run_channel(self, channel, *, force: bool):
        with channel_context(channel):
            _audit_config(self, channel)
            return _PREV["run_channel"](self, channel, force=force)

    def prepare_one(service, channel):
        with channel_context(channel):
            return _PREV["prepare_one"](service, channel)

    def publish_one(service, channel, row):
        with channel_context(channel):
            return bool(_PREV["publish_one"](service, channel, row))

    def decide(channel, article, recent, *, hard_limit=prod.MEDIA_POST_HARD_LIMIT, format_marker=None):
        return _decide_rc74(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)

    svc.AutopilotService._run_channel = run_channel
    rc67._prepare_one = prepare_one
    rc66._publish_one = publish_one
    prod.decide = decide
    svc.decide = decide

    # One static cache-format generation avoids cross-channel global races.
    svc.POST_FORMAT_PREFIX = "telegram-post-v74:"
    prod.POST_FORMAT_PREFIX = "telegram-post-v74:"

    if _PREV["set_direction"] is not None:
        def set_direction(db, channel_id: int, direction: str) -> None:
            _PREV["set_direction"](db, int(channel_id), direction)
            _invalidate_channel_drafts(db, int(channel_id), "content_direction")
        Database.set_channel_content_direction = set_direction

    if _PREV["save_policy"] is not None:
        def save_policy(db, policy) -> None:
            _PREV["save_policy"](db, policy)
            _invalidate_channel_drafts(db, int(policy.channel_id), "channel_policy")
        Database.rc59_save_channel_policy = save_policy

    LOG.info(
        "RC74 installed: universal-only runtime, per-channel language context in worker threads, "
        "channel-neutral media gate, deterministic nonblocking pre-dedupe and config-driven publication"
    )
    _INSTALLED = True
