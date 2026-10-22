from __future__ import annotations

import ast
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
    source_body_hard_limit, source_context_name, strip_forbidden_source_body_attribution,
)
from .domain import MONITORING_EVENT_TYPES, BlockedBy, ChannelConfig, ChannelMode, Decision, EditorialRuntimeProfile, Stage
from .loghub import event
from .learning import LearningEngine
from .storage import V2Store
from .topic_saturation import topic_saturation_reason
from .evidence_first import assess_monitoring_source, assess_monitoring_media
from .claim_verifier import verify_qualified_claims
from .polarity_verifier import verify_source_polarity
from .claim_trace import trace_output_claims

# 2.2.4: values that mean the model copied the schema instead of deciding.
_PLACEHOLDER_REASONS = frozenset({"коротко", "none", "reason", "short", "одне речення", "..."})

# 2.2.3: structured selector rejection codes (see the CHANNEL-FIT SELECTOR prompt).
SELECTOR_REJECT_CODES = (
    "off_topic", "weak_audience_hook", "routine_pr", "weak_mechanism", "weak_visual",
    "duplicate", "insufficient_facts", "stale", "other",
)


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _clean(value: Any, limit: int = 12000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _parse_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip().lstrip("\ufeff")
    text = re.sub(r"^```(?:json|javascript|js)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    candidate = ""
    if start >= 0:
        depth = 0
        quoted = False
        escaped = False
        for idx, ch in enumerate(text[start:], start=start):
            if quoted:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    quoted = False
                continue
            if ch == '"':
                quoted = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:idx + 1]
                    break
    if not candidate:
        raise ValueError("AI не повернув JSON")
    variants = [candidate]
    repaired = candidate.replace("“", '"').replace("”", '"').replace("’", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    if repaired != candidate:
        variants.append(repaired)
    last_error: Exception | None = None
    for value in variants:
        try:
            obj = json.loads(value)
        except Exception as exc:
            last_error = exc
            try:
                obj = ast.literal_eval(value)
            except Exception as fallback_exc:
                last_error = fallback_exc
                continue
        if isinstance(obj, dict):
            return obj
        last_error = ValueError("AI JSON має бути object")
    raise ValueError(f"AI повернув пошкоджений JSON: {last_error}")

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


_LIVE_SECURITY_ALERT_RE = re.compile(
    r"(?iu)(?:"
    r"\b(?:повітрян\w*\s+тривог\w*|відбій\s+тривог\w*|загроз\w*\s+(?:бпла|ракет)|"
    r"(?:чути|чутно|чули|пролунав|пролунавши|пролунали|був|було)\s+(?:\w+\s+){0,3}вибух\w*|"
    r"(?:бачать|видно|помітили|спостерігають)\s+(?:\w+\s+){0,3}дим\w*|"
    r"(?:летить|рухається|курс\w*|проліт\w*)\s+(?:\w+\s+){0,3}(?:fpv|фпв|бпла|дрон\w*|ракет\w*|шахед\w*))\b"
    r"|(?:\bвибух\s+(?:був|є)\b)"
    r")"
)
_RECAP_FACT_RE = re.compile(
    r"(?iu)\b(?:за\s+(?:минул\w+\s+добу|останні\s+24\s+годин)|"
    r"вранці|зранку|сьогодні\s+вранці|учора|вчора|"
    r"минулої\s+ночі|внаслідок\s+атаки|унаслідок\s+удару|"
    r"було\s+атаковано|зазнал\w+\s+атаки|пошкоджен\w+|"
    r"зруйнован\w+|постраждал\w+|загинул\w+|поранен\w+)\b"
)
_RESULT_FACT_RE = re.compile(
    r"(?iu)\b(?:було\s+атаковано|зазнал\w+\s+атаки|"
    r"пошкоджен\w+|зруйнован\w+|постраждал\w+|"
    r"загинул\w+|поранен\w+|"
    r"(?:рятувальник\w+|ДСНС)\s+(?:ліквідувал\w+|завершил\w+)|"
    r"ліквідован\w+\s+пожеж\w+)\b"
)


def _postfactum_security_policy(channel: ChannelConfig, article: Any) -> str:
    """Monitoring security notices must describe confirmed past events.

    Reject raw sound/smoke/flight alerts *before* invoking AI. Do not interpret
    a timestamp or the word 'yesterday' as evidence of a completed event.
    """
    if channel.mode != ChannelMode.MONITORING:
        return ""
    source = " ".join((str(_v(article, "title", "")), _source_text(article))).casefold()
    security = re.search(r"(?iu)(?:вибух\w*|дим\w*|тривог\w*|відбій|дрон\w*|фпв|fpv|бпла|ланцет\w*|ракет\w*|шахед\w*|обстріл\w*|атак\w*|удар\w*)", source)
    if not security:
        return ""
    result = _RESULT_FACT_RE.search(source)
    # Confirmed retrospective attack alone suffices: damage is NOT mandatory.
    completed = re.search(
        r"(?iu)(?:було\s+атаковано|зазнал\w*\s+атаки|"
        r"унаслідок\s+(?:атаки|удару)|внаслідок\s+(?:атаки|удару)|"
        r"(?:зранку|вранці|учора|вчора|за\s+(?:минул\w+\s+добу|добу)).{0,110}"
        r"(?:атакувал\w*|атак\w*|обстрілял\w*|завдал\w*\s+удар\w*))",
        source,
    )
    if completed or result:
        return ""
    return "POSTFACTUM_ONLY: оперативний сигнал без підтвердженої завершеної події"


# 2.1.0: deterministic stop conditions are checked before AI selection AND
# immediately before publication. The body is never allowed to supply missing
# facts absent from the source itself.
_EDITORIAL_META_LEAK_RE = re.compile(
    r"(?iu)(?:\b(?:готовий\s+текст\s+(?:поста|публікації)|джерело\s+додасть\s+footer|"
    r"не\s+публікувати\b|не\s+підходить\s+для\s+публікації|"
    r"немає\s+нового\s+повідомлення\s+для\s+публікації|"
    r"за\s+наданим\s+контекстом|ось\s+(?:готовий|переписаний)\s+(?:текст|пост))"
    r"|\b(?:as\s+an\s+ai|i\s+cannot\s+comply)\b)"
)
_BARE_ALERT_RE = re.compile(
    r"(?iu)(?:^|\s)(?:гучно[!. ]*|знову[!. ]*|ще[!. ]*|каби[!. ]*|"
    r"молні(?:я|ї)[!. ]*|пуски\s+каб\w*[!. ]*|"
    r"вибух\w*[!. ]*|дим[!. ]*|тривог\w*[!. ]*)$"
)
# 2.2.9 P0: source-owned bare tactical threat alerts are NOT local_news.
# This deterministic rule is independent of AI event typing and channel marker.
_BARE_DRONE_DESTINATION_ALERT_RE = re.compile(
    r"(?iu)\b(?:ланцет\w*|бпла|дрон\w*|шахед\w*|фпв|fpv|каб(?:и|ів)?)\b"
    r"[^.!?\n]{0,28}\b(?:на|по|у|в|над|біля|поблизу|до|"
    r"в\s+бік|у\s+напрямку|напрямку)\b\s+\S+"
)


_LIVE_THREAT_RE = re.compile(
    r"(?iu)\b(?:пуски\s+(?:каб\w*|ракет\w*)|каб\w*\s+(?:в\s+бік|у\s+напрямку)|"
    r"бпла\s+(?:летить|рухається)|(?:летить|рухається)\s+(?:бпла|ракета|шахед)|"
    r"(?:(?:знову|ще)\s+)?гучно[!. ]*|"
    r"(?:чути|чутно|пролунав|пролунали)\s+вибух\w*|"
    r"повітрян\w*\s+тривог\w*|відбій\s+тривог\w*)\b"
)


# Operator LIVE #74908: "повідомляють підписники" is the same unverified
# attribution as "підписники повідомляють", regardless of AI rewriting.
_MONITORING_READER_REVERSE = re.compile(
    r"(?iu)\b(?:повідомляють|повідомили|повідомляє|пишуть|"
    r"розповідають|кажуть|стверджують|заявляють)\b"
    r"[^.!?\n]{0,95}\b(?:(?:наші|місцеві|деякі|окремі)\s+)?"
    r"(?:підписник\w*|читач\w*|очевидц\w*|свідк\w*|сусід\w*)\b|"
    r"\b(?:баба\s+[а-яіїєґ]+|кум|сусід\w*)\b"
    r"[^.!?\n]{0,70}\b(?:сказав|сказала|казала|каже|"
    r"повідомив|повідомила|розповів|розповіла)\b|"
    r"\b(?:у\s+чат(?:і|ах)\s+пишуть|"
    r"повідомленн\w*\s+від\s+(?:наших\s+)?(?:читач\w*|підписник\w*))\b"
)


_MONITORING_READER_RUMOR = re.compile(
    r"(?iu)(?:\b(?:підписник[иаів]*|читач[іів]*|очевидц[іів]*|свідк[иів]*)\b"
    r".{0,95}\b(?:повідом|пиш|розпов|каж|ствердж)|"
    r"\b(?:зі\s+слів|за\s+словами)\s+(?:читач|підписник|очевидц|свідк)|"
    r"\b(?:нам\s+пишуть|пишуть\s+нам|читачі\s+пишуть|пишуть\s+читачі))"
)
_MONITORING_PRIVATE_NOTICES = re.compile(
    r"(?iu)(?:\b(?:загубил[аи]|загублен[аийі]|знайшли|чиї|чий)\b"
    r".{0,85}\b(?:ключ[іи]|вейп|електронн\w*\s+сигарет|гаманець|телефон|собак|тварин)|"
    r"\b(?:загубили\s+вейп|чий\s+малий\s+бігає|чия\s+собак))"
)
_MONITORING_UNOFFICIAL_POWER = re.compile(
    r"(?iu)(?:зникло\s+світло|світло\s+зникло|немає\s+світла|світла\s+немає|вимкнул\w*\s+світло|"
    r"електрик\w*\s+вже\s+відновил\w*)"
)
_MONITORING_OFFICIAL_ORIGIN = re.compile(
    r"(?iu)(?:військов\w*\s+адміністрац|\b(?:міськ|селищн|сільськ|обласн)\w*\s+рад\w*|"
    r"\b(?:ОВА|МВА|ДСНС|поліці\w*|міськрад\w*|обленерго|"
    r"міністерств\w*|департамент\w*|комунальн\w*\s+установ\w*)\b)"
)


def _monitoring_official_context_reject(article: Any, channel: ChannelConfig | None = None) -> str:
    raw = str(_v(article, "raw_text", "") or "").strip()
    source_name = str(_v(article, "source_name", "") or "").strip()
    title = str(_v(article, "title", "") or "").strip()
    # Title is not proof. The first source caption takes precedence.
    # The disallowed material is unverified citizen-submitted reporting,
    # NOT reporting created by an independent local newsroom.
    source_owned = (raw + "\n" + title).strip()
    citizen_claim = bool(_MONITORING_READER_RUMOR.search(source_owned) or _MONITORING_READER_REVERSE.search(source_owned) or re.search(
        r"(?iu)(?:\b(?:місцеві|жителі|мешканці|люди)\s+"
        r"(?:пишуть|повідомляють|кажуть|стверджують|розповідають)\b|"
        r"\b(?:за\s+словами|зі\s+слів)\s+"
        r"(?:місцевих|мешканців|жителів|очевидців)\b)",
        source_owned,
    ))
    confirmed_independently = bool(re.search(
        r"(?iu)(?:(?:офіційно\s+)?підтвердил\w*|"
        r"(?:поліція|ДСНС|ОВА|МВА|міська\s+рада|обласна\s+адміністрація)"
        r"[^.!?\n]{0,95}?(?:повідомил\w*|підтвердил\w*))",
        source_owned,
    ))
    if citizen_claim and not confirmed_independently:
        return "MONITORING_READER_RUMOR_NOT_OFFICIAL"
    if _MONITORING_PRIVATE_NOTICES.search(raw):
        return "MONITORING_PRIVATE_ANNOUNCEMENT"
    if _MONITORING_UNOFFICIAL_POWER.search(source_owned) and not _MONITORING_OFFICIAL_ORIGIN.search(source_owned + " " + source_name):
        return "MONITORING_UNVERIFIED_SERVICE_RUMOR"
    # Headlines without independently verifiable factual content do not
    # acquire meaning merely because a photo/video is attached.
    if len(raw) < 95 and re.search(r"(?iu)\b(?:чий|чиї|малий|хтось|незнайом\w*)\b", raw):
        return "MONITORING_AMBIGUOUS_CAPTION"
    # Two unrelated lost-and-found objects in one stitched source are not
    # a news event. The collector must not silently join their contacts.
    if re.search(r"(?iu)\bключ[іи]\b", raw) and re.search(r"(?iu)\bвейп\b", raw):
        return "MONITORING_MULTIPLE_INDEPENDENT_NOTICES"
    # Explicit operator rule: only original institutional/community accounts,
    # not aggregators reproducing eyewitness, subscriber, or reader messages.
    # Empty names in migrated records are handled by the other source gates.
    source_url = str(_v(article, "source_url", "") or "")
    # This source-origin rule belongs to the channel configuration, not to the core.
    # Legacy/injected policies may not expose the new domain method.
    # Unknown modes retain the strict institutional behavior.
    source_policy = str(getattr(getattr(channel, "policy", None), "monitoring_source_policy", "institutional") or "institutional").strip().casefold()
    if source_policy not in {"institutional", "connected_original"}:
        source_policy = "institutional"
    if source_policy == "connected_original" and bool(_telegram_meta(article).get("forwarded")):
        return "MONITORING_NOT_ORIGINAL_FORWARD"
    require_institutional_name = source_policy == "institutional"
    if require_institutional_name and source_url.startswith(("https://t.me/", "http://t.me/", "https://telegram.me/")) and source_name and not re.fullmatch(r"S\d+", source_name) and not re.search(
        r"(?iu)(?:\b(?:ОВА|МВА|ДСНС|МВС|поліція|поліції|міськрада|обленерго)\b|"
        r"громад|військов.{0,15}адміністрац|\b(?:міськ|селищн|сільськ|обласн)\w*\s+рад|"
        r"департамент|міністерств|управління\s+освіт|центр\s+соціальн|"
        r"комунальн\w*\s+(?:заклад|установ|підприємств))", source_name
    ):
        return "MONITORING_SOURCE_NOT_OFFICIAL"
    return ""


def _denied_original_monitoring_source(channel: ChannelConfig, article: Any) -> bool:
    """Block configured source origins, including forwarded posts, not incidental mentions.

    A plain link inside a legitimate locally written news item is not by itself
    proof that the entire item was forwarded. Only canonical publication origin,
    Telegram forward metadata, or an explicit attribution repost are sufficient.
    """
    from urllib.parse import urlparse
    if channel.mode != ChannelMode.MONITORING:
        return False
    raw = str(getattr(channel.policy, "monitoring_denied_origins", "") or "")
    denied = {part.casefold().lstrip("@") for token in re.split(r"[,;\s]+", raw)
              if (part := token.strip().strip("/").split("/")[-1])}
    if not denied:
        return False

    def match(value: object) -> bool:
        candidate = str(value or "").strip().lower()
        if not candidate:
            return False
        if candidate.startswith("@"):
            return candidate[1:] in denied
        if candidate.startswith(("https://", "http://")):
            parsed = urlparse(candidate)
            if parsed.hostname not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
                return False
            parts = [x for x in parsed.path.split("/") if x]
            return bool(parts and parts[0].casefold() in denied)
        return candidate.strip("@/") in denied

    # Article source itself is the excluded original channel.
    for key in ("source_url", "canonical_source_url"):
        if match(_v(article, key, "")):
            return True
    meta = _telegram_meta(article)
    # The collector may expose any of these provenance fields across formats.
    for key in ("forward_from", "forward_from_chat", "forward_source_url",
                "forward_origin", "forwarded_from", "origin_url", "original_source_url"):
        value = meta.get(key)
        if isinstance(value, dict):
            value = value.get("username") or value.get("url") or value.get("source_url")
        if match(value):
            return True
    # Reposted/quoted original with explicit source link in payload.
    forwarded = bool(meta.get("forwarded") or meta.get("is_forwarded"))
    source_text = str(_v(article, "raw_text", "") or "")
    linked_origins = [(m.group(0), m.start()) for m in re.finditer(
        r"https?://(?:t\.me|telegram\.me)/[^\s<>]+", source_text, flags=re.I
    ) if match(m.group(0))]
    if linked_origins:
        if forwarded:
            return True
        # Native Telegram "copy with attribution" can lose the forward flag.
        # An original's link as the opening attribution (with only a few
        # introductory glyphs) is evidence of a repost, not a local story.
        if any(position <= 18 for _, position in linked_origins):
            return True
        # Text explicitly credited to the denied original by source link
        # is also a copy, when it contains no independent local event detail.
        if any(re.search(r"(?u)[,:—–-]\s*$", source_text[max(0, position-12):position])
               for _, position in linked_origins):
            return True
    return False


def hard_editorial_reject(channel: ChannelConfig, article: Any, text: str = "") -> str:
    """Reasons for irreversible, non-AI publication rejection.

    The monitoring policy may be customized with channel rules. Its invariant
    is source sufficiency: no rewriter can manufacture missing event context.
    """
    if _EDITORIAL_META_LEAK_RE.search(str(text or "")):
        return "EDITORIAL_META_LEAK"
    from .publication_safety import is_ai_rejection_text
    if is_ai_rejection_text(text):
        return "AI_REJECTION_LEAK_BLOCKED"
    # The input may already be a polluted multi-story card collection.
    # This veto is source-owned, independent of the AI writer and image ranking.
    if channel.mode == ChannelMode.EDITORIAL:
        from .source_integrity import multi_story_page_cards_reason
        source_problem = multi_story_page_cards_reason(article)
        if source_problem:
            return source_problem
    if channel.mode != ChannelMode.MONITORING:
        return ""
    if _denied_original_monitoring_source(channel, article):
        return "MONITORING_REPOST_DENYLIST_SOURCE"
    # Evaluate the SOURCE, not AI rewrite/title/forwarding channel, at both
    # selection and final Telegram send. This also catches existing READY rows
    # imported from older versions after their media blockers are resolved.
    from .monitoring_civic_quality import civic_relevance_exclusion
    source_exclusion = civic_relevance_exclusion(channel, article)
    if source_exclusion:
        return source_exclusion
    source = _source_text(article).strip()
    official_gate = _monitoring_official_context_reject(article, channel)
    if official_gate:
        return official_gate
    clean = re.sub(r"https?://\S+", "", source).strip(" .!?—–:;\n\t")
    # A weapon + place/destination bulletin is an active positional alert,
    # even when the source omits verbs such as "flies" or "moving".
    if _BARE_DRONE_DESTINATION_ALERT_RE.search(clean) and not _RESULT_FACT_RE.search(clean):
        return "MONITORING_LIVE_ALERT"
    if re.search(r"(?iu)\b(?:рсзв|окупанти)\b.{0,70}\b(?:криють|гатять|обстрілюють)\b", clean) and not _RESULT_FACT_RE.search(clean):
        return "MONITORING_ACTIVE_ATTACK_WARNING"
    evidence = assess_monitoring_source(article, final_text=text)
    if not evidence.allowed:
        return evidence.reasons[0]
    if len(clean) < 90 and re.search(r"(?iu)розважа\w*[,! ]{0,8}як\s+можемо", clean):
        return "MONITORING_BANTER_NOT_NEWS"
    if len(clean) < 18 or _BARE_ALERT_RE.fullmatch(clean):
        return "MONITORING_CONTEXT_MISSING"
    # A photo/video caption cannot stand in for reading the video. When it
    # contains no established event/result, never invent the missing context.
    if (
        re.search(r"(?iu)\b(?:відео|фото|ілюстраці\w*|кадр\w*)\b", clean)
        and len(clean) < 95
        and not _RESULT_FACT_RE.search(clean)
        and not re.search(r"(?iu)\b(?:відкрили|уклали|запустили|призначили|оголосили|надають|отримати|відбудеться)\b", clean)
    ):
        return "MONITORING_MEDIA_CONTEXT_MISSING"
    # 2.1.16: bare threat-level bulletins are live alerts, not news.
    # Preserve separate factual reports about consequences and official actions.
    danger_level = re.search(
        r"(?iu)(?:рівень\s+(?:небезпек\w*|загроз\w*)|"
        r"(?:небезпек\w*|загроз\w*)\s+рівень)"
        r"[^.!?\n]{0,90}?(?:підвищ\w*|зниж\w*|червон\w*|помаранчев\w*|жовт\w*)"
        r"|(?:підвищ\w*|зниж\w*)[^.!?\n]{0,55}рівень\s+(?:небезпек\w*|загроз\w*)",
        clean,
    )
    if danger_level and not _RESULT_FACT_RE.search(clean) and not re.search(
        r"(?iu)\b(?:евакуац\w*|відкри\w*\s+укритт\w*|перекри\w*\s+дорог\w*|"
        r"запровад\w*\s+(?:обмеженн\w*|заход\w*)|пошкоджен\w*|поранен\w*)\b",
        clean,
    ):
        return "MONITORING_LIVE_DANGER_LEVEL"
    # Reject bare current air-strike destination warnings; never turn them
    # into invented confirmed incidents.
    if re.search(r"(?iu)\bКАБ(?:и|ів)?\b\s+(?:на|по|у|в|біля)\s+\S+", clean) and not _RESULT_FACT_RE.search(clean):
        return "MONITORING_LIVE_ALERT"
    if text and "місцеві жителі повідомляють" in text.casefold() and "місцеві жителі повідомляють" not in source.casefold():
        return "MONITORING_UNGROUNDED_WITNESS"
    # Unresolved active threats must not become normal news posts.
    # Official confirmed end-of-event notices remain eligible separately.
    if _LIVE_THREAT_RE.search(clean):
        return "MONITORING_LIVE_ALERT"
    # Even with a casualty/damage figure, an unfolding rescue or new strike
    # is not a settled community notice. Wait for a coherent official recap.
    if (
        re.search(r"(?iu)\b(?:атак\w*|удар\w*|обстріл\w*|вибух\w*|завал\w*|прильот\w*|дрон\w*|каб\w*)\b", clean)
        and re.search(r"(?iu)(?:щойно|тільки\s+що|прямо\s+зараз|"
                      r"рятувальн\w*\s+операці\w*\s+трива\w*|"
                      r"(?:рятувальник\w*|служб\w*)\s+продовж\w*|"
                      r"під\s+завал\w*\s+шука\w*|"
                      r"(?:наслідки|інформац\w*)\s+уточню\w*|"
                      r"на\s+місці\s+працю\w*)", clean)
    ):
        return "MONITORING_UNSETTLED_EVENT"
    if re.search(r"(?iu)\bмолні(?:я|ї)\b", clean):
        return "MONITORING_CONTEXT_MISSING"
    # Catch abbreviated live alerts such as "Вибухи у Запоріжжі", which
    # have no actionable verified outcome even if the final text invents one.
    postfactum = _postfactum_security_policy(channel, article)
    if postfactum:
        return postfactum
    return ""


def deterministic_monitoring_exclusion(channel: ChannelConfig, article: Any) -> str:
    """Apply local exclusions only when the operator explicitly configured them."""
    critical = hard_editorial_reject(channel, article)
    if critical:
        return critical
    postfactum = _postfactum_security_policy(channel, article)
    if postfactum:
        return postfactum
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


_UK_MONTH_AFTER_GLUE = re.compile(
    r"(?iu)(?<=[А-Яа-яІіЇїЄєҐґ])"
    r"(?=\d{1,2}\s+(?:січ\w*|лют\w*|берез\w*|квіт\w*|"
    r"трав\w*|черв\w*|лип\w*|серп\w*|верес\w*|"
    r"жовт\w*|листопад\w*|груд\w*)\b)"
)


_UK_DAY_MONTH = re.compile(
    r"(?iu)\b(0?[1-9]|[12]\d|3[01])\s+"
    r"(січ|лют|берез|квіт|трав|черв|лип|серп|верес|жовт|листопад|груд)\w*\b"
)


def _source_day_month_pairs(text: str) -> set[tuple[int, str]]:
    """Retain date semantics; route №23 cannot support a fabricated 23 October."""
    clean = re.sub(r"https?://\S+", "", str(text or ""))
    clean = _UK_MONTH_AFTER_GLUE.sub(" ", clean)
    return {(int(day), month.casefold()) for day,month in _UK_DAY_MONTH.findall(clean)}


def _number_tokens(text: str) -> set[str]:
    clean = re.sub(r"https?://\S+", "", str(text or ""))
    # Telegram may join the last word of an HTML block to a date:
    # "транспорту22 жовтня". The number is SOURCE-OWNED, not invented.
    # Only split a glued DAY+MONTH, not arbitrary embedded model/product
    # identifiers (GPT5, iPhone16), preserving invented-number protection.
    clean = _UK_MONTH_AFTER_GLUE.sub(" ", clean)
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
        # 2.2.4: a short notice must not grow. The old floor of 80 chars and
        # "+100" ceiling made models pad a 28-char "Загроза КАБ" with invented
        # advice and invented attack details. Retell, do not expand.
        effective_min = max(20, int(source_len * 0.6))
        effective_max = min(configured_max, max(180, source_len + 100), int(source_len * 1.5) + 20)
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


_UNSUPPORTED_CAUSE_RE = re.compile(
    r"(?iu)\b(?:через|унаслідок|внаслідок)\s+(?:атак[иу]|удар[уу]|обстрілу|влучання|падіння|роботи\s+ппо|детонації)"
)
_UNSUPPORTED_ORIGIN_RE = re.compile(
    r"(?iu)\b(?:ворож(?:ого|ої|их)|російськ(?:ого|ої|их))\s+(?:fpv|фпв|дрон[а-яіїєґ]*|безпілотник[а-яіїєґ]*)"
)
_UNSUPPORTED_QUALIFIER_RE = re.compile(r"(?iu)\bза\s+попередньою\s+інформацією\b")
_SOURCE_CAUSAL_LINK_RE = re.compile(
    r"(?iu)\b(?:через|унаслідок|внаслідок|спричинив|спричинила|спричинило|завдав|завдала|вдарив|вдарила|атакував|атакувала|влучив|влучила)\b"
)


def _source_grounding_night_issues(article: Any, text: str) -> tuple[str, ...]:
    """Protect short incident bulletins from invented causality and attribution.

    Avoid trying to settle the entire factual meaning by keyword matching.
    For short alerts, specific *new* causal links must remain in source.
    """
    source = _source_text(article).casefold()
    output = str(text or "")
    if len(source) > 280 or not re.search(r"(?iu)\b(?:вибух|дим|пожеж|удар|атак|дрон|фпв|fpv|обстріл)", source):
        return ()
    issues = []
    if _UNSUPPORTED_CAUSE_RE.search(output) and not _SOURCE_CAUSAL_LINK_RE.search(source):
        issues.append("нічний факт-контроль: джерело не підтверджує причину події")
    if _UNSUPPORTED_ORIGIN_RE.search(output) and not re.search(r"(?iu)\b(?:ворож|російськ|окупант)", source):
        issues.append("нічний факт-контроль: джерело не встановлює походження дрона")
    if _UNSUPPORTED_QUALIFIER_RE.search(output) and not re.search(r"(?iu)\bпопередн", source):
        issues.append("нічний факт-контроль: придумана атрибуція «за попередньою інформацією»")
    return tuple(issues)


def _monitoring_grounding_blockers(article: Any, value: str) -> tuple[str, ...]:
    """Block common padding that states things the source never said."""
    source = _source_text(article).casefold()
    text = str(value or "")
    issues: list[str] = list(_source_grounding_night_issues(article, text))
    # Do not summarize different phases of a rapidly changing situation as
    # simultaneous facts. Ask editor to keep the current settled status only.
    low_output = text.casefold()
    opposite_phases = (
        (r"\b(?:перекрит\w*|закрит\w*)", r"\b(?:відновлен\w*|відкрит\w*|рух\s+відновлено)"),
        (r"\b(?:скасован\w*|скасували)", r"\b(?:триває|діє|запроваджено)"),
    )
    if any(re.search(old, low_output, re.I) and re.search(new, low_output, re.I)
           for old, new in opposite_phases):
        issues.append("змішано завершену та поточну фази події; потрібен лише останній підтверджений стан")
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



def _trim_candidate_to_hard_limit(text: str, hard_max_chars: int, *, min_chars: int=80) -> str:
    """Deterministically shorten over-limit text without asking another model."""
    value=" ".join(str(text or "").replace("\r","\n").split()) if "\n" not in str(text or "") else str(text or "").strip()
    limit=max(80,int(hard_max_chars))
    if len(value)<=limit:
        return value
    window=value[:limit+1].rstrip()
    # Prefer a complete sentence/paragraph near the limit.
    candidates=[window.rfind(mark) for mark in (".","!","?","\n")]
    cut=max(candidates)
    floor=max(80,int(min_chars)*2//3)
    if cut>=floor:
        return window[:cut+1].strip()
    # Never silently publish a word-boundary fragment such as "щоб вик".
    # An incomplete candidate must go through generation retry/QA, not READY.
    raise ValueError("Редакційний QA: немає завершеного речення в ліміті")


def _rc111_prepare_candidate(
    channel: ChannelConfig,
    article: Any,
    raw: str,
    *,
    hard_max_chars: int,
    min_chars: int,
) -> str:
    """Safe local repairs for deterministic QA failures.

    Only formatting/attribution/length is changed. Facts and numbers are never
    synthesized or deleted here.
    """
    value=str(raw or "").strip()
    if channel.mode == ChannelMode.MONITORING:
        value=restore_practical_literals(article,value,hard_max_chars=hard_max_chars)
        value=strip_non_actionable_article_urls(article,value)
    value=strip_forbidden_source_body_attribution(channel,article,value)
    value=_trim_candidate_to_hard_limit(value,hard_max_chars,min_chars=min_chars)
    return value



def _is_editorial_prompt_echo(value: str) -> bool:
    """Reject leaked instructions without rejecting ordinary Ukrainian prose."""
    instructions = (
        "Поверни ТІЛЬКИ готовий текст поста без службових пояснень",
        "Поверни тільки фінальний текст",
    )
    for line in str(value or "").splitlines():
        words = re.findall(r"\w+", line.casefold(), flags=re.UNICODE)
        if len(words) < 4:
            continue
        for instruction in instructions:
            tokens = set(re.findall(r"\w+", instruction.casefold(), flags=re.UNICODE))
            if len(set(words) & tokens) >= 4 and len(set(words) & tokens) / len(tokens) >= 0.6:
                return True
    return False


_UNSUPPORTED_ANALYSIS_CLAIMS = (
    (
        re.compile(r"(?iu)\b(?:це|такий\s+крок|така\s+подія)\s+(?:свідчить|підтверджує)\s+про\b"),
        re.compile(r"(?iu)(?:свідч\w+\s+про|підтвердж\w+\s+|suggests?\s+that|indicat(?:es|ed)\s+that|demonstrat(?:es|ed)\s+that)"),
    ),
    (
        re.compile(r"(?iu)\bза\s+попередньою\s+інформацією\b"),
        re.compile(r"(?iu)(?:попередн\w+\s+(?:інформац|дан)|preliminary|initial\s+reports?|early\s+reports?)"),
    ),
    (
        re.compile(r"(?iu)\b(?:експерти|аналітики)\s+(?:припускають|прогнозують)\b"),
        re.compile(r"(?iu)(?:експерт\w+|аналітик\w+|experts?|analysts?|predict(?:s|ed)?|forecast(?:s|ed)?)"),
    ),
)


def _unsupported_analysis_claims(article: Any, value: str) -> tuple[str, ...]:
    """Content Tool-style grounding check for conspicuous invented speculation.

    Works with Ukrainian and English evidence, without low-overlap heuristics that
    could reject legitimate English-to-Ukrainian translations.
    """
    source = " ".join((
        str(_v(article, "title", "") or ""),
        _source_text(article),
    ))
    output = str(value or "")
    issues = []
    for generated, supported in _UNSUPPORTED_ANALYSIS_CLAIMS:
        if generated.search(output) and not supported.search(source):
            issues.append("непідтверджений аналітичний висновок або припущення")
            break
    return tuple(issues)


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
    from .publication_safety import is_ai_rejection_text
    if is_ai_rejection_text(value):
        raise ValueError("AI_REJECTION_LEAK_BLOCKED: службова відмова замість Telegram-поста")
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
    analysis_issues = _unsupported_analysis_claims(article, value)
    if analysis_issues:
        raise ValueError("Fact Grounding QA: " + "; ".join(analysis_issues))
    source = "\n".join((
        str(_v(article, "source_name", "")),
        str(_v(article, "title", "")),
        str(_v(article, "raw_text", "")),
    ))
    invented = sorted(_number_tokens(value) - _number_tokens(source))
    if invented:
        raise ValueError("AI додав число, якого немає у джерелі: " + ", ".join(invented[:10]))
    # A number elsewhere in the article (e.g. trolleybus №23) cannot justify
    # a different calendar day. Compare actual day+month pairs whenever the
    # original explicitly contains a Ukrainian named-month date.
    source_dates = _source_day_month_pairs(source)
    output_dates = _source_day_month_pairs(value)
    unsupported_dates = sorted(output_dates - source_dates) if source_dates else []
    if unsupported_dates:
        raise ValueError(
            "AI додав дату, якої немає у джерелі: " +
            ", ".join(f"{day} {month}" for day,month in unsupported_dates[:5])
        )
    # 2.1.5: The operator's published Ledger article #47923 ended midway
    # through "щоб вик". Never accept an unfinished generative fragment.
    # The source footer is appended separately; body must end on a sentence.
    if re.search(r"[А-Яа-яІіЇїЄєҐґA-Za-z0-9]$", value) and not re.search(
        r"(?:https?://\\S+|[.!?…][\\)\\]»”'\"]*)$", value
    ):
        raise ValueError("Редакційний QA: незавершене речення або обірваний текст")
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
            seen.add(value); out.append(("Переглянути відео" if ("youtube.com" in value or "youtu.be" in value or "vimeo.com" in value) else "Деталі/реєстрація", value))
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
    # Compare canonical source URLs, not substrings: a model may append a word
    # directly to a forms.gle token. That is a CORRUPTED link, not a new form.
    source_urls = [(label, literal) for label, literal in _practical_literals(article)]
    seen_urls = {m.group(0).rstrip(".,;:!?") for m in re.finditer(r"https?://[^\s<>]+", value)}
    missing = []
    for label, literal in source_urls:
        if literal.startswith(("http://", "https://")):
            if literal in seen_urls:
                continue
            # A malformed model URL beginning with a source URL must be
            # repaired by replacing it, rather than appending another copy.
            contaminated = [u for u in seen_urls if u.startswith(literal) and u != literal]
            for bad in contaminated:
                value = value.replace(bad, literal)
                seen_urls.discard(bad)
                seen_urls.add(literal)
            if contaminated:
                continue
        elif literal in value:
            continue
        missing.append((label, literal))
    if not missing:
        return value
    suffix = "\n\n" + "\n".join(f"{label}: {literal}" for label, literal in missing)
    if len(value) + len(suffix) > int(hard_max_chars):
        # Source-owned reader-action links are more important than optional
        # commentary. Shorten a complete sentence boundary to leave room;
        # subsequent fact, language and length gates still validate the result.
        room = int(hard_max_chars) - len(suffix)
        if room < 80:
            raise ValueError(
                f"Практичні контакти/URL джерела не вміщуються в ліміт {int(hard_max_chars)}"
            )
        value = _trim_candidate_to_hard_limit(value, room, min_chars=80)
        if len(value) + len(suffix) > int(hard_max_chars):
            raise ValueError(
                f"Не вдалося безпечно зберегти практичні контакти/URL в ліміті {int(hard_max_chars)}"
            )
    return value + suffix


# 2.1.23: Monitoring posts must not send truncated source/AI fragments.
# Examine sentence endings rather than banning legitimate short traffic reports.
_DANGLING_MONITORING_TAIL_RE = re.compile(
    r"(?iu)(?:^|\s)(?:і|й|та|або|але|бо|що|щоб|на|у|в|до|від|по|про|для|із|зі|"
    r"цей|ця|це|ці|тих|цих|того|такого|тех|який|яка|яке|які)\s*[.!?…]*$"
)


def monitoring_fragment_quality_issues(text: str) -> tuple[str, ...]:
    """Conservative final-only check for broken sentences, not stylistic rewriting."""
    value = str(text or "").strip()
    if not value:
        return ()
    # Telegram posts may contain emoji, multiple paragraphs and a source footer.
    body = re.split(r"(?im)^\s*(?:читати\s+у|джерело\s*:|https?://)", value, maxsplit=1)[0]
    sentences = re.split(r"(?<=[.!?…])\s+|\n+", body)
    for sentence in sentences:
        sentence = sentence.strip(" \t\r\n•🚨🔴⚠️")
        if not sentence:
            continue
        if _DANGLING_MONITORING_TAIL_RE.search(sentence):
            return ("MONITORING_BROKEN_SENTENCE_TAIL",)
    return ()


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
    # Independent final publish-boundary language sentinel. Run BEFORE source
    # and fact checks so another issue cannot mask a nonword that would be sent.
    issues.extend("Жорсткий мовний QA: " + item for item in final_language_blockers(value))
    critical = hard_editorial_reject(channel, article, value)
    if critical:
        issues.append(critical)
    postfactum = _postfactum_security_policy(channel, article)
    if postfactum:
        issues.append(postfactum)
    source_policy = _source_body_policy_issues(channel, article, value)
    issues.extend(source_policy)
    if channel.mode == ChannelMode.MONITORING:
        # Shadow-only semantic audit: unresolved paraphrases are measured and
        # never rejected based on lexical overlap alone.
        source_id = str(_v(article, "source_url", "") or _v(article, "id", "") or "unknown")
        trace = trace_output_claims(
            str(_v(article, "raw_text", "") or ""), value, source_id=source_id,
        )
        if trace.unresolved:
            event(
                "editorial", "monitoring claims unresolved in source trace",
                channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0),
                unresolved_count=len(trace.unresolved),
                claim_count=len(trace.statements), trace_mode="shadow_only",
            )
        issues.extend(assess_monitoring_media(article, final_text=value).reasons)
        issues.extend(v.code for v in verify_source_polarity(
            str(_v(article, "raw_text", "") or ""), value,
            source_id=str(_v(article, "source_url", "") or _v(article, "id", "") or "unknown"),
        ))
        issues.extend(v.code for v in verify_qualified_claims(
            str(_v(article, "raw_text", "") or ""), value,
            source_id=str(_v(article, "source_url", "") or _v(article, "id", "") or "unknown"),
        ))
        issues.extend(monitoring_fragment_quality_issues(value))
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
        # Guard the public entrypoint: LIVE may wrap the inner monitoring selector.
        if channel.mode == ChannelMode.MONITORING:
            source_problem = _monitoring_official_context_reject(article, channel)
            if source_problem:
                return EditorialOutcome(Decision.REJECT, reason=source_problem, fit_score=0)
        # Run the source-integrity veto at the shared public entry point.
        # Runtime contracts replace _select_editorial dynamically, so checks
        # confined to that inner method would otherwise be bypassed in LIVE.
        if channel.mode == ChannelMode.EDITORIAL:
            from .source_integrity import multi_story_page_cards_reason
            source_problem = multi_story_page_cards_reason(article)
            if source_problem:
                event("editorial", "multi story page contamination rejected",
                      channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0),
                      reason=source_problem)
                return EditorialOutcome(Decision.REJECT, reason=source_problem, fit_score=0)
        return self._select_monitoring(channel, article) if channel.mode == ChannelMode.MONITORING else self._select_editorial(channel, article)

    def _select_monitoring(self, channel: ChannelConfig, article: Any) -> EditorialOutcome:
        local = deterministic_monitoring_exclusion(channel, article)
        if local:
            return EditorialOutcome(Decision.REJECT, reason="MONITORING_LOCAL_REJECT: " + local, fit_score=0)
        inclusion = channel.policy.selection_rules.strip()
        exclusion = channel.policy.rejection_rules.strip()
        if not inclusion and not exclusion:
            return EditorialOutcome(Decision.PUBLISH, reason="MONITORING_PASS: explicit inclusion/exclusion empty; interest gates disabled", fit_score=100, angle="Передай факт точно і стисло.")
        types = "\n".join(f"- {key}: {label}" for key, label in MONITORING_EVENT_TYPES.items())
        prompt = f"""Ти UNIVERSAL MONITORING POLICY GATE.
Не оцінюй цікавість, wow, editorial value, баланс тем або broad appeal. Застосуй ТІЛЬКИ ручні правила цього каналу.
INCLUSION RULES:
{inclusion or 'Не задано: inclusion виконаний.'}

EXCLUSION RULES:
{exclusion or 'Не задано.'}
Спершу визнач ТИП повідомлення (рівно один ключ):
{types}
attack_summary — лише якщо є конкретний підсумок: кількість загиблих/поранених/пошкоджених об'єктів або офіційні підсумки. Повідомлення «обстріляли/закидають/атакують» без такого результату — attack_in_progress.
Потім рішення: explicit exclusion -> excluded=true; якщо inclusion заданий і SOURCE йому не відповідає -> included=false. Не доповнюй невідомі факти здогадками.
SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}
SOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}
SOURCE:
{_source_pack(article, 3600)}
Поверни ТІЛЬКИ JSON з такими полями (значення визнач сам, не копіюй цей опис):
{{"event_type": "<один ключ зі списку>", "settled": <true якщо подія завершена і має підсумок, інакше false>, "included": <true/false>, "excluded": <true/false>, "reason": "<одне речення: чому саме таке рішення>"}}"""

        def parse(raw: str):
            obj = _parse_json(raw)
            event_type = str(obj.get("event_type") or "").strip().casefold()
            if event_type not in MONITORING_EVENT_TYPES:
                raise ValueError(f"invalid event_type {event_type!r}")
            reason = _clean(obj.get("reason"), 500)
            # 2.2.4: a copied template value is not a decision ("коротко", "<...>").
            if not reason or reason.casefold().strip(" .") in _PLACEHOLDER_REASONS or reason.startswith("<"):
                raise ValueError("placeholder reason")
            for key in ("included", "excluded", "settled"):
                if not isinstance(obj.get(key), bool):
                    raise ValueError(f"{key} must be boolean")
            return event_type, bool(obj["settled"]), bool(obj["included"]), bool(obj["excluded"]), reason

        result = self.gateway.run(prompt, validator=lambda raw: parse(raw), max_output_tokens=220, timeout_seconds=22, purpose="monitoring_selector")
        event_type, settled, included, excluded, reason = parse(result.text)
        # P0: prevent an AI false "not Zaporizhzhia" rejection when the
        # source explicitly identifies the region and reports settled casualties.
        # This corrects ONLY the geographic false-negative, never safety/event blocks.
        regional_source = (" ".join((
            _clean(_v(article, "source_name", ""), 200),
            _clean(_v(article, "title", ""), 400),
            _source_text(article)[:1800],
        ))).casefold()
        false_geo_reject = bool(re.search(
            r"(?:не\s+стосується|не\s+належить|не\s+відповідає).{0,100}"
            r"(?:запорізьк|регіон|област|тематиц)", reason.casefold(), re.S
        ))
        region_evidence = bool(re.search(
            r"запоріжж|запорізьк|оріхів|василівк|мелітопол|бердянськ|"
            r"енергодар|гуляйпол|полог[иів]|токмак", regional_source
        ))
        casualty_evidence = bool(re.search(
            r"загибл|загинул|поранен|постраждал|пошкоджен", regional_source
        ))
        if false_geo_reject and region_evidence and casualty_evidence:
            included, excluded = True, False
            reason = "Регіональна прив'язка підтверджена джерелом; " + reason
            event("editorial", "MONITORING_GEO_FALSE_REJECT_CORRECTED",
                  channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0))
        if event_type == "attack_summary" and not settled:
            event_type = "attack_in_progress"
        blocked_types = channel.policy.blocked_event_types()
        # A model can contradict its own rationale: 56082 was marked included
        # while the returned explanation explicitly ordered rejection.
        # Fail closed for explicit English/Ukrainian reject instructions only.
        rationale_reject = bool(re.search(
            r"(?iu)(?:\bshould\s+be\s+rejected\b|\bmust\s+be\s+rejected\b|"
            r"\bshould\s+not\s+be\s+published\b|\bmust\s+not\s+be\s+published\b|"
            r"\b(?:слід|треба|необхідно)\s+відхилити\b|"
            r"\bне\s+(?:можна|слід|варто)\s+публікувати\b)",
            reason,
        ))
        if event_type in blocked_types:
            return EditorialOutcome(
                Decision.REJECT,
                reason=f"MONITORING_EVENT_TYPE_BLOCKED: [{event_type}] {reason}",
                fit_score=0, provider=result.provider, model=result.model,
            )
        rejected = excluded or (bool(inclusion) and not included) or rationale_reject
        return EditorialOutcome(
            Decision.REJECT if rejected else Decision.PUBLISH,
            reason=("MONITORING_POLICY_REJECT: " if rejected else "MONITORING_POLICY_PASS: ") + f"[{event_type}] " + reason,
            fit_score=0 if rejected else 100,
            angle="" if rejected else "Передай факт точно і стисло.",
            provider=result.provider,
            model=result.model,
        )

    def _select_editorial(self, channel: ChannelConfig, article: Any) -> EditorialOutcome:
        from .source_integrity import multi_story_page_cards_reason
        source_problem = multi_story_page_cards_reason(article)
        if source_problem:
            event("editorial", "multi story page contamination rejected",
                  channel_id=channel.id, article_id=int(_v(article, "id", 0) or 0),
                  reason=source_problem)
            return EditorialOutcome(Decision.REJECT, reason=source_problem, fit_score=0)
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
        prompt = f"""Ти CHANNEL-FIT SELECTOR Telegram-автопілота. Застосуй політику каналу, перевір реальну значущість для аудиторії. Відхиляй гік-експерименти, фанатські порти, гаражні саморобки без суттєвого прориву чи користі. Для commercial editorial шукай бренд, маркетингову механіку або споживчу поведінку. Брак фактів або контексту означає reject, а не припущення.
PURPOSE: {p.purpose}\nAUDIENCE: {p.audience}\nSELECTION: {p.selection_rules}\nEXCLUSIONS: {p.rejection_rules}\nEXTRA: {p.selector_extra_prompt}
{topic_memory}
SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE TITLE: {_clean(_v(article, 'title', ''), 700)}\nSOURCE:\n{_source_pack(article, 3600)}
Для CPU-local fallback одразу оціни також editorial value, щоб не робити окремий дорогий AI-виклик.
Якщо decision="reject", reject_code — РІВНО один із: off_topic, weak_audience_hook, routine_pr, weak_mechanism, weak_visual, duplicate, insufficient_facts, stale, other.
Поверни ТІЛЬКИ JSON: {{"decision":"publish" або "reject","reject_code":"","fit_score":0,"reason":"коротко","angle":"кут","topic_tags":["..."],"novelty":0,"consequence_or_insight":0,"mechanism":0,"reader_payoff":0,"retellability":0,"concrete_stakes":0,"why_now":0,"curiosity_only":false}}"""

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
            # 2.2.3: a structured code makes rejection statistics countable instead of
            # guessing a category from free text. Unknown/missing codes stay uncoded.
            code = str(fit.get("reject_code") or "").strip().casefold()
            prefix = f"[{code}] " if code in SELECTOR_REJECT_CODES else ""
            return EditorialOutcome(Decision.REJECT, reason=prefix + _clean(fit.get("reason"), 600), fit_score=score, provider=fit_result.provider, model=fit_result.model)
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
        prompt = f"""Ти UNIVERSAL EDITORIAL VALUE GATE. Матеріал уже пройшов channel fit. Оціни 0..100: novelty, consequence_or_insight, mechanism, reader_payoff, retellability, concrete_stakes, why_now. curiosity_only=true для старих ігрових портів, одиничних експериментів, нішевих хобі та саморобок без доведеного широкого результату; не прирівнюй технічну новизну до значущості.
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
        if curiosity and not (insight >= 80 and payoff >= 80 and novelty >= 80):
            return False, "niche_curiosity_only", score
        standard = score >= t["standard_score"] and payoff >= t["standard_payoff"] and retell >= t["standard_retellability"] and max(insight, mechanism, stakes) >= t["standard_signal"] and not (why_now < t["standard_why_now"] and novelty < t["standard_novelty_exception"])
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
СТРУКТУРА: якщо фінальний текст має 350+ символів, обов'язково поділи його щонайменше на 2 короткі смислові абзаци; типовий редакторський пост — 2–3 абзаци, орієнтир 500–850 символів за наявності змісту. Не пиши суцільну стіну тексту. Не використовуй штучні повтори літер або пунктуації.{monitoring_rule}{named_source_style}
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
            return _rc111_prepare_candidate(
                channel, article, raw,
                hard_max_chars=validation_hard_max,
                min_chars=effective_min,
            )

        slop_profile = _anti_slop_profile(channel)

        def validator(raw: str) -> None:
            if _is_editorial_prompt_echo(raw):
                raise ValueError("AI повторив службову інструкцію промпту")
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
        lt = apply_local_languagetool_detailed(final, timeout=1.2, max_changes=18, require_ready=False, source_text=_source_pack(article, 6200))
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
        prompt = f"""Ти фінальний редактор українського Telegram-тексту перед автоматичною публікацією. Перевір факти за SOURCE, потім виправ мову, граматику, узгодження, ясність, повтори і структуру. Якщо DRAFT містить непідтверджені твердження, перепиши відповідний фрагмент ЗАНОВО з SOURCE, а не поліруй вигадку. Не додавай жодних нових фактів/чисел/назв. Не роздувай коротке джерело. Не додавай порад, моралей чи фраз про відсутні деталі, якщо їх немає у SOURCE. {source_attribution_instruction}Якщо текст уже добрий, поверни його без змін.
CHANNEL RULES: {p.writing_rules}\nSTYLE: {p.style_rules}\n{style_memory}\n{source_context_instruction}SOURCE NAME: {_clean(_v(article, 'source_name', ''), 300)}\nSOURCE:\n{_source_pack(article, 5200)}\nDRAFT:\n{draft}\nПоверни тільки фінальний текст."""

        def prepared_text(raw: str) -> str:
            return _rc111_prepare_candidate(
                channel, article, raw,
                hard_max_chars=final_hard_max,
                min_chars=min_chars,
            )

        slop_profile = _anti_slop_profile(channel)

        def validator(raw: str) -> None:
            if _is_editorial_prompt_echo(raw):
                raise ValueError("AI повторив службову інструкцію промпту")
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
