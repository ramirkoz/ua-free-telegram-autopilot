from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Iterable, Mapping

from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc38")
_INSTALLED = False

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+(?:[’'-][A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+)*")
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+")
_LATIN_ANCHOR_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9._+-]{2,}|[A-Z]{2,}[A-Z0-9._+-]*|[A-Za-z]+\d+[A-Za-z0-9._+-]*)\b")
_NUMBER_RE = re.compile(r"(?<![A-Za-zА-Яа-яІіЇїЄєҐґ])\d+(?:[.,]\d+)?")

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "after", "before", "about", "will", "new",
    "але", "або", "без", "від", "для", "до", "його", "її", "їх", "із", "коли", "на", "не", "після", "про",
    "та", "так", "також", "у", "це", "цей", "ця", "ці", "що", "який", "яка", "як", "ще", "вже", "може",
}

_ANCHOR_STOP = {"AI", "API", "GPU", "CPU", "USA", "US", "EU", "UK", "NASA", "HTTP", "PDF", "RSS"}

_ACTION_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("export", ("export", "smuggl", "customs", "shipment", "sanction", "illegal shipment", "експорт", "вивез", "митниц", "контраб", "санкц", "постач")),
    ("charges", ("indict", "charged", "charges", "prosecut", "обвинувач", "прокурат", "підозр")),
    ("breach", ("breach", "leak", "exposed", "hack", "виток", "злам", "викраден")),
    ("recall", ("recall", "відкликан", "відклика")),
    ("regulation", ("regulator", "antitrust", "ftc", "ban", "banned", "rule", "регулятор", "антимонопол", "заборон")),
    ("launch", ("launch", "released", "release", "unveil", "introduced", "запуск", "випуст", "представ")),
    ("research", ("study", "research", "scientist", "discovered", "found", "дослідж", "вчен", "відкри", "знайш")),
    ("outage", ("outage", "down", "disruption", "збій", "недоступ")),
    ("funding", ("funding", "raised", "raises", "valuation", "інвест", "залуч")),
    ("acquisition", ("acquir", "merger", "bought", "купує", "придба", "злитт")),
)

_GEO_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("china", ("china", "chinese", "кита", "китай")),
    ("taiwan", ("taiwan", "taiwanese", "тайван")),
    ("korea", ("korea", "korean", "коре")),
    ("usa", ("united states", "u.s.", " usa ", "сша", "американ")),
    ("europe", ("europe", "european", "європ")),
    ("russia", ("russia", "russian", "росі")),
    ("uk", ("britain", "british", "united kingdom", "британ")),
    ("japan", ("japan", "japanese", "япон")),
    ("ukraine", ("ukraine", "ukrainian", "україн")),
)

_TOPIC_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cyber", ("cve-", "vulnerability", "zero-day", "zero day", "breach", "ransomware", "malware", "cybersecurity", "security flaw", "виток", "уразлив", "кібер")),
    ("space", ("space", "nasa", "spacex", "falcon", "starlink", "mars", "moon", "galaxy", "astronom", "meteor", "perseid", "iss", "orbit", "rocket", "космос", "марс", "галак", "метеор", "мкс", "орбіт")),
    ("mobility_robotics", ("tesla", "hyundai", "vehicle", "electric car", " ev ", "robot", "humanoid", "autonomous", "автомоб", "електромоб", "робот")),
    ("ai_compute", ("artificial intelligence", " ai ", "openai", "chatgpt", "claude", "gemini", "llm", "agent", "nvidia", "gpu", "cpu", "chip", "semiconductor", "server", "data center", "datacenter", "transformer", "mainframe", "ibm z", " ші ", "чип", "сервер", "дата-центр", "процесор", "мейнфрейм")),
    ("science_energy", ("fusion", "glacier", "climate", "energy", "physics", "biology", "medical", "medicine", "battery", "grid", "термоядер", "льодовик", "клімат", "енерг", "фізик", "біолог", "медиц")),
    ("software", ("windows", "linux", "macos", "microsoft teams", "software", "browser", "application", "open source", "github", "video", "4k", "програм", "браузер", "відео")),
    ("business_regulation", ("startup", "funding", "acquisition", "antitrust", "ftc", "regulator", "lawsuit", "marketplace", "real estate", "стартап", "антимонопол", "регулятор", "ринок")),
)

_TOPIC_LABELS = {
    "cyber": "кібербезпека",
    "space": "космос/астрономія",
    "mobility_robotics": "авто/робототехніка",
    "ai_compute": "ШІ/чипи/дата-центри",
    "science_energy": "наука/енергетика",
    "software": "software/споживчі технології",
    "business_regulation": "бізнес/регулювання",
}

_HIGH_IMPACT = (
    "actively exploited", "zero-day", "zero day", "cve-", "breach", "ransomware", "mass outage",
    "recall", "fatal", "emergency", "court ordered", "antitrust settlement", "phase 3", "critical vulnerability",
    "активно експлуат", "критична уразлив", "витік", "відкликан", "аварі", "антимонопол",
)


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else str(value)


def _row_story(row: Mapping[str, Any] | Any) -> str:
    return "\n".join(
        part for part in (
            _row_value(row, "title"),
            _row_value(row, "teaser_text"),
            _row_value(row, "event_summary"),
            _row_value(row, "full_article_uk"),
            _row_value(row, "raw_text")[:4000],
        ) if part
    )


def _content_tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(str(value or "")) if len(token) >= 3 and token.casefold() not in _STOPWORDS}


def _actions(value: str) -> set[str]:
    low = f" {str(value or '').casefold()} "
    return {name for name, terms in _ACTION_FAMILIES if any(term in low for term in terms)}


def _geos(value: str) -> set[str]:
    low = f" {str(value or '').casefold()} "
    return {name for name, terms in _GEO_GROUPS if any(term in low for term in terms)}


def _anchors(value: str) -> set[str]:
    out = set()
    for item in _LATIN_ANCHOR_RE.findall(str(value or "")):
        if item.upper() in _ANCHOR_STOP:
            continue
        out.add(item.casefold())
    return out


def _numbers(value: str) -> set[str]:
    return {item.replace(",", ".") for item in _NUMBER_RE.findall(str(value or ""))}


def primary_topic(row: Mapping[str, Any] | Any) -> str:
    title = _row_value(row, "title").casefold()
    text = f" {_row_story(row).casefold()} "
    best_name = ""
    best_score = 0
    for name, terms in _TOPIC_GROUPS:
        score = sum(3 if term.strip() in title else 1 for term in terms if term in text)
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def topic_balance_reject_reason(article: Mapping[str, Any] | Any, recent: Iterable[Mapping[str, Any] | Any]) -> str:
    topic = primary_topic(article)
    if not topic:
        return ""
    haystack = _row_story(article).casefold()
    if any(signal in haystack for signal in _HIGH_IMPACT):
        return ""
    categories = [primary_topic(row) for row in list(recent)[:12]]
    categories = [item for item in categories if item]
    if len(categories) < 6:
        return ""
    last10 = categories[:10]
    count10 = Counter(last10)[topic]
    count4 = Counter(categories[:4])[topic]
    hard_cap = 3 if topic == "space" else 4
    if count10 >= hard_cap or (count10 >= 3 and count4 >= 2):
        label = _TOPIC_LABELS.get(topic, topic)
        return f"TOPIC_BALANCE_SKIP: тема «{label}» уже займає {count10} із останніх {len(last10)} публікацій; сильнішу тематичну різноманітність ставимо вище за ще один схожий слот."
    return ""


def compact_readability_issues(text: str) -> tuple[str, ...]:
    value = str(text or "").strip()
    if not value:
        return ("порожній текст",)
    issues: list[str] = []
    words = _WORD_RE.findall(value)
    paragraphs = [p.strip() for p in re.split(r"\n+", value) if p.strip()]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", " ".join(paragraphs)) if s.strip()]
    if len(words) > 90:
        issues.append(f"забагато слів для Telegram-новини ({len(words)} > 90; ціль 55–80)")
    if len(value) > 720:
        issues.append(f"текст надто щільний ({len(value)} символів > 720)")
    if len(paragraphs) > 3:
        issues.append(f"забагато абзаців ({len(paragraphs)} > 3)")
    if len(sentences) > 5:
        issues.append(f"забагато речень ({len(sentences)} > 5)")
    if sentences:
        if len(_WORD_RE.findall(sentences[0])) > 24:
            issues.append("перше речення надто довге для гачка")
        if any(len(_WORD_RE.findall(sentence)) > 27 for sentence in sentences):
            issues.append("є речення довше 27 слів")
    if len(words) >= 75 and len(paragraphs) < 2:
        issues.append("довгий текст злитий в один абзац")
    return tuple(dict.fromkeys(issues))


def _event_duplicate_fallback(current_title: str, current_body: str, recent_published: Iterable[Mapping[str, Any] | Any]):
    from .event_dedupe import DuplicateMatch
    current_story = f"{current_title}\n{current_body}"
    cur_tokens = _content_tokens(current_story)
    cur_actions = _actions(current_story)
    cur_anchors = _anchors(current_story)
    cur_geos = _geos(current_story)
    cur_numbers = _numbers(current_story)
    if not cur_tokens:
        return None
    best = None
    for row in recent_published:
        old_body = _row_value(row, "teaser_text") or _row_value(row, "event_summary") or _row_value(row, "full_article_uk")
        old_title = _row_value(row, "title")
        if not old_body:
            continue
        old_story = f"{old_title}\n{old_body}"
        old_tokens = _content_tokens(old_story)
        shared = cur_tokens & old_tokens
        if len(shared) < 5:
            continue
        containment = len(shared) / max(1, min(len(cur_tokens), len(old_tokens)))
        shared_actions = cur_actions & _actions(old_story)
        shared_anchors = cur_anchors & _anchors(old_story)
        shared_geos = cur_geos & _geos(old_story)
        shared_numbers = cur_numbers & _numbers(old_story)
        strong = False
        if shared_actions and shared_anchors and shared_geos and containment >= 0.18:
            strong = True
        elif shared_actions and len(shared_anchors) >= 2 and containment >= 0.20:
            strong = True
        elif shared_actions and shared_geos and shared_numbers and containment >= 0.16:
            strong = True
        if not strong:
            continue
        try:
            article_id = int(row["id"])
        except Exception:
            continue
        score = min(0.98, 0.64 + 0.10 * min(2, len(shared_actions)) + 0.06 * min(3, len(shared_anchors)) + 0.05 * min(2, len(shared_geos)) + 0.08 * min(1, len(shared_numbers)) + 0.12 * min(1.0, containment))
        reason = f"RC38: та сама подія за дією/сутностями/географією (shared={len(shared)}, actions={len(shared_actions)}, anchors={len(shared_anchors)}, geo={len(shared_geos)})"
        match = DuplicateMatch(article_id=article_id, score=score, reason=reason)
        if best is None or match.score > best.score:
            best = match
    return best


def install_rc38_policy() -> None:
    """RC38: event-level dedupe, lighter copy, and rolling topic balance."""
    global _INSTALLED
    if _INSTALLED:
        return
    from . import event_dedupe as event_dedupe_module
    from . import production_pipeline as production_module
    from . import rc37_policy as rc37_module
    from . import service as service_module

    marker = "telegram-post-v23:"
    production_module.POST_FORMAT_PREFIX = marker
    service_module.POST_FORMAT_PREFIX = marker

    base_interest_style_issues = rc37_module.interest_style_issues
    base_style_examples = rc37_module.style_prompt_examples

    def rc38_interest_style_issues(text: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*base_interest_style_issues(text), *compact_readability_issues(text))))

    compact_contract = (
        "\n\nRC38 COMPACT NEWSROOM CONTRACT:\n"
        "Target 55–80 words; NEVER exceed 90 words. Use 2–3 short paragraphs and 3–5 sentences total. "
        "Tell ONE core fact plus at most three supporting details. If a detail is useful but not necessary to understand the news, cut it. "
        "The first sentence should usually fit within 22 words. No paragraph should become a mini-essay. "
        "Prefer plain verbs and concrete nouns over institutional framing. Do not explain familiar technology unless the explanation is essential to the event. "
        "Do not use 'Йдеться про' as a default bridge. Finish on the last useful fact, not a conclusion."
    )

    def rc38_style_examples(article, *, limit: int = 2) -> str:
        return base_style_examples(article, limit=limit) + compact_contract

    rc37_module.interest_style_issues = rc38_interest_style_issues
    rc37_module.style_prompt_examples = rc38_style_examples

    original_event_dedupe = service_module.find_event_duplicate

    def rc38_event_dedupe(current_title: str, current_body: str, recent):
        match = original_event_dedupe(current_title, current_body, recent)
        if match is not None:
            return match
        return _event_duplicate_fallback(current_title, current_body, recent)

    event_dedupe_module.find_event_duplicate = rc38_event_dedupe
    service_module.find_event_duplicate = rc38_event_dedupe

    original_decide = production_module.decide

    def decide(channel, article, recent, *, hard_limit=production_module.MEDIA_POST_HARD_LIMIT, format_marker=None):
        balance_reason = topic_balance_reject_reason(article, recent)
        if balance_reason:
            return Decision(
                decision="reject", duplicate_of=None, reason=balance_reason,
                event_key="ctrl-ua-topic-balance-v1", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.98, provider="local-rule", model="topic-balance-v1",
            )
        result = original_decide(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)
        if result.decision == "publish":
            issues = compact_readability_issues(str(result.telegram_teaser or ""))
            if issues:
                raise production_module.PostAIQAExhausted("RC38 compact final gate: " + "; ".join(issues), issues, provider_outage=False)
        return result

    production_module.decide = decide
    service_module.decide = decide
    LOG.info("RC38 policy installed: marker=%s", marker)
    _INSTALLED = True
