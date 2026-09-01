from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Iterable, Mapping

from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc60")
_INSTALLED = False

# RC60 is deliberately channel-agnostic. These are language-quality rules, not
# editorial-topic rules. Channel taste remains entirely in ChannelPolicy.
_JARGON_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsocial[- ]first\b", re.I), "social-first"),
    (re.compile(r"\bhot takes?\b", re.I), "hot takes"),
    (re.compile(r"\bqualified views?\b", re.I), "qualified views"),
    (re.compile(r"\brun rate\b", re.I), "run rate"),
    (re.compile(r"\bshot list\b", re.I), "shot list"),
    (re.compile(r"\bcreator payouts?\b", re.I), "creator payouts"),
    (re.compile(r"\bfan funding\b", re.I), "fan funding"),
    (re.compile(r"\bad revenue\b", re.I), "ad revenue"),
    (re.compile(r"\bself[- ]serve\b", re.I), "self-serve"),
    (re.compile(r"\bcreator economy\b", re.I), "creator economy"),
    (re.compile(r"\bbrand activation\b", re.I), "brand activation"),
    (re.compile(r"\bperformance marketing\b", re.I), "performance marketing"),
    (re.compile(r"\bopen source\b", re.I), "open source"),
    (re.compile(r"\bfair use\b", re.I), "fair use"),
    (re.compile(r"\bengagement rate\b", re.I), "engagement rate"),
)

_GENERIC_JARGON = {
    "creator", "creators", "campaign", "campaigns", "engagement", "insights", "performance",
    "payout", "payouts", "revenue", "reach", "workflow", "workflows", "launch", "launches",
    "branding", "marketing", "community", "challenge", "reward", "rewards", "behavior", "behaviour",
}

# Ordinary product/company/standard names are not language mixing. This list is
# intentionally small because uppercase acronyms, CamelCase and tokens with digits
# are already allowed by shape.
_ALLOWED_LOWER_LATIN = {
    "ios", "macos", "android", "linux", "python", "javascript", "typescript", "github", "reddit",
    "youtube", "instagram", "facebook", "tiktok", "threads", "snapchat", "whatsapp", "telegram",
}

_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9.+_-]{2,})(?![A-Za-z0-9])")
_URL_RE = re.compile(r"https?://\S+", re.I)


def latin_jargon_issues(text: str) -> tuple[str, ...]:
    """Return translatable English jargon that escaped into Ukrainian prose.

    Proper names, acronyms and model names remain allowed. The purpose is not to
    purge Latin characters; it is to stop sentences that alternate between
    Ukrainian grammar and untranslated professional English vocabulary.
    """
    value = _URL_RE.sub(" ", str(text or ""))
    issues: list[str] = []
    for pattern, label in _JARGON_PHRASES:
        if pattern.search(value) and label not in issues:
            issues.append(label)

    for match in _TOKEN_RE.finditer(value):
        token = match.group(1)
        low = token.casefold()
        if low in _ALLOWED_LOWER_LATIN:
            continue
        if token.isupper() or any(ch.isdigit() for ch in token) or "." in token:
            continue
        # CamelCase / brand-shaped tokens are names, not untranslated prose.
        if any(ch.isupper() for ch in token[1:]):
            continue
        if low in _GENERIC_JARGON and low not in issues:
            issues.append(low)
    return tuple(issues[:8])


def _ua_language_appendix() -> str:
    return """

ГЛОБАЛЬНА МОВНА НОРМА RC60:
- готовий пост має читатися як природний український текст, а не суміш української граматики з англійським професійним жаргоном;
- перекладай загальні англійські терміни, якщо український відповідник передає зміст без втрати факту;
- англійською залишай власні назви брендів, компаній, продуктів, кампаній, моделей, стандартів, абревіатури та терміни без усталеного українського відповідника;
- якщо спеціальний англійський термін справді треба залишити, при першій згадці коротко поясни його українською;
- не залишай без пояснення такі конструкції, як social-first, hot takes, qualified views, run rate, shot list, creator payouts, fan funding, ad revenue, self-serve, open source або fair use;
- не підмінюй переклад транслітерацією на кшталт «перформанс», «інсайти», «кріейтори», якщо можна сказати природно: результативність, висновки, автори/творці контенту.
""".strip()


_STOP = {
    "the", "and", "for", "with", "from", "into", "about", "that", "this", "your", "new", "more", "now",
    "after", "before", "over", "under", "latest", "says", "say", "how", "why", "what", "when", "where",
    "a", "an", "to", "of", "in", "on", "at", "by", "as", "is", "are", "was", "were", "be", "been",
}
_TITLE_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{1,}")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9.+_-]{2,}|[A-Z]{2,}[A-Z0-9.+_-]*)\b")

_EVENT_FAMILIES: dict[str, tuple[str, ...]] = {
    "regulation": ("designat", "classif", "oversight", "regulat", "rule", "law", "ban", "probe", "dsa", "antitrust"),
    "campaign": ("campaign", "advert", "creator", "commercial", "activation", "stunt", "spot", "promo", "collab"),
    "lawsuit": ("lawsuit", "sues", "sued", "court", "complaint", "alleges", "settlement"),
    "security": ("hack", "breach", "cyberattack", "ransomware", "malware", "vulnerability", "exploit"),
    "research": ("study", "research", "scientist", "researcher", "discover", "finds", "found", "trial"),
    "business": ("acquir", "merger", "funding", "valuation", "layoff", "appoint", "hires", "revenue"),
    "product": ("launch", "unveil", "release", "introduc", "announce", "rollout", "update"),
}


def _title_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _TITLE_WORD_RE.findall(str(value or ""))
        if len(token) >= 3 and token.casefold() not in _STOP
    }


def _numbers(value: str) -> set[str]:
    return {item.replace(",", ".") for item in _NUMBER_RE.findall(str(value or ""))}


def _entities(value: str) -> set[str]:
    return {item.casefold() for item in _ENTITY_RE.findall(str(value or "")) if item.casefold() not in _STOP}


def _families(value: str) -> set[str]:
    low = str(value or "").casefold()
    return {name for name, stems in _EVENT_FAMILIES.items() if any(stem in low for stem in stems)}


def _row_value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _cross_source_title_match(current_title: str, row: Mapping[str, Any] | Any) -> tuple[float, str] | None:
    old_title = str(_row_value(row, "title", "") or "")
    cur_tokens = _title_tokens(current_title)
    old_tokens = _title_tokens(old_title)
    if not cur_tokens or not old_tokens:
        return None
    shared_tokens = cur_tokens & old_tokens
    entities = _entities(current_title) & _entities(old_title)
    families = _families(current_title) & _families(old_title)
    shared_numbers = _numbers(current_title) & _numbers(old_title)
    union = cur_tokens | old_tokens
    jaccard = len(shared_tokens) / max(1, len(union))

    # Two named anchors + same event family is a strong cross-source event key.
    if len(entities) >= 2 and families and (len(shared_tokens) >= 3 or shared_numbers):
        return 0.91 + min(0.07, 0.02 * len(entities)), "та сама подія в іншому джерелі: збігаються сутності та тип події"

    # One brand/entity plus the same distinctive number and action is enough when
    # headlines otherwise share several words. This catches e.g. two reports about
    # one 100-creators campaign without merging unrelated stories about the brand.
    if len(entities) >= 1 and families and shared_numbers and len(shared_tokens) >= 3:
        return 0.90, "та сама подія в іншому джерелі: сутність, дія й числовий факт збігаються"

    # Strong title overlap with a shared entity is useful for differently worded
    # follow-ups that add background but describe the same announcement.
    if len(entities) >= 1 and len(shared_tokens) >= 5 and jaccard >= 0.34:
        return 0.89, "сильний міжджерельний збіг заголовків і ключової сутності"
    return None


def find_event_duplicate_rc60(
    current_title: str,
    current_body: str,
    recent_published: Iterable[Mapping[str, Any] | Any],
):
    from . import event_dedupe as event_module

    rows = list(recent_published)
    original = getattr(event_module, "_rc60_original_find_event_duplicate", None)
    if original is not None:
        match = original(current_title, current_body, rows)
        if match is not None:
            return match

    best = None
    for row in rows:
        result = _cross_source_title_match(current_title, row)
        if result is None:
            continue
        score, reason = result
        try:
            article_id = int(_row_value(row, "id", 0) or 0)
        except Exception:
            article_id = 0
        if not article_id:
            continue
        candidate = event_module.DuplicateMatch(article_id=article_id, score=score, reason=reason)
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def _title_duplicate_rc60(article: Any, recent: list[Any]) -> int | None:
    from . import production_pipeline as production

    original = getattr(production, "_rc60_original_title_duplicate", None)
    if original is not None:
        hit = original(article, recent)
        if hit is not None:
            return hit
    title = str(_row_value(article, "title", "") or "")
    for row in recent:
        if _cross_source_title_match(title, row) is not None:
            try:
                return int(_row_value(row, "id", 0) or 0) or None
            except Exception:
                continue
    return None


def _repair_language(channel: Any, article: Any, body: str, *, hard_limit: int) -> str:
    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc51_feedback as rc51
    from . import rc59_universal_policy as rc59
    from .evidence_pack import build_evidence_pack

    db = rc51._ACTIVE_DB
    policy = db.rc59_get_channel_policy(int(channel.id)) if db is not None else rc59.default_policy(channel)
    source = build_evidence_pack(article, char_budget=6000).text
    issues = ", ".join(latin_jargon_issues(body))
    prompt = f"""Ти мовний редактор українського Telegram-посту.

Виправ ЛИШЕ мову і термінологію готового тексту. Не змінюй новинний кут, не додавай і не вилучай факти, числа, дати, власні назви або причинні зв'язки.
Переклади загальний англійський професійний жаргон природною українською. Власні назви брендів, компаній, продуктів, кампаній, моделей, стандартів і абревіатури залишай як є.
Якщо англійський спеціальний термін без українського еквівалента необхідний, коротко поясни його українською при першій згадці.
Проблемні елементи, знайдені QA: {issues}.
Дотримуйся редакційного стилю каналу:
{rc59.policy_text(policy)}

SOURCE EVIDENCE PACK, єдине джерело фактів:
{source}

ПОТОЧНИЙ ТЕКСТ:
{body}

Поверни ТІЛЬКИ виправлений український пост, без пояснень."""
    allowed_years = rc40._rc40_allowed_years(article)
    allowed_numbers = rc40._rc40_allowed_numbers(article)

    def validator(raw: str) -> None:
        checked = rc40._validated_ua_body(
            raw, article=article, allowed_years=allowed_years,
            allowed_numbers=allowed_numbers, hard_limit=hard_limit,
        )
        if rc59.refusal_meta_reason(checked):
            raise production.ProductionPipelineError("Мовний редактор повернув метакоментар.")
        remaining = latin_jargon_issues(checked)
        if remaining:
            raise production.ProductionPipelineError("Залишився неперекладений англомовний жаргон: " + ", ".join(remaining))

    result = production.run_ai(
        prompt, validator=validator,
        max_output_tokens=620, local_prompt=prompt, local_max_output_tokens=620,
        cloud_timeout_seconds=28, local_timeout_seconds=18, task_timeout_seconds=70,
        local_repair=False, suppress_provider_on_quota=False,
        allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
    )
    return rc40._validated_ua_body(
        result.text, article=article, allowed_years=allowed_years,
        allowed_numbers=allowed_numbers, hard_limit=hard_limit,
    )


def decide_rc60(channel: Any, article: Any, recent: list[Any], *, hard_limit: int, format_marker: str | None = None) -> Decision:
    from . import production_pipeline as production
    from . import rc59_universal_policy as rc59

    decision = rc59.decide_rc59(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)
    if decision.decision != "publish":
        return decision

    issues = latin_jargon_issues(decision.telegram_teaser)
    if not issues:
        return replace(decision, reason=decision.reason + " RC60 language-mix QA PASS.")

    LOG.info("RC60 language repair article_id=%s issues=%s", _row_value(article, "id", "?"), ",".join(issues))
    try:
        repaired = _repair_language(channel, article, decision.telegram_teaser, hard_limit=hard_limit)
    except Exception as exc:
        raise production.PostAIQAExhausted(
            "RC60: не вдалося безпечно прибрати англомовний професійний жаргон: " + str(exc),
            (str(exc),), provider_outage="Немає доступного AI-провайдера" in str(exc),
        ) from exc

    remaining = latin_jargon_issues(repaired)
    if remaining:
        raise production.PostAIQAExhausted(
            "RC60: після мовної редактури лишився неперекладений жаргон: " + ", ".join(remaining),
            tuple(remaining), provider_outage=False,
        )
    return replace(
        decision,
        telegram_teaser=repaired,
        full_article_uk=repaired,
        event_summary=repaired[:1000],
        reason=decision.reason + " RC60 language repair PASS.",
    )


def install_rc60_editorial_quality() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import event_dedupe as event_module
    from . import production_pipeline as production
    from . import rc59_universal_policy as rc59
    from . import service as service_module

    # Preserve originals explicitly so the wrapper never recurses after install.
    if not hasattr(event_module, "_rc60_original_find_event_duplicate"):
        event_module._rc60_original_find_event_duplicate = event_module.find_event_duplicate
    if not hasattr(production, "_rc60_original_title_duplicate"):
        production._rc60_original_title_duplicate = production._title_duplicate

    original_writer_prompt = rc59._writer_prompt

    def writer_prompt_rc60(policy, channel, article, selector, *, hard_limit):
        return original_writer_prompt(policy, channel, article, selector, hard_limit=hard_limit) + "\n\n" + _ua_language_appendix()

    def decide(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        return decide_rc60(channel, article, recent, hard_limit=hard_limit, format_marker=format_marker)

    rc59._writer_prompt = writer_prompt_rc60
    production._title_duplicate = _title_duplicate_rc60
    event_module.find_event_duplicate = find_event_duplicate_rc60
    service_module.find_event_duplicate = find_event_duplicate_rc60
    production.decide = decide
    service_module.decide = decide
    production.POST_FORMAT_PREFIX = "telegram-post-v37:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v37:"

    _INSTALLED = True
    LOG.info("RC60 installed: cross-source event dedupe + natural-Ukrainian jargon QA; channel policy remains universal")
