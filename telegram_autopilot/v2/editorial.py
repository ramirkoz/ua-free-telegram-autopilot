from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..anti_slop import assess_ukrainian_slop, compact_feedback, sanitize_text
from ..evidence_pack import build_evidence_pack
from ..fact_guard import actionable_source_urls, article_non_actionable_urls, source_urls_in_text, strip_non_actionable_article_urls, validate_fact_guard
from ..language import looks_ukrainian
from ..grammar_guard import hard_grammar_blockers, needs_grammar_polish, preserves_content
from ..language_tool_local import apply_local_languagetool_detailed
from ..rewrite_verifier import assess_rewrite, hard_editorial_blockers
from ..ukrainian_quality import apply_safe_ukrainian_fixes, final_language_blockers, human_style_issues, language_quality_issues
from .ai_gateway import AIGateway, GatewayExhausted
from .source_attribution import (
    require_source_context, source_body_attribution_issues, source_body_context_name, source_body_instruction,
    source_body_hard_limit, source_context_name,
)
from .domain import BlockedBy, ChannelConfig, ChannelMode, Decision, EditorialRuntimeProfile, Stage
from .loghub import event
from .learning import LearningEngine
from .storage import V2Store
from .topic_saturation import topic_saturation_reason


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _clean(value: Any, limit: int = 12000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _parse_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("AI не повернув JSON")
    obj = json.loads(text[a : b + 1])
    if not isinstance(obj, dict):
        raise ValueError("AI JSON має бути object")
    return obj


def _source_pack(article: Any, budget: int = 6000) -> str:
    try:
        return build_evidence_pack(article, char_budget=budget).text
    except Exception:
        return (_clean(_v(article, "title", ""), 700) + "\n" + _clean(_v(article, "raw_text", ""), budget)).strip()


def _telegram_meta(article: Any) -> dict[str, Any]:
    try:
        layout = json.loads(str(_v(article, "article_layout_json", "") or "{}"))
    except Exception:
        return {}
    tg = layout.get("telegram") if isinstance(layout, dict) else None
    return tg if isinstance(tg, dict) else {}


def _rule_mentions(rules: str, *tokens: str) -> bool:
    low = str(rules or "").casefold()
    return any(token.casefold() in low for token in tokens)


def deterministic_monitoring_exclusion(channel: ChannelConfig, article: Any) -> str:
    """Apply local exclusions only when the operator explicitly configured them."""
    rules = channel.policy.rejection_rules
    if not rules.strip():
        return ""
    low = (str(_v(article, "title", "")) + "\n" + str(_v(article, "raw_text", ""))).casefold()
    meta = _telegram_meta(article)
    if bool(meta.get("forwarded")) and _rule_mentions(rules, "репост", "переслан", "forward"):
        return "Нативний Telegram-репост/переслане повідомлення"
    if _rule_mentions(rules, "хвилин", "мовчан", "пошан") and (
        "хвилина мовчання" in low or ("хвилин" in low and ("мовчан" in low or "пошан" in low))
    ):
        return "Хвилина мовчання/пошани"
    if _rule_mentions(rules, "тривог", "відбій", "летить", "повітря") and any(
        re.search(pattern, low, re.I)
        for pattern in (
            r"\bповітрян\w*\s+тривог",
            r"\bвідбій\b.*\bтривог",
            r"\bтривог\w*\s+скас",
            r"\b(бпла|ракета|шахед\w*)\b.*\b(летить|рухаєть|курс\w*)",
            r"\b(летить|рухаєть)\b.*\b(бпла|ракета|шахед\w*)",
        )
    ):
        return "Оперативне повідомлення про тривогу/відбій/рух загрози"
    if _rule_mentions(rules, "привітан", "календар", "свят", "пам'ятн", "пам’ятн") and any(
        token in low for token in ("вітаємо", "привітав", "привітала", "привітали", "щиро віта", "з нагоди", "побажав", "побажала")
    ):
        return "Протокольне/календарне привітання"
    if _rule_mentions(rules, "настр", "побажан", "гарного дня", "без поді", "мотивац") and any(
        token in low for token in ("гарного дня", "вдалого дня", "вдалого тижня", "спокійного ранку", "доброго ранку", "хорошого настрою", "настрій на день")
    ):
        return "Побажання/пост настрою без інформаційної події"
    return ""


def extract_actionable_facts(article: Any) -> list[str]:
    raw = str(_v(article, "raw_text", "") or "")
    source = str(_v(article, "title", "") or "") + "\n" + raw
    source_name = str(_v(article, "source_name", "") or "")
    out: list[str] = []

    def add(label: str, value: str) -> None:
        clean = " ".join(str(value or "").split()).strip(" ,;")
        item = f"{label}: {clean}" if clean else ""
        if item and item not in out:
            out.append(item[:420])

    for url in actionable_source_urls(source, source_name=source_name):
        add("URL", url)
    for email in re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", source, flags=re.I):
        add("EMAIL", email)
    for phone in re.findall(r"(?<!\d)(?:\+?\d[\d\s()\-]{7,}\d)(?!\d)", source):
        digits = re.sub(r"\D", "", phone)
        if 8 <= len(digits) <= 15:
            add("ТЕЛЕФОН", phone)
    for line in (part.strip() for part in raw.splitlines() if part.strip()):
        low = line.casefold()
        if any(token in low for token in ("адрес", "вул.", "вулиц", "просп.", "проспект", "зупинка", "графік", "працює", "прийом", "реєстрац", "дедлайн")) and (re.search(r"\d", line) or "адрес" in low or "реєстрац" in low):
            add("ПРАКТИЧНА ДЕТАЛЬ", line)
    return out[:20]


def _number_tokens(text: str) -> set[str]:
    clean = re.sub(r"https?://\S+", "", str(text or ""))
    result: set[str] = set()
    for token in re.findall(r"(?<!\w)\d[\d\s.,:/-]*\d|(?<!\w)\d(?!\w)", clean):
        normalized = re.sub(r"[\s,._]", "", token).strip()
        if normalized:
            result.add(normalized)
    return result


TELEGRAM_BODY_SAFE_MAX = 880
TRUSTED_EDITOR_PROVIDERS = ("gemini", "nvidia", "groq", "cloudflare", "codex")


_ABSENCE_FILLER_RE = re.compile(
    r"\b(?:додатков\w*\s+інформац\w*|детал\w*|термін\w*|строк\w*)[^.!?]{0,55}\b(?:не\s+надан\w*|відсутн\w*|невідом\w*)",
    re.I,
)
_GENERIC_ADVICE_RE = re.compile(
    r"\b(?:зберігайте\s+спокій(?:но)?|стежте\s+за\s+своїми\s+речами|слідкуйте\s+за\s+своїми\s+речами|бережіть\s+себе|будьте\s+уважн\w*)\b",
    re.I,
)

# Factual-monitoring is allowed to paraphrase facts, but not invent an editorial
# conclusion around them. These are generic discourse patterns, never channel names.
# A phrase is blocked only when the source itself contains no matching signal.
_MONITORING_COMMENTARY_RULES: tuple[tuple[re.Pattern[str], tuple[str, ...], str], ...] = (
    (re.compile(r"\b(?:це|такий|така|таке|такі)\s+(?:свідчить|свідчать|демонструє|демонструють|показує|показують|підкреслює|підкреслюють|підтверджує|підтверджують|нагадує|нагадують)\b", re.I),
     ("свідч", "демонстр", "показує", "показують", "підкресл", "підтвердж", "нагадує", "нагадують"),
     "додано редакційний висновок/інтерпретацію, якої немає у джерелі"),
    (re.compile(r"\bважлив\w*\s+(?:крок|сигнал|нагадування|приклад|підтвердження)\b", re.I),
     ("важлив", "крок", "сигнал", "нагадув", "приклад", "підтвердж"),
     "додано оцінку важливості, якої немає у джерелі"),
    (re.compile(r"\bце\s+(?:ще\s+раз\s+)?(?:доводить|показує|підтверджує|нагадує)\b", re.I),
     ("довод", "показує", "підтвердж", "нагадує"),
     "додано авторський підсумок, якого немає у джерелі"),
    (re.compile(r"\b(?:продовжує|продовжують)\s+(?:працювати|підтримувати|допомагати|розвивати|дбати)\b", re.I),
     ("продовжує", "продовжують"),
     "додано узагальнення про тривалу діяльність, якого немає у джерелі"),
    (re.compile(r"\b(?:це|такий|така|таке|такі|подібн\w*)(?:\s+[А-Яа-яІіЇїЄєҐґ'’.-]+){0,3}\s+(?:допомагає|допомагають|дозволяє|дозволяють|сприяє|сприяють|покращує|покращують|посилює|посилюють|зміцнює|зміцнюють|створює|створюють)\b", re.I),
     ("допомага", "дозволя", "сприя", "покращ", "посил", "зміцн", "створю"),
     "додано пояснення ефекту/користі, якого немає у джерелі"),
    (re.compile(r"\b(?:важливо|показово|символічно|цінно|принципово|особливо\s+важливо)\b", re.I),
     ("важлив", "показов", "символіч", "цінн", "принципов"),
     "додано оцінне судження, якого немає у джерелі"),
    (re.compile(r"\b(?:отже|таким\s+чином|зрештою)\b", re.I),
     ("отже", "таким чином", "зрештою"),
     "додано авторський висновок, якого немає у джерелі"),
    (re.compile(r"\b(?:це|такий|така|таке|такі)\s+(?:приклад|нагадування|свідчення|підтвердження|можливість|ознака)\b", re.I),
     ("приклад", "нагадув", "свідчен", "підтвердж", "можлив", "ознака"),
     "додано редакційну рамку/оцінку, якої немає у джерелі"),
)


def _source_text(article: Any) -> str:
    return " ".join(str(_v(article, "raw_text", "") or "").split()).strip()


def _monitoring_limits(channel: ChannelConfig, article: Any, body_hard_max: int) -> tuple[int, int, int]:
    """Do not force a tiny community notice to grow into a synthetic article."""
    p = channel.policy
    configured_max = max(120, min(int(p.target_max_chars), int(body_hard_max)))
    configured_min = max(80, min(int(p.target_min_chars), configured_max))
    if channel.mode != ChannelMode.MONITORING:
        return configured_min, configured_max, int(body_hard_max)

    source_len = len(_source_text(article))
    if source_len <= 220:
        effective_min = 80
        effective_max = min(configured_max, max(180, source_len + 100))
    elif source_len <= 420:
        effective_min = min(configured_min, max(90, int(source_len * 0.42)))
        effective_max = min(configured_max, max(260, source_len + 120))
    elif source_len <= 650:
        effective_min = min(configured_min, max(120, int(source_len * 0.46)))
        effective_max = min(configured_max, max(360, source_len + 100))
    else:
        effective_min = configured_min
        effective_max = configured_max
    effective_max = max(effective_min, min(effective_max, int(body_hard_max)))
    return effective_min, effective_max, effective_max


def _monitoring_grounding_blockers(article: Any, value: str) -> tuple[str, ...]:
    """Block common padding that states things the source never said."""
    source = _source_text(article).casefold()
    text = str(value or "")
    issues: list[str] = []
    for match in _ABSENCE_FILLER_RE.finditer(text):
        fragment = " ".join(match.group(0).split()).casefold()
        if fragment not in source and not any(token in source for token in ("не надан", "відсутн", "невідом")):
            issues.append("додано службову фразу про відсутні деталі/терміни, якої немає у джерелі")
            break
    if _GENERIC_ADVICE_RE.search(text) and not _GENERIC_ADVICE_RE.search(source):
        issues.append("додано загальну пораду/мораль, якої немає у джерелі")
    for pattern, source_signals, message in _MONITORING_COMMENTARY_RULES:
        if not pattern.search(text):
            continue
        if not any(signal in source for signal in source_signals):
            issues.append(message)
    return tuple(dict.fromkeys(issues))


def _source_body_policy_issues(channel: ChannelConfig, article: Any, value: str) -> tuple[str, ...]:
    issues = list(source_body_attribution_issues(channel, article, value))
    if channel.mode == ChannelMode.MONITORING:
        source = str(_v(article, "raw_text", "") or "")
        source_name = str(_v(article, "source_name", "") or "")
        excluded = set(article_non_actionable_urls(article))
        actionable = set(actionable_source_urls(source, source_name=source_name, excluded_urls=excluded))
        source_urls = set(source_urls_in_text(source))
        candidate_urls = set(source_urls_in_text(str(value or "")))
        # Canonical/source-message/media URLs are attribution or already attached media,
        # never reader-action links. Block them even when the model inserted the URL
        # itself and raw_text did not contain it literally.
        redundant = sorted((candidate_urls & (source_urls | excluded)) - actionable)
        if redundant:
            issues.append("у тіло повернуто непрактичне посилання на матеріал/джерело, яке дублює footer")
    return tuple(dict.fromkeys(issues))


def validate_writer_output(
    article: Any,
    text: str,
    *,
    min_chars: int,
    max_chars: int,
    hard_max_chars: int | None = None,
    required_context: str = "",
    slop_profile: str = "",
) -> str:
    # Gate 1 is deterministic sanitation: strip invisible/bidi junk before any
    # language or factual validation. This mirrors the upstream anti-ai-slop
    # architecture but keeps all runtime work local and dependency-free.
    value = apply_safe_ukrainian_fixes(sanitize_text(str(text or ""))).strip()
    if len(value) < max(80, int(min_chars) * 2 // 3):
        raise ValueError("Непридатна довжина Telegram-тексту: надто коротко")
    if hard_max_chars is not None and len(value) > int(hard_max_chars):
        raise ValueError(f"Непридатна довжина Telegram-тексту: понад жорсткий ліміт {int(hard_max_chars)}")
    if len(value) > max(int(max_chars) + 250, int(max_chars) * 3 // 2):
        raise ValueError("Непридатна довжина Telegram-тексту: надто довго")
    if not looks_ukrainian(value):
        raise ValueError("AI не повернув природний український текст")
    require_source_context(value, required_context)
    validate_fact_guard(article, value)
    source = "\n".join((
        str(_v(article, "source_name", "")),
        str(_v(article, "title", "")),
        str(_v(article, "raw_text", "")),
    ))
    invented = sorted(_number_tokens(value) - _number_tokens(source))
    if invented:
        raise ValueError("AI додав число, якого немає у джерелі: " + ", ".join(invented[:10]))
    if value.count("(") != value.count(")") or value.count("«") != value.count("»"):
        raise ValueError("Незакриті дужки/лапки")
    paragraphs = [" ".join(part.split()).strip() for part in re.split(r"\n+", value) if part.strip()]
    if len(value) >= 350 and len(paragraphs) < 2:
        raise ValueError("Редакційний QA: суцільна стіна тексту без абзаців")
    paragraph_limit = 420 if (hard_max_chars or max_chars) <= 900 else 620
    if any(len(part) > paragraph_limit for part in paragraphs):
        raise ValueError("Редакційний QA: надто довгий абзац")
    if re.search(r"(?iu)([A-Za-zА-Яа-яІіЇїЄєҐґ])\1{7,}", value):
        raise ValueError("Редакційний QA: пошкоджений повтор символу")
    if re.search(r"([!?.,:;])\1{5,}", value):
        raise ValueError("Редакційний QA: пошкоджена серія пунктуації")
    if re.search(r"(?:\b(?:і|й|але|або|бо|що|через|після|до|для|з|із|на|у|в|та)\s*)$", value.casefold().rstrip()):
        raise ValueError("Останнє речення обірване")
    hard_issues = hard_editorial_blockers(value)
    if hard_issues:
        raise ValueError("Жорсткий QA: " + "; ".join(hard_issues[:4]))
    language_blockers = final_language_blockers(value)
    if language_blockers:
        raise ValueError("Жорсткий мовний QA: " + "; ".join(language_blockers[:4]))
    grammar_blockers = hard_grammar_blockers(value)
    if grammar_blockers:
        raise ValueError("Жорсткий граматичний QA: " + "; ".join(grammar_blockers[:4]))
    readability = assess_rewrite(value, hard_limit=int(hard_max_chars or max_chars))
    if not readability.publishable:
        raise ValueError("Readability QA: " + "; ".join(readability.issues[:5]))
    issues = list(language_quality_issues(value)) + list(human_style_issues(value))
    if len(issues) >= 3:
        raise ValueError("Мовний QA: " + "; ".join(issues[:3]))
    if slop_profile:
        slop = assess_ukrainian_slop(value, profile=slop_profile)
        if not slop.publishable:
            raise ValueError(
                f"UA Anti-Slop {slop.score}/{slop.gate}: " + compact_feedback(slop)
            )
        value = slop.sanitized_text
    return value


def _is_commercial_editorial(channel: ChannelConfig) -> bool:
    try:
        return EditorialRuntimeProfile(str(channel.editorial_runtime_profile)) == EditorialRuntimeProfile.COMMERCIAL_EDITORIAL
    except Exception:
        return False


def _anti_slop_profile(channel: ChannelConfig) -> str:
    # The gate is configured by channel behaviour, never by channel ID/name.
    if channel.mode == ChannelMode.MONITORING:
        return "community"
    if _is_commercial_editorial(channel):
        return "commercial"
    return "news"


_STANDARD_EDITORIAL_THRESHOLDS: dict[str, int] = {
    "standard_score": 60, "standard_payoff": 50, "standard_retellability": 48,
    "standard_signal": 52, "standard_why_now": 32, "standard_novelty_exception": 78,
    "mechanism_lane_fit": 60, "mechanism_lane_score": 48, "mechanism_lane_mechanism": 60,
    "mechanism_lane_payoff": 55, "mechanism_lane_retellability": 50,
    "insight_lane_fit": 60, "insight_lane_score": 48, "insight_lane_insight": 62,
    "insight_lane_payoff": 55, "insight_lane_retellability": 48,
    "creative_lane_fit": 60, "creative_lane_score": 50, "creative_lane_novelty": 65,
    "creative_lane_payoff": 55, "creative_lane_retellability": 58,
}

_COMMERCIAL_EDITORIAL_THRESHOLDS: dict[str, int] = {
    "commercial_case_fit": 60, "commercial_case_score": 52, "commercial_transferability": 45, "commercial_anchor": 58,
    "creative_case_fit": 65, "creative_case_score": 48, "creative_execution": 68, "creative_anchor": 52,
    "mechanism_case_fit": 70, "mechanism_case_score": 46, "mechanism": 65, "mechanism_transferability": 50,
    # RC69 broad-audience lane. Values remain visible/editable through
    # editorial_thresholds_json in Channel Settings.
    "broad_interest_fit": 54, "broad_interest_score": 50,
    "broad_general_interest": 58, "broad_retellability": 58,
    "broad_culture_or_surprise": 55,
}

def _editorial_thresholds(channel: ChannelConfig) -> dict[str, int]:
    base = dict(_COMMERCIAL_EDITORIAL_THRESHOLDS if _is_commercial_editorial(channel) else _STANDARD_EDITORIAL_THRESHOLDS)
    try:
        raw = json.loads(str(channel.editorial_thresholds_json or "{}"))
    except Exception:
        raw = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in base:
                continue
            try:
                base[key] = max(0, min(100, int(float(value))))
            except Exception:
                continue
    return base


def _practical_literals(article: Any) -> list[tuple[str, str]]:
    source = str(_v(article, "raw_text", "") or "")
    source_name = str(_v(article, "source_name", "") or "")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in actionable_source_urls(source, source_name=source_name, excluded_urls=article_non_actionable_urls(article)):
        if value not in seen:
            seen.add(value); out.append(("Деталі/реєстрація", value))
    for email in re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", source, flags=re.I):
        if email not in seen:
            seen.add(email); out.append(("Email", email))
    for phone in re.findall(r"(?<!\d)(?:\+?\d[\d\s()\-]{7,}\d)(?!\d)", source):
        digits = re.sub(r"\D", "", phone)
        value = " ".join(phone.split())
        if 8 <= len(digits) <= 15 and value not in seen:
            seen.add(value); out.append(("Телефон", value))
    return out[:8]


def restore_practical_literals(article: Any, text: str, *, hard_max_chars: int) -> str:
    value = str(text or "").strip()
    missing = [(label, literal) for label, literal in _practical_literals(article) if literal not in value]
    if not missing:
        return value
    suffix = "\n\n" + "\n".join(f"{label}: {literal}" for label, literal in missing)
    if len(value) + len(suffix) > int(hard_max_chars):
        raise ValueError(
            f"AI прибрав практичні контакти/URL, а відновлення перевищує ліміт {int(hard_max_chars)}"
        )
    return value + suffix


def prepublish_quality_issues(channel: ChannelConfig, article: Any, text: str) -> tuple[str, ...]:
    """Final deterministic gate at the publication boundary.

    It intentionally performs no AI work.  READY rows imported from an older
    build or created before a channel-rule change must still satisfy the current
    channel policy immediately before Telegram sees them.
    """
    value = str(text or "").strip()
    issues: list[str] = []
    if not value:
        return ("порожній final_text",)
    source_policy = _source_body_policy_issues(channel, article, value)
    issues.extend(source_policy)
    if channel.mode == ChannelMode.MONITORING:
        issues.extend(_monitoring_grounding_blockers(article, value))
    try:
        body_hard_max = source_body_hard_limit(channel, article, default_body_limit=TELEGRAM_BODY_SAFE_MAX)
        effective_min, effective_max, validation_hard_max = _monitoring_limits(channel, article, body_hard_max)
        validate_writer_output(
            article, value, min_chars=effective_min, max_chars=effective_max,
            hard_max_chars=validation_hard_max, required_context=source_body_context_name(channel, article),
            slop_profile=_anti_slop_profile(channel),
        )
    except Exception as exc:
        issues.append(str(exc))
    return tuple(dict.fromkeys(item for item in issues if str(item).strip()))


@dataclass(slots=True)
class EditorialOutcome:
    decision: Decision
    reason: str = ""
    angle: str = ""
    fit_score: int = 0
    editorial_value_score: int | None = None
    draft_text: str = ""
    final_text: str = ""
    provider: str = ""
    model: str = ""


class EditorialEngine:
    def __init__(self, store: V2Store, gateway: AIGateway):
        self.store = store
        self.gateway = gateway
        self.learning = LearningEngine(store)

    def select(self, channel: ChannelConfig, article: Any) -> EditorialOutcome:
        return self._select_monitoring(channel, article) if channel.mode == ChannelMode.MONITORING else self._select_editorial(channel, article)

    def _select_monitoring(self, channel: ChannelConfig, article: Any) -> EditorialOutcome:
        local = deterministic_monitoring_exclusion(channel, article)
        if local:
            return EditorialOutcome(Decision.REJECT, reason="MONITORING_LOCAL_REJECT: " + local, fit_score=0)
        inclusion = channel.policy.selection_rules.strip()
        exclusion = channel.policy.rejection_rules.strip()
        if not inclusion and not exclusion:
            return EditorialOutcome(Decision.PUBLISH, reason="MONITORING_PASS: explicit inclusion/exclusion empty; interest gates disabled", fit_score=100, angle="Передай факт точно і стисло.")
        prompt = f"""Ти UNIVERSAL MONITORING POLICY GATE.
Не оцінюй цікавість, wow, editorial value, баланс тем або broad appeal. Застосуй ТІЛЬКИ ручні правила цього каналу.
INCLUSION RULES:\n{inclusion or 'Не задано: inclusion виконаний.'}\n\nEXCLUSION RULES:\n{exclusion or 'Не задано.'}
Рішення: explicit exclusion -> reject; якщо inclusion заданий і SOURCE йому не відповідає -> reject; сумнів -> publish.
SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 3600)}
Поверни ТІЛЬКИ JSON: {{"included":true,"excluded":false,"reason":"коротко"}}"""

        def parse(raw: str):
            obj = _parse_json(raw)
            return bool(obj.get("included", True)), bool(obj.get("excluded", False)), _clean(obj.get("reason"), 500)

        result = self.gateway.run(prompt, validator=lambda raw: parse(raw), max_output_tokens=190, timeout_seconds=22, purpose="monitoring_selector")
        included, excluded, reason = parse(result.text)
        rejected = excluded or (bool(inclusion) and not included)
        return EditorialOutcome(
            Decision.REJECT if rejected else Decision.PUBLISH,
            reason=("MONITORING_POLICY_REJECT: " if rejected else "MONITORING_POLICY_PASS: ") + (reason or "none"),
            fit_score=0 if rejected else 100,
            angle="" if rejected else "Передай факт точно і стисло.",
            provider=result.provider,
            model=result.model,
        )

    def _select_editorial(self, channel: ChannelConfig, article: Any) -> EditorialOutcome:
        p = channel.policy
        learning = self.learning.topic_assessment(channel.id, article)
        if learning.hard_suppress:
            reason = (
                f"LEARNING_ADMIN_DISLIKE: very close recent editor-disliked story #{learning.matched_article_id}; "
                f"similarity={learning.matched_similarity:.2f}"
            )
            event("learning", "topic hard suppress", channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0), detail=reason)
            return EditorialOutcome(Decision.REJECT, reason=reason, fit_score=0)
        topic_memory = self.learning.topic_memory_block(channel.id, article)
        prompt = f"""Ти CHANNEL-FIT SELECTOR Telegram-автопілота. Перевір лише відповідність SOURCE політиці каналу. Не оцінюй broad appeal або wow.
PURPOSE: {p.purpose}\nAUDIENCE: {p.audience}\nSELECTION: {p.selection_rules}\nEXCLUSIONS: {p.rejection_rules}\nEXTRA: {p.selector_extra_prompt}
{topic_memory}
SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 3600)}
Для CPU-local fallback одразу оціни також editorial value, щоб не робити окремий дорогий AI-виклик.
Поверни ТІЛЬКИ JSON: {{"decision":"publish" або "reject","fit_score":0,"reason":"коротко","angle":"кут","topic_tags":["..."],"novelty":0,"consequence_or_insight":0,"mechanism":0,"reader_payoff":0,"retellability":0,"concrete_stakes":0,"why_now":0,"curiosity_only":false}}"""

        def parse_fit(raw: str):
            obj = _parse_json(raw)
            decision = str(obj.get("decision") or "").casefold()
            if decision not in {"publish", "reject"}:
                raise ValueError("invalid decision")
            return obj

        fit_result = self.gateway.run(prompt, validator=lambda raw: parse_fit(raw), max_output_tokens=210, timeout_seconds=25, purpose="editorial_selector")
        fit = parse_fit(fit_result.text)
        raw_score = max(0, min(100, int(fit.get("fit_score", 0) or 0)))
        # RC54: a categorical PUBLISH with fit=9 is internally contradictory. For
        # channels with the explicit commercial editorial profile, trust the categorical channel-fit decision and let the dedicated
        # commercial value gate make the second decision instead of killing it here.
        if _is_commercial_editorial(channel) and fit["decision"] == "publish" and raw_score < 60:
            event("editorial", "normalized contradictory sold fit score", level=30, channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0), raw_fit=raw_score, normalized_fit=60)
            raw_score = 60
        score = max(0, min(100, raw_score + int(learning.fit_adjustment)))
        if learning.fit_adjustment:
            event(
                "learning", "topic soft adjustment", channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0),
                admin_score=round(learning.admin_score, 3), audience_score=round(learning.audience_score, 3),
                adjustment=int(learning.fit_adjustment), raw_fit=raw_score, adjusted_fit=score,
            )
        if fit["decision"] == "reject":
            return EditorialOutcome(Decision.REJECT, reason=_clean(fit.get("reason"), 600), fit_score=score, provider=fit_result.provider, model=fit_result.model)
        value_keys = ("novelty", "consequence_or_insight", "mechanism", "reader_payoff", "retellability", "concrete_stakes", "why_now")
        if _is_commercial_editorial(channel):
            value = self._sold_value_gate(article)
            allowed, code, value_score = self._sold_value_allowed(value, score, _editorial_thresholds(channel))
            if not allowed:
                return EditorialOutcome(Decision.REJECT, reason=f"SOLD_VALUE_REJECT score={value_score}; code={code}; " + _clean(value.get("reason"), 420), fit_score=score, editorial_value_score=value_score, provider=fit_result.provider, model=fit_result.model)
            return EditorialOutcome(Decision.PUBLISH, reason=f"SOLD_VALUE_PASS score={value_score}; lane={code}; fit={score}; learning={learning.fit_adjustment:+d}", angle=_clean(fit.get("angle"), 500), fit_score=score, editorial_value_score=value_score, provider=fit_result.provider, model=fit_result.model)
        if fit_result.provider == "local" and all(key in fit for key in value_keys):
            value = {key: max(0, min(100, int(float(fit.get(key, 0) or 0)))) for key in value_keys}
            value["curiosity_only"] = bool(fit.get("curiosity_only", False))
            value["reason"] = _clean(fit.get("reason"), 420)
            event("ai", "CPU local fit/value combined", channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0))
        else:
            value = self._value_gate(article)
        allowed, code, value_score = self._value_allowed(value, score, _editorial_thresholds(channel))
        if not allowed:
            return EditorialOutcome(Decision.REJECT, reason=f"EDITORIAL_VALUE_REJECT score={value_score}; code={code}; " + _clean(value.get("reason"), 420), fit_score=score, editorial_value_score=value_score, provider=fit_result.provider, model=fit_result.model)
        return EditorialOutcome(Decision.PUBLISH, reason=f"EDITORIAL_VALUE_PASS score={value_score}; lane={code}; fit={score}; learning={learning.fit_adjustment:+d}", angle=_clean(fit.get("angle"), 500), fit_score=score, editorial_value_score=value_score, provider=fit_result.provider, model=fit_result.model)

    def _sold_value_gate(self, article: Any) -> dict[str, Any]:
        prompt = f"""Ти COMMERCIAL + BROAD-AUDIENCE EDITORIAL VALUE GATE. Матеріал уже пройшов channel fit.
Оціни 0..100 дві незалежні речі.
1) Профільний commercial case: commercial_mechanism, consumer_behavior, creative_execution, measurable_result, strategic_transferability, why_now.
2) Цікавість широкій аудиторії: general_interest, retellability, culture_signal, surprise_or_conflict, consumer_relevance.
ВАЖЛИВО: матеріал НЕ мусить бути навчальним маркетинговим кейсом. Попкультура × бренд, мем, вірусний феномен, дивний товар/ціна, незвична колаборація, споживча поведінка, техно/культурний сюжет або брендова провокація можуть бути сильними самі по собі, якщо їх хочеться дочитати й переказати людині поза професією.
SOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 3600)}
Поверни ТІЛЬКИ JSON: {{"commercial_mechanism":0,"consumer_behavior":0,"creative_execution":0,"measurable_result":0,"strategic_transferability":0,"why_now":0,"general_interest":0,"retellability":0,"culture_signal":0,"surprise_or_conflict":0,"consumer_relevance":0,"reason":"коротко"}}"""

        def parse(raw: str):
            obj = _parse_json(raw)
            for key in (
                "commercial_mechanism", "consumer_behavior", "creative_execution",
                "measurable_result", "strategic_transferability", "why_now",
                "general_interest", "retellability", "culture_signal",
                "surprise_or_conflict", "consumer_relevance",
            ):
                obj[key] = max(0, min(100, int(float(obj.get(key, 0) or 0))))
            return obj

        return parse(self.gateway.run(prompt, validator=lambda raw: parse(raw), max_output_tokens=260, timeout_seconds=25, purpose="commercial_value_gate").text)

    @staticmethod
    def _sold_value_allowed(data: Mapping[str, Any], fit: int, thresholds: Mapping[str, int] | None = None) -> tuple[bool, str, int]:
        t = dict(_COMMERCIAL_EDITORIAL_THRESHOLDS); t.update(dict(thresholds or {}))
        mechanism = int(data.get("commercial_mechanism", 0)); behavior = int(data.get("consumer_behavior", 0)); creative = int(data.get("creative_execution", 0)); result = int(data.get("measurable_result", 0)); transfer = int(data.get("strategic_transferability", 0)); why_now = int(data.get("why_now", 0))
        general = int(data.get("general_interest", 0)); retell = int(data.get("retellability", 0)); culture = int(data.get("culture_signal", 0)); surprise = int(data.get("surprise_or_conflict", 0)); consumer = int(data.get("consumer_relevance", 0))
        score = int(round(mechanism*.24 + behavior*.18 + creative*.16 + result*.18 + transfer*.18 + why_now*.06))
        broad_score = int(round(general*.30 + retell*.25 + culture*.15 + surprise*.15 + consumer*.15))
        if fit >= t["broad_interest_fit"] and broad_score >= t["broad_interest_score"] and general >= t["broad_general_interest"] and retell >= t["broad_retellability"] and max(culture, surprise, consumer) >= t["broad_culture_or_surprise"]:
            return True, "broad_audience_commercial", broad_score
        if fit >= t["commercial_case_fit"] and score >= t["commercial_case_score"] and transfer >= t["commercial_transferability"] and max(mechanism, behavior, result) >= t["commercial_anchor"]:
            return True, "commercial_case", score
        if fit >= t["creative_case_fit"] and score >= t["creative_case_score"] and creative >= t["creative_execution"] and max(mechanism, behavior, transfer) >= t["creative_anchor"]:
            return True, "creative_commercial_case", score
        if fit >= t["mechanism_case_fit"] and score >= t["mechanism_case_score"] and mechanism >= t["mechanism"] and transfer >= t["mechanism_transferability"]:
            return True, "mechanism_case", score
        return False, "below_sold_value", max(score, broad_score)

    def _value_gate(self, article: Any) -> dict[str, Any]:
        prompt = f"""Ти UNIVERSAL EDITORIAL VALUE GATE. Матеріал уже пройшов channel fit. Оціни 0..100: novelty, consequence_or_insight, mechanism, reader_payoff, retellability, concrete_stakes, why_now. curiosity_only=true лише якщо цінність тримається на поверхневому wow без payoff.
SOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 3600)}
Поверни ТІЛЬКИ JSON: {{"novelty":0,"consequence_or_insight":0,"mechanism":0,"reader_payoff":0,"retellability":0,"concrete_stakes":0,"why_now":0,"curiosity_only":false,"reason":"коротко"}}"""

        def parse(raw: str):
            obj = _parse_json(raw)
            for key in ("novelty", "consequence_or_insight", "mechanism", "reader_payoff", "retellability", "concrete_stakes", "why_now"):
                obj[key] = max(0, min(100, int(float(obj.get(key, 0) or 0))))
            return obj

        return parse(self.gateway.run(prompt, validator=lambda raw: parse(raw), max_output_tokens=210, timeout_seconds=25, purpose="value_gate").text)

    @staticmethod
    def _value_allowed(data: Mapping[str, Any], fit: int, thresholds: Mapping[str, int] | None = None) -> tuple[bool, str, int]:
        t = dict(_STANDARD_EDITORIAL_THRESHOLDS); t.update(dict(thresholds or {}))
        weights = {"novelty": .14, "consequence_or_insight": .19, "mechanism": .14, "reader_payoff": .19, "retellability": .15, "concrete_stakes": .09, "why_now": .10}
        score = int(round(sum(int(data.get(key, 0) or 0) * weight for key, weight in weights.items())))
        novelty = int(data.get("novelty", 0)); insight = int(data.get("consequence_or_insight", 0)); mechanism = int(data.get("mechanism", 0)); payoff = int(data.get("reader_payoff", 0)); retell = int(data.get("retellability", 0)); stakes = int(data.get("concrete_stakes", 0)); why_now = int(data.get("why_now", 0)); curiosity = bool(data.get("curiosity_only", False))
        standard = not (curiosity and insight < 55 and payoff < 60) and score >= t["standard_score"] and payoff >= t["standard_payoff"] and retell >= t["standard_retellability"] and max(insight, mechanism, stakes) >= t["standard_signal"] and not (why_now < t["standard_why_now"] and novelty < t["standard_novelty_exception"])
        if standard: return True, "standard", score
        if fit >= t["mechanism_lane_fit"] and score >= t["mechanism_lane_score"] and mechanism >= t["mechanism_lane_mechanism"] and payoff >= t["mechanism_lane_payoff"] and retell >= t["mechanism_lane_retellability"]: return True, "policy_fit_mechanism_lane", score
        if fit >= t["insight_lane_fit"] and score >= t["insight_lane_score"] and insight >= t["insight_lane_insight"] and payoff >= t["insight_lane_payoff"] and retell >= t["insight_lane_retellability"]: return True, "policy_fit_insight_lane", score
        if fit >= t["creative_lane_fit"] and score >= t["creative_lane_score"] and novelty >= t["creative_lane_novelty"] and payoff >= t["creative_lane_payoff"] and retell >= t["creative_lane_retellability"]: return True, "policy_fit_creative_lane", score
        return False, "below_editorial_value", score

    def write(self, channel: ChannelConfig, article: Any, selection: EditorialOutcome) -> EditorialOutcome:
        p = channel.policy
        source_name = source_context_name(channel, article)
        source_context = source_body_context_name(channel, article)
        body_hard_max = source_body_hard_limit(
            channel, article, default_body_limit=TELEGRAM_BODY_SAFE_MAX
        )
        effective_min, effective_max, validation_hard_max = _monitoring_limits(channel, article, body_hard_max)
        if channel.mode == ChannelMode.MONITORING:
            event(
                "editorial", "monitoring dynamic length", channel_id=channel.id,
                article_id=int(_v(article, "id", 0) or 0), source_chars=len(_source_text(article)),
                configured_min=int(p.target_min_chars), effective_min=effective_min, effective_max=effective_max,
            )
        facts = extract_actionable_facts(article)
        protected = "\n".join("- " + item for item in facts) if facts else "Немає."
        style_memory = self.learning.style_memory_block(channel.id, article)
        source_context_instruction = (
            f'SOURCE CONTEXT: {source_context}\n'
            f'ОБОВ\'ЯЗКОВО: у першому абзаці природно вживи точну назву «{source_context}» хоча б один раз. '
            'Не замінюй її безликим описом джерела.\n'
            if source_context else ""
        )
        monitoring_rule = (
            "\nКОРОТКЕ ДЖЕРЕЛО: не добирай обсяг штучно. Якщо SOURCE містить лише 1–2 факти, напиши короткий пост і завершуй. "
            "Не додавай фрази про те, що деталі/терміни не надані, якщо SOURCE цього прямо не каже. "
            "Не додавай від себе порад, моралей, застережень, оцінок важливості, висновків або загальних фраз. "
            "Не пиши «це свідчить/показує/підкреслює», «важливий крок», «продовжує працювати/підтримувати» та подібні інтерпретації, якщо SOURCE прямо цього не стверджує. "
            if channel.mode == ChannelMode.MONITORING else ""
        )
        named_source_style = source_body_instruction(channel, article)
        prompt = f"""Ти єдиний автор Telegram-поста. Напиши природною українською. Використовуй ТІЛЬКИ SOURCE та SOURCE NAME. Не вигадуй фактів, чисел, назв або причинності. Не додавай source footer: його додасть система.
СТРУКТУРА: якщо фінальний текст має 350+ символів, обов'язково поділи його щонайменше на 2 короткі смислові абзаци; типовий пост — 2–4 абзаци. Не пиши суцільну стіну тексту. Не використовуй штучні повтори літер або пунктуації.{monitoring_rule}{named_source_style}
CHANNEL PURPOSE: {p.purpose}
WRITING RULES: {p.writing_rules}
STYLE RULES: {p.style_rules}
EXTRA: {p.writer_extra_prompt}
{style_memory}
ANGLE: {selection.angle}
{source_context_instruction}SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}
Цільова довжина: {effective_min}-{effective_max} символів. ЖОРСТКО: готовий текст не може перевищувати {validation_hard_max} символів, бо система додає окремий footer джерела.
PROTECTED ACTIONABLE FACTS: якщо релевантні правилам каналу, збережи точні контакти/адреси/дати/час/URL дослівно.
{protected}
SOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}
SOURCE:
{_source_pack(article, 6200)}
Поверни ТІЛЬКИ готовий текст поста без службових пояснень."""

        def prepared_text(raw: str) -> str:
            value = str(raw or "").strip()
            if channel.mode == ChannelMode.MONITORING:
                value = restore_practical_literals(article, value, hard_max_chars=validation_hard_max)
                value = strip_non_actionable_article_urls(article, value)
            return value

        slop_profile = _anti_slop_profile(channel)

        def validator(raw: str) -> None:
            candidate = prepared_text(raw)
            if channel.mode == ChannelMode.MONITORING:
                grounding = _monitoring_grounding_blockers(article, candidate)
                if grounding:
                    raise ValueError("Monitoring grounding QA: " + "; ".join(grounding))
            source_policy = _source_body_policy_issues(channel, article, candidate)
            if source_policy:
                raise ValueError("Source-body QA: " + "; ".join(source_policy))
            validate_writer_output(
                article, candidate, min_chars=effective_min, max_chars=effective_max,
                hard_max_chars=validation_hard_max, required_context=source_context, slop_profile=slop_profile,
            )

        result = self.gateway.run(prompt, validator=validator, max_output_tokens=1100, timeout_seconds=30, purpose="writer")
        draft = validate_writer_output(
            article, prepared_text(result.text), min_chars=effective_min, max_chars=effective_max,
            hard_max_chars=validation_hard_max, required_context=source_context, slop_profile=slop_profile,
        )
        quality = assess_rewrite(draft, hard_limit=validation_hard_max)
        needs_trusted_editor = (
            quality.needs_second_candidate
            or bool(language_quality_issues(draft))
            or bool(human_style_issues(draft))
            or needs_grammar_polish(draft)
        )
        if needs_trusted_editor:
            event(
                "editorial", "trusted final editor required", channel_id=channel.id,
                article_id=int(_v(article, "id", 0) or 0), generator=result.provider,
                monitoring=channel.mode == ChannelMode.MONITORING, quality=quality.score,
            )
            final = self._final_edit(
                channel, article, draft, min_chars=effective_min, max_chars=effective_max,
                hard_max_chars=validation_hard_max, trusted_only=True, fail_closed=True,
            )
        else:
            final = draft

        # Optional local LanguageTool pass. It never creates a dependency, but if it
        # is already available we accept only conservative edits and re-run every gate.
        lt = apply_local_languagetool_detailed(final, timeout=1.2, max_changes=18, require_ready=False)
        if lt.changes and preserves_content(final, lt.text):
            candidate = prepared_text(lt.text)
            validator(candidate)
            final = validate_writer_output(
                article, candidate, min_chars=effective_min, max_chars=effective_max,
                hard_max_chars=validation_hard_max, required_context=source_context, slop_profile=slop_profile,
            )
        return EditorialOutcome(Decision.PUBLISH, reason=selection.reason, angle=selection.angle, fit_score=selection.fit_score, editorial_value_score=selection.editorial_value_score, draft_text=draft, final_text=final, provider=result.provider, model=result.model)

    def _final_edit(
        self, channel: ChannelConfig, article: Any, draft: str, *, min_chars: int, max_chars: int,
        hard_max_chars: int | None = None, trusted_only: bool = False, fail_closed: bool = False,
    ) -> str:
        p = channel.policy
        source_name = source_context_name(channel, article)
        source_context = source_body_context_name(channel, article)
        body_hard_max = source_body_hard_limit(
            channel, article, default_body_limit=TELEGRAM_BODY_SAFE_MAX
        )
        final_hard_max = min(body_hard_max, int(hard_max_chars or body_hard_max))
        style_memory = self.learning.style_memory_block(channel.id, article)
        source_context_instruction = (
            f'SOURCE CONTEXT: {source_context}\n'
            f'Не прибирай і не змінюй точну назву «{source_context}»: вона потрібна, щоб пост був зрозумілий поза контекстом джерела.\n'
            if source_context else ""
        )
        source_attribution_instruction = source_body_instruction(channel, article)
        prompt = f"""Ти фінальний редактор українського Telegram-тексту перед автоматичною публікацією. Виправ мову, граматику, узгодження, ясність, повтори і структуру. Не додавай жодних нових фактів/чисел/назв. Не роздувай коротке джерело. Не додавай порад, моралей чи фраз про відсутні деталі, якщо їх немає у SOURCE. {source_attribution_instruction}Якщо текст уже добрий, поверни його без змін.
CHANNEL RULES: {p.writing_rules}\nSTYLE: {p.style_rules}\n{style_memory}\n{source_context_instruction}SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE:\n{_source_pack(article, 5200)}\nDRAFT:\n{draft}\nПоверни тільки фінальний текст."""

        def prepared_text(raw: str) -> str:
            value = str(raw or "").strip()
            if channel.mode == ChannelMode.MONITORING:
                value = restore_practical_literals(article, value, hard_max_chars=final_hard_max)
                value = strip_non_actionable_article_urls(article, value)
            return value

        slop_profile = _anti_slop_profile(channel)

        def validator(raw: str) -> None:
            candidate = prepared_text(raw)
            if channel.mode == ChannelMode.MONITORING:
                grounding = _monitoring_grounding_blockers(article, candidate)
                if grounding:
                    raise ValueError("Monitoring grounding QA: " + "; ".join(grounding))
            source_policy = _source_body_policy_issues(channel, article, candidate)
            if source_policy:
                raise ValueError("Source-body QA: " + "; ".join(source_policy))
            validate_writer_output(
                article, candidate, min_chars=min_chars, max_chars=max_chars,
                hard_max_chars=final_hard_max, required_context=source_context, slop_profile=slop_profile,
            )

        try:
            result = self.gateway.run(
                prompt, validator=validator, max_output_tokens=1100, timeout_seconds=28,
                allowed_providers=TRUSTED_EDITOR_PROVIDERS if trusted_only else None, purpose="final_editor",
            )
            candidate = prepared_text(result.text)
            validator(candidate)
            return validate_writer_output(
                article, candidate, min_chars=min_chars, max_chars=max_chars,
                hard_max_chars=final_hard_max, required_context=source_context, slop_profile=slop_profile,
            )
        except GatewayExhausted:
            if fail_closed:
                raise
            return draft

    def process_article(self, article_id: int, heartbeat: Callable[[], None] | None = None) -> EditorialOutcome:
        article = self.store.get_article(article_id)
        if article is None:
            raise KeyError(article_id)
        channel = self.store.get_channel(int(article["channel_id"]))
        if channel is None:
            raise RuntimeError("CHANNEL_MISSING")
        canonical = str(article["canonical_source_url"] or "").strip()
        if not canonical.startswith(("http://", "https://")):
            self.store.update_article(article_id, blocked_by=str(BlockedBy.SOURCE), last_error_code="SOURCE_MISSING", last_error_detail="Немає canonical source URL")
            raise RuntimeError("SOURCE_MISSING")
        if heartbeat is not None:
            try: heartbeat()
            except Exception: pass
        selection = self.select(channel, article)
        if heartbeat is not None:
            try: heartbeat()
            except Exception: pass
        self.store.update_article(article_id, stage=str(Stage.SELECTED), editorial_value_score=selection.editorial_value_score, ai_provider=selection.provider, ai_model=selection.model, status_detail=selection.reason)
        event("editorial", "selector decision", channel_id=channel.id, article_id=article_id, decision=str(selection.decision), reason=selection.reason, fit=selection.fit_score, value=selection.editorial_value_score)
        if selection.decision == Decision.REJECT:
            self.store.update_article(article_id, decision=str(Decision.REJECT), blocked_by=str(BlockedBy.NONE), reject_reason=selection.reason)
            return selection
        saturation = topic_saturation_reason(self.store, channel, article)
        if saturation:
            blocked = EditorialOutcome(Decision.REJECT, reason=saturation, fit_score=selection.fit_score, editorial_value_score=selection.editorial_value_score, provider=selection.provider, model=selection.model)
            self.store.update_article(article_id, decision=str(Decision.REJECT), blocked_by=str(BlockedBy.NONE), reject_reason=saturation, status_detail=saturation)
            event("editorial", "topic saturation blocked", level=30, channel_id=channel.id, article_id=article_id, detail=saturation)
            return blocked
        if heartbeat is not None:
            try: heartbeat()
            except Exception: pass
        written = self.write(channel, article, selection)
        if heartbeat is not None:
            try: heartbeat()
            except Exception: pass
        self.store.update_article(article_id, stage=str(Stage.QA_PASSED), draft_text=written.draft_text, final_text=written.final_text, ai_provider=written.provider, ai_model=written.model, status_detail=written.reason)
        self.store.mark_ready(article_id)
        event("editorial", "article ready", channel_id=channel.id, article_id=article_id, provider=written.provider, model=written.model, chars=len(written.final_text))
        return written
