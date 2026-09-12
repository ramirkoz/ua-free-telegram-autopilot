from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..evidence_pack import build_evidence_pack
from ..fact_guard import validate_fact_guard
from ..language import looks_ukrainian
from ..ukrainian_quality import apply_safe_ukrainian_fixes, human_style_issues, language_quality_issues
from .ai_gateway import AIGateway, GatewayExhausted
from .domain import BlockedBy, ChannelConfig, ChannelMode, Decision, Stage
from .loghub import event
from .learning import LearningEngine
from .storage import V2Store


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
    out: list[str] = []

    def add(label: str, value: str) -> None:
        clean = " ".join(str(value or "").split()).strip(" ,;")
        item = f"{label}: {clean}" if clean else ""
        if item and item not in out:
            out.append(item[:420])

    for url in re.findall(r"https?://[^\s<>()\]\[{}\"']+", source, flags=re.I):
        add("URL", url.rstrip(".,;:!?"))
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


def validate_writer_output(article: Any, text: str, *, min_chars: int, max_chars: int, hard_max_chars: int | None = None) -> str:
    value = apply_safe_ukrainian_fixes(str(text or "")).strip()
    if len(value) < max(80, int(min_chars) * 2 // 3):
        raise ValueError("Непридатна довжина Telegram-тексту: надто коротко")
    if hard_max_chars is not None and len(value) > int(hard_max_chars):
        raise ValueError(f"Непридатна довжина Telegram-тексту: понад жорсткий ліміт {int(hard_max_chars)}")
    if len(value) > max(int(max_chars) + 250, int(max_chars) * 3 // 2):
        raise ValueError("Непридатна довжина Telegram-тексту: надто довго")
    if not looks_ukrainian(value):
        raise ValueError("AI не повернув природний український текст")
    validate_fact_guard(article, value)
    source = str(_v(article, "title", "")) + "\n" + str(_v(article, "raw_text", ""))
    invented = sorted(_number_tokens(value) - _number_tokens(source))
    if invented:
        raise ValueError("AI додав число, якого немає у джерелі: " + ", ".join(invented[:10]))
    if value.count("(") != value.count(")") or value.count("«") != value.count("»"):
        raise ValueError("Незакриті дужки/лапки")
    if re.search(r"(?:\b(?:і|й|але|або|бо|що|через|після|до|для|з|із|на|у|в|та)\s*)$", value.casefold().rstrip()):
        raise ValueError("Останнє речення обірване")
    issues = list(language_quality_issues(value)) + list(human_style_issues(value))
    if len(issues) >= 3:
        raise ValueError("Мовний QA: " + "; ".join(issues[:3]))
    return value


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
SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 5200)}
Поверни ТІЛЬКИ JSON: {{"included":true,"excluded":false,"reason":"коротко"}}"""

        def parse(raw: str):
            obj = _parse_json(raw)
            return bool(obj.get("included", True)), bool(obj.get("excluded", False)), _clean(obj.get("reason"), 500)

        result = self.gateway.run(prompt, validator=lambda raw: parse(raw), max_output_tokens=190, timeout_seconds=22)
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
SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 5600)}
Поверни ТІЛЬКИ JSON: {{"decision":"publish" або "reject","fit_score":0,"reason":"коротко","angle":"кут","topic_tags":["..."]}}"""

        def parse_fit(raw: str):
            obj = _parse_json(raw)
            decision = str(obj.get("decision") or "").casefold()
            if decision not in {"publish", "reject"}:
                raise ValueError("invalid decision")
            return obj

        fit_result = self.gateway.run(prompt, validator=lambda raw: parse_fit(raw), max_output_tokens=340, timeout_seconds=25)
        fit = parse_fit(fit_result.text)
        raw_score = max(0, min(100, int(fit.get("fit_score", 0) or 0)))
        score = max(0, min(100, raw_score + int(learning.fit_adjustment)))
        if learning.fit_adjustment:
            event(
                "learning", "topic soft adjustment", channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0),
                admin_score=round(learning.admin_score, 3), audience_score=round(learning.audience_score, 3),
                adjustment=int(learning.fit_adjustment), raw_fit=raw_score, adjusted_fit=score,
            )
        if fit["decision"] == "reject":
            return EditorialOutcome(Decision.REJECT, reason=_clean(fit.get("reason"), 600), fit_score=score, provider=fit_result.provider, model=fit_result.model)
        value = self._value_gate(article)
        allowed, code, value_score = self._value_allowed(value, score)
        if not allowed:
            return EditorialOutcome(Decision.REJECT, reason=f"EDITORIAL_VALUE_REJECT score={value_score}; code={code}; " + _clean(value.get("reason"), 420), fit_score=score, editorial_value_score=value_score, provider=fit_result.provider, model=fit_result.model)
        return EditorialOutcome(Decision.PUBLISH, reason=f"EDITORIAL_VALUE_PASS score={value_score}; lane={code}; fit={score}; learning={learning.fit_adjustment:+d}", angle=_clean(fit.get("angle"), 500), fit_score=score, editorial_value_score=value_score, provider=fit_result.provider, model=fit_result.model)

    def _value_gate(self, article: Any) -> dict[str, Any]:
        prompt = f"""Ти UNIVERSAL EDITORIAL VALUE GATE. Матеріал уже пройшов channel fit. Оціни 0..100: novelty, consequence_or_insight, mechanism, reader_payoff, retellability, concrete_stakes, why_now. curiosity_only=true лише якщо цінність тримається на поверхневому wow без payoff.
SOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 5800)}
Поверни ТІЛЬКИ JSON: {{"novelty":0,"consequence_or_insight":0,"mechanism":0,"reader_payoff":0,"retellability":0,"concrete_stakes":0,"why_now":0,"curiosity_only":false,"reason":"коротко"}}"""

        def parse(raw: str):
            obj = _parse_json(raw)
            for key in ("novelty", "consequence_or_insight", "mechanism", "reader_payoff", "retellability", "concrete_stakes", "why_now"):
                obj[key] = max(0, min(100, int(float(obj.get(key, 0) or 0))))
            return obj

        return parse(self.gateway.run(prompt, validator=lambda raw: parse(raw), max_output_tokens=360, timeout_seconds=25).text)

    @staticmethod
    def _value_allowed(data: Mapping[str, Any], fit: int) -> tuple[bool, str, int]:
        weights = {"novelty": .14, "consequence_or_insight": .19, "mechanism": .14, "reader_payoff": .19, "retellability": .15, "concrete_stakes": .09, "why_now": .10}
        score = int(round(sum(int(data.get(key, 0) or 0) * weight for key, weight in weights.items())))
        novelty = int(data.get("novelty", 0)); insight = int(data.get("consequence_or_insight", 0)); mechanism = int(data.get("mechanism", 0)); payoff = int(data.get("reader_payoff", 0)); retell = int(data.get("retellability", 0)); stakes = int(data.get("concrete_stakes", 0)); why_now = int(data.get("why_now", 0)); curiosity = bool(data.get("curiosity_only", False))
        standard = not (curiosity and insight < 55 and payoff < 60) and score >= 60 and payoff >= 50 and retell >= 48 and max(insight, mechanism, stakes) >= 52 and not (why_now < 32 and novelty < 78)
        if standard: return True, "standard", score
        if fit >= 60 and score >= 48 and mechanism >= 60 and payoff >= 55 and retell >= 50: return True, "policy_fit_mechanism_lane", score
        if fit >= 60 and score >= 48 and insight >= 62 and payoff >= 55 and retell >= 48: return True, "policy_fit_insight_lane", score
        if fit >= 60 and score >= 50 and novelty >= 65 and payoff >= 55 and retell >= 58: return True, "policy_fit_creative_lane", score
        return False, "below_editorial_value", score

    def write(self, channel: ChannelConfig, article: Any, selection: EditorialOutcome) -> EditorialOutcome:
        p = channel.policy
        effective_max = max(120, min(int(p.target_max_chars), TELEGRAM_BODY_SAFE_MAX))
        effective_min = max(80, min(int(p.target_min_chars), effective_max))
        facts = extract_actionable_facts(article)
        protected = "\n".join("- " + item for item in facts) if facts else "Немає."
        style_memory = self.learning.style_memory_block(channel.id, article)
        prompt = f"""Ти єдиний автор Telegram-поста. Напиши природною українською. Використовуй ТІЛЬКИ SOURCE. Не вигадуй фактів, чисел, назв або причинності. Не додавай source footer: його додасть система.
CHANNEL PURPOSE: {p.purpose}
WRITING RULES: {p.writing_rules}
STYLE RULES: {p.style_rules}
EXTRA: {p.writer_extra_prompt}
{style_memory}
ANGLE: {selection.angle}
Цільова довжина: {effective_min}-{effective_max} символів. ЖОРСТКО: готовий текст не може перевищувати {TELEGRAM_BODY_SAFE_MAX} символів, бо система додає окремий footer джерела.
PROTECTED ACTIONABLE FACTS: якщо релевантні правилам каналу, збережи точні контакти/адреси/дати/час/URL дослівно.
{protected}
SOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}
SOURCE:
{_source_pack(article, 6200)}
Поверни ТІЛЬКИ готовий текст поста без службових пояснень."""

        def validator(raw: str) -> None:
            validate_writer_output(article, raw, min_chars=effective_min, max_chars=effective_max, hard_max_chars=TELEGRAM_BODY_SAFE_MAX)

        result = self.gateway.run(prompt, validator=validator, max_output_tokens=1100, timeout_seconds=30)
        draft = validate_writer_output(article, result.text, min_chars=effective_min, max_chars=effective_max, hard_max_chars=TELEGRAM_BODY_SAFE_MAX)
        final = self._final_edit(channel, article, draft, min_chars=effective_min, max_chars=effective_max)
        return EditorialOutcome(Decision.PUBLISH, reason=selection.reason, angle=selection.angle, fit_score=selection.fit_score, editorial_value_score=selection.editorial_value_score, draft_text=draft, final_text=final, provider=result.provider, model=result.model)

    def _final_edit(self, channel: ChannelConfig, article: Any, draft: str, *, min_chars: int, max_chars: int) -> str:
        p = channel.policy
        style_memory = self.learning.style_memory_block(channel.id, article)
        prompt = f"""Ти фінальний редактор. Виправ ТІЛЬКИ мову, ясність, повтори і структуру. Не додавай жодних нових фактів/чисел/назв. Якщо текст уже добрий, поверни його без змін.
CHANNEL RULES: {p.writing_rules}\nSTYLE: {p.style_rules}\n{style_memory}\nSOURCE:\n{_source_pack(article, 5200)}\nDRAFT:\n{draft}\nПоверни тільки фінальний текст."""

        def validator(raw: str) -> None:
            validate_writer_output(article, raw, min_chars=min_chars, max_chars=max_chars, hard_max_chars=TELEGRAM_BODY_SAFE_MAX)

        try:
            result = self.gateway.run(prompt, validator=validator, max_output_tokens=1100, timeout_seconds=28)
            return validate_writer_output(article, result.text, min_chars=min_chars, max_chars=max_chars, hard_max_chars=TELEGRAM_BODY_SAFE_MAX)
        except GatewayExhausted:
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
