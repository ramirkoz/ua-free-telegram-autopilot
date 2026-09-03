from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

LOG = logging.getLogger("telegram_autopilot.rc64")
_INSTALLED = False

QUIET_HOURS = (0, 7)
TECHNICAL_GAP_MINUTES = 5
EVENT_TITLE_WINDOW_HOURS = 36
_LOG_EVERY_SECONDS = 300
_LAST_HOLD_LOG: dict[tuple[int, str], float] = {}

_PREV_SELECTOR = None
_PREV_SELECTOR_PROMPT = None
_PREV_WRITER_PROMPT = None
_PREV_DECIDE = None
_PREV_EVENT = None
_PREV_PENDING = None


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _parse_dt(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def publication_hold_reason(service: Any, channel: Any, *, now: datetime | None = None) -> tuple[str, datetime | None]:
    """RC64 keeps only quiet hours plus a tiny anti-double-send delay.

    There are no daily caps, rolling caps, source caps, topic caps or editorial
    60/90-minute pacing gates in training mode. Quality, dedupe and selector
    decisions remain the real publication gates.
    """
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    start, end = QUIET_HOURS
    if start <= current.hour < end:
        wake = current.replace(hour=end, minute=0, second=0, microsecond=0)
        return "quiet_hours", wake

    try:
        raw_last = service.db.last_published_at(int(channel.id))
    except Exception:
        raw_last = ""
    last = _parse_dt(raw_last)
    if last is None:
        return "", None

    last_local = last.astimezone(current.tzinfo)
    next_allowed = last_local + timedelta(minutes=TECHNICAL_GAP_MINUTES)
    if current < next_allowed:
        return "technical_spacing", next_allowed
    return "", None


def training_gap_ok(service: Any, channel: Any) -> bool:
    reason, until = publication_hold_reason(service, channel)
    if not reason:
        return True

    cid = int(getattr(channel, "id", 0) or 0)
    key = (cid, reason)
    stamp = time.monotonic()
    if stamp - _LAST_HOLD_LOG.get(key, 0.0) >= _LOG_EVERY_SECONDS:
        _LAST_HOLD_LOG[key] = stamp
        until_text = until.isoformat(timespec="minutes") if until is not None else "unknown"
        LOG.info(
            "RC64 HOLD channel_id=%s channel=%s reason=%s until=%s; no editorial publication-count/spacing caps",
            cid,
            str(getattr(channel, "name", "") or cid),
            reason,
            until_text,
        )
    return False


def _pending_training(db: Any, cid: int, limit: int = 20):
    """Prefer diversity, but never hard-hide a candidate because of saturation."""
    from . import rc62_editorial_control as rc62

    base = _PREV_PENDING or rc62._PREV.get("pending")
    if base is None:
        return []
    rows = list(base(db, int(cid), max(80, min(320, max(1, int(limit)) * 4))))
    if not rows:
        return rows

    marketing = rc62._is_marketing_channel(db, int(cid))
    kind = "marketing" if marketing else "ctrlua"
    now = datetime.now(timezone.utc)
    source_counts: dict[int, int] = {}
    facet_counts: dict[str, int] = {}
    try:
        with db.connect() as con:
            recent = con.execute(
                """SELECT a.*,s.name AS source_name,s.priority AS source_priority
                   FROM articles a JOIN sources s ON s.id=a.source_id
                   WHERE a.channel_id=? AND a.status='published' AND a.published_at<>''
                     AND datetime(a.published_at)>=datetime('now','-8 hours')
                   ORDER BY a.published_at DESC LIMIT 100""",
                (int(cid),),
            ).fetchall()
    except Exception:
        recent = []

    for old in recent:
        dt = _parse_dt(_v(old, "published_at"))
        if dt is None:
            continue
        age = now - dt.astimezone(timezone.utc)
        sid = int(_v(old, "source_id", 0) or 0)
        facet = rc62._facet(old, kind)
        if age <= timedelta(hours=8 if marketing else 6):
            source_counts[sid] = source_counts.get(sid, 0) + 1
        if facet and age <= timedelta(hours=5 if marketing else 4):
            facet_counts[facet] = facet_counts.get(facet, 0) + 1

    ranked: list[tuple[int, int, Any]] = []
    for index, row in enumerate(rows):
        sid = int(_v(row, "source_id", 0) or 0)
        facet = rc62._facet(row, kind)
        # Soft preference only. Repeated sources/topics remain eligible once the
        # fresher/diverse candidates ahead of them are exhausted.
        penalty = 3 * source_counts.get(sid, 0) + 2 * facet_counts.get(facet, 0)
        ranked.append((penalty, index, row))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [row for _penalty, _index, row in ranked[: max(1, int(limit))]]


def _selector_prompt_rc64(policy: Any, article: Any, *, channel_id: int = 0) -> str:
    from . import rc62_editorial_control as rc62

    base = _PREV_SELECTOR_PROMPT(policy, article, channel_id=channel_id)
    if not rc62._marketing(policy):
        return base
    return base + """

RC64 ПРОДАНО! — ШИРШИЙ СВІТ, НЕ ЛИШЕ РЕКЛАМНІ КЕЙСИ.
Канал цікавиться будь-яким реальним механізмом, який змушує людей дивитися, хотіти, купувати, платити, повертатися, підписуватися або поширювати.
Сильними можуть бути НЕ тільки кампанії, а й: consumer behavior, pricing і знижки, retail/e-commerce, dark patterns та інтерфейси, loyalty, packaging, platform monetization, creator economy, influencer mechanics, viral products, PR-фейли, експерименти з поведінкою покупців і дивні комерційні механіки.
marketing_mechanic_score означає силу МЕХАНІЗМУ ВПЛИВУ НА ПОВЕДІНКУ, а не наявність рекламної кампанії чи агентства.
Не знижуй оцінку лише тому, що матеріал не є campaign case study. Якщо механіка зрозуміла широкому читачеві і її хочеться переказати — це повноцінний кандидат ПРОДАНО!.
""".strip()


def _run_selector_rc64(policy: Any, article: Any, *, channel_id: int = 0):
    from . import rc62_editorial_control as rc62

    result, parsed = _PREV_SELECTOR(policy, article, channel_id=channel_id)
    data = dict(parsed)
    marketing = rc62._marketing(policy)

    if marketing and data.get("decision") == "reject" and str(data.get("reason") or "").startswith("RC62 HUMAN_INTEREST_REJECT"):
        try:
            raw = rc62._parse_marketing(result.text)
        except Exception:
            raw = {}
        if raw.get("decision") == "publish":
            h = int(raw.get("human_interest_score", 0) or 0)
            f = int(raw.get("friend_share_score", 0) or 0)
            m = int(raw.get("marketing_mechanic_score", 0) or 0)
            c = int(raw.get("creative_surprise_score", 0) or 0)
            hook = " ".join(str(raw.get("non_marketer_hook") or "").split())
            behavioral = h >= 75 and f >= 66 and m >= 58 and bool(hook)
            high_human = h >= 82 and f >= 68 and m >= 48 and bool(hook)
            if behavioral or high_human:
                data = dict(raw)
                data["decision"] = "publish"
                data["reason"] = (
                    f"RC64 BROAD_HUMAN_INTEREST_PASS: сильна поведінкова/комерційна механіка "
                    f"(human={h}, share={f}, creative={c}, mechanic={m})."
                )

    decision = str(data.get("decision") or "reject")
    article_id = _v(article, "id", "?")
    LOG.info(
        "RC64 SELECTOR_%s channel_id=%s article_id=%s fit=%s human=%s share=%s creative=%s mechanic=%s reason=%s",
        "PASS" if decision == "publish" else "REJECT",
        int(channel_id or 0), article_id, int(data.get("fit_score", 0) or 0),
        int(data.get("human_interest_score", 0) or 0), int(data.get("friend_share_score", 0) or 0),
        int(data.get("creative_surprise_score", 0) or 0), int(data.get("marketing_mechanic_score", 0) or 0),
        " ".join(str(data.get("reason") or "").split())[:500],
    )
    return result, data


def _writer_prompt_rc64(policy: Any, channel: Any, article: Any, selector: dict[str, Any], *, hard_limit: int) -> str:
    base = _PREV_WRITER_PROMPT(policy, channel, article, selector, hard_limit=hard_limit)
    return base + """

RC64 НОРМА УКРАЇНСЬКИХ ВЛАСНИХ НАЗВ:
- імена й прізвища людей у звичайному українському тексті передавай українською за усталеним написанням/транслітерацією: Michael J. Fox → Майкл Джей Фокс, Harrison Ford → Гаррісон Форд;
- загальновідомі назви наукових об'єктів/інституцій/хвороб подавай природною українською формою, якщо вона усталена: Hubble → «Габбл», Parkinson's disease → хвороба Паркінсона;
- НЕ перекладай і не транслітеруй бренди, компанії, продукти, сервіси, моделі, абревіатури, формули й технічні позначення без усталеної української форми: Smalls, Deep Fission, Midjourney, PlayStation, NbSe2, TaS2, sFlt-1 залишаються як у SOURCE;
- не вигадуй українське написання, якщо не впевнений. У такому разі лиши оригінал.
""".strip()


_LATIN_NAME_SEQUENCE = re.compile(
    r"\b(?:[A-Z][A-Za-z'’.-]{1,}|[A-Z])(?:\s+(?:[A-Z][A-Za-z'’.-]{1,}|[A-Z])){1,3}\b"
)
_LOCALIZE_SINGLE = re.compile(r"\b(?:Hubble|Parkinson(?:'s|’s)?)\b", re.I)


def _needs_name_localization(text: str) -> bool:
    value = str(text or "")
    return bool(_LATIN_NAME_SEQUENCE.search(value) or _LOCALIZE_SINGLE.search(value))


def _localize_remaining_names(article: Any, body: str, *, hard_limit: int) -> str:
    """Targeted fallback only when the writer left clearly localizable Latin names."""
    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from .evidence_pack import build_evidence_pack

    source = build_evidence_pack(article, char_budget=5000).text
    prompt = f"""Ти фінальний український редактор власних назв. Виправ ТІЛЬКИ спосіб написання власних назв у POST.

ПРАВИЛА:
1. Імена/прізвища людей передавай українською за усталеним написанням або коректною транслітерацією.
2. Усталені загальновідомі українські назви наукових об'єктів/інституцій/хвороб подавай українською.
3. Бренди, компанії, продукти, сервіси, моделі, абревіатури, хімічні формули та технічні позначення НЕ перекладай без усталеної української форми.
4. Не змінюй жодного факту, числа, дати, причинного зв'язку, структури чи змісту. Не додавай пояснень.
5. Якщо латинська назва має лишитися латиницею — лиши її.

SOURCE:
{source}

POST:
{body}

Поверни ТІЛЬКИ готовий пост."""
    years = rc40._rc40_allowed_years(article)
    nums = rc40._rc40_allowed_numbers(article)

    def validator(raw: str) -> None:
        rc40._validated_ua_body(
            raw, article=article, allowed_years=years, allowed_numbers=nums, hard_limit=hard_limit
        )

    result = production.run_ai(
        prompt, validator=validator, max_output_tokens=680,
        local_prompt=prompt, local_max_output_tokens=680,
        cloud_timeout_seconds=26, local_timeout_seconds=18, task_timeout_seconds=60,
        local_repair=False, suppress_provider_on_quota=False,
        allowed_providers={"codex", "gemini", "groq"},
    )
    return rc40._validated_ua_body(
        result.text, article=article, allowed_years=years, allowed_numbers=nums, hard_limit=hard_limit
    )


def _decide_rc64(channel: Any, article: Any, recent: list[Any], *, hard_limit: int, format_marker: str | None = None):
    decision = _PREV_DECIDE(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)
    if decision.decision != "publish" or not _needs_name_localization(decision.telegram_teaser):
        return decision
    try:
        fixed = _localize_remaining_names(article, decision.telegram_teaser, hard_limit=hard_limit)
    except Exception as exc:
        # Localization must improve copy, never become another throughput kill switch.
        LOG.warning("RC64 name localization degraded article_id=%s keep_original=1 error=%s", _v(article, "id", "?"), exc)
        return replace(decision, reason=decision.reason + " RC64 name localization degraded; safe original kept.")
    changed = fixed != decision.telegram_teaser
    LOG.info("RC64 name localization article_id=%s changed=%s", _v(article, "id", "?"), int(changed))
    if not changed:
        return decision
    return replace(
        decision,
        telegram_teaser=fixed,
        full_article_uk=fixed,
        event_summary=fixed[:1000],
        reason=decision.reason + " RC64 Ukrainian named-entity localization PASS.",
    )


def _within_event_window(row: Any, hours: int = EVENT_TITLE_WINDOW_HOURS) -> bool:
    dt = _parse_dt(_v(row, "published_at"))
    if dt is None:
        return False
    return datetime.now(timezone.utc) - dt.astimezone(timezone.utc) <= timedelta(hours=hours)


def _strong_title_event(current_title: str, row: Any):
    from . import event_dedupe as ev

    old_title = str(_v(row, "title", "") or "")
    cur_tokens = ev._tokens(current_title)
    old_tokens = ev._tokens(old_title)
    if not cur_tokens or not old_tokens:
        return None
    shared = cur_tokens & old_tokens
    containment = len(shared) / max(1, min(len(cur_tokens), len(old_tokens)))
    cur_anchors = ev._latin_anchors(current_title)
    old_anchors = ev._latin_anchors(old_title)
    anchor_shared = cur_anchors & old_anchors
    if _within_event_window(row) and len(shared) >= 4 and containment >= 0.55 and (anchor_shared or len(shared) >= 5):
        score = min(0.98, 0.72 + 0.04 * len(shared) + 0.08 * min(1, len(anchor_shared)))
        return score, f"та сама подія за сильним збігом заголовків у {EVENT_TITLE_WINDOW_HOURS}h (shared={len(shared)}, containment={containment:.2f})"
    return None


def _find_duplicate_rc64(title: str, body: str, recent: Any):
    from . import event_dedupe as ev

    rows = list(recent)
    hit = _PREV_EVENT(title, body, rows)
    if hit is not None:
        return hit
    best = None
    for row in rows:
        pair = _strong_title_event(title, row)
        if pair is None:
            continue
        try:
            article_id = int(_v(row, "id", 0) or 0)
        except Exception:
            article_id = 0
        if not article_id:
            continue
        candidate = ev.DuplicateMatch(article_id=article_id, score=pair[0], reason=pair[1])
        if best is None or candidate.score > best.score:
            best = candidate
    if best is not None:
        LOG.info("RC64 EVENT_DUPLICATE duplicate_of=%s score=%.2f reason=%s", best.article_id, best.score, best.reason)
    return best


def install_rc64_live_tuning() -> None:
    global _INSTALLED, _PREV_SELECTOR, _PREV_SELECTOR_PROMPT, _PREV_WRITER_PROMPT, _PREV_DECIDE, _PREV_EVENT, _PREV_PENDING
    if _INSTALLED:
        return

    from . import event_dedupe as ev
    from . import production_pipeline as prod
    from . import rc59_universal_policy as rc59
    from . import rc62_editorial_control as rc62
    from . import service as svc
    from .database import Database

    _PREV_SELECTOR = rc59._run_selector
    _PREV_SELECTOR_PROMPT = rc62.selector_prompt
    _PREV_WRITER_PROMPT = rc59._writer_prompt
    _PREV_DECIDE = prod.decide
    _PREV_EVENT = ev.find_event_duplicate
    _PREV_PENDING = rc62._PREV.get("pending")

    svc.AutopilotService._gap_ok = training_gap_ok
    Database.pending_articles = _pending_training

    rc62.selector_prompt = _selector_prompt_rc64
    rc59._run_selector = _run_selector_rc64
    rc59._writer_prompt = _writer_prompt_rc64

    ev.find_event_duplicate = _find_duplicate_rc64
    svc.find_event_duplicate = _find_duplicate_rc64

    def wrapped(channel, article, recent, *, hard_limit=prod.MEDIA_POST_HARD_LIMIT, format_marker=None):
        return _decide_rc64(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)

    prod.decide = wrapped
    svc.decide = wrapped
    prod.POST_FORMAT_PREFIX = "telegram-post-v39:"
    svc.POST_FORMAT_PREFIX = "telegram-post-v39:"

    LOG.info(
        "RC64 installed: 5m technical-only spacing, no hard source/topic saturation, broader ПРОДАНО! behavioral scope, "
        "selector diagnostics, Ukrainian named-entity localization and 36h cross-source title-event dedupe"
    )
    _INSTALLED = True
