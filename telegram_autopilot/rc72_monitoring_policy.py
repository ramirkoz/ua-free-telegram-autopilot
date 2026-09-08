from __future__ import annotations

import logging
from typing import Any, Mapping

LOG = logging.getLogger("telegram_autopilot.rc72.monitoring")
_INSTALLED = False
_PREV_MONITORING_SELECTOR = None


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _clean(value: Any, limit: int = 12000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _normalize_saved_rule(value: str, *, kind: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        from . import rc59_universal_policy as rc59
        generic = rc59.ChannelPolicy()
        default_text = generic.selection_rules if kind == "selection" else generic.rejection_rules
        if _clean(text).casefold() == _clean(default_text).casefold():
            return ""
    except Exception:
        pass
    return text


def _saved_rules(channel_id: int) -> tuple[str, str] | None:
    try:
        from . import rc51_feedback as rc51
        db = rc51._ACTIVE_DB
        if db is None:
            return None
        with db.connect() as con:
            row = con.execute(
                "SELECT selection_rules,rejection_rules FROM channel_policies WHERE channel_id=?",
                (int(channel_id),),
            ).fetchone()
        if row is None:
            return None
        inclusion = _normalize_saved_rule(str(row[0] or ""), kind="selection")
        exclusion = _normalize_saved_rule(str(row[1] or ""), kind="rejection")
        return inclusion, exclusion
    except Exception as exc:
        LOG.debug("RC72 saved monitoring policy lookup failed channel_id=%s: %s", channel_id, exc)
        return None


def _monitoring_selector_rc72(policy: Any, article: Any, *, channel_id: int):
    # Old channels that never saved an explicit fine policy keep the previous
    # monitoring behaviour. Saved rules, when present, are the only authority.
    saved = _saved_rules(int(channel_id or 0))
    if saved is None:
        return _PREV_MONITORING_SELECTOR(policy, article, channel_id=int(channel_id or 0))

    inclusion, exclusion = saved
    if not inclusion and not exclusion:
        from .ai_router import Result
        result = Result("monitoring-pass", "local-rule", "rc72-monitoring-no-rules", "RC72 monitoring no explicit rules")
        return result, {
            "decision": "publish",
            "fit_score": 100,
            "reason": "RC72 MONITORING_PASS: для каналу не задано inclusion/exclusion rules; editorial-interest gates вимкнені.",
            "angle": "Передай новий факт точно, стисло і без оцінки його цікавості.",
            "topic_tags": [],
        }

    from . import production_pipeline as production
    from .evidence_pack import build_evidence_pack
    from . import rc68_editorial_value as rc68

    source = build_evidence_pack(article, char_budget=5200).text
    prompt = f"""Ти UNIVERSAL MONITORING POLICY GATE.

Це МОНІТОРИНГОВИЙ канал. НЕ оцінюй цікавість, broad appeal, wow-ефект, editorial value, тематичний баланс або бажання читача це переказати.
Ти застосовуєш ТІЛЬКИ ручні правила КОНКРЕТНОГО каналу нижче.

INCLUSION RULES (що канал відстежує):
{inclusion or 'Не задано: вважай inclusion виконаним.'}

EXCLUSION RULES (що канал не бере):
{exclusion or 'Не задано.'}

Правила рішення:
1. Якщо SOURCE чітко підпадає під EXCLUSION RULES -> reject.
2. Якщо inclusion заданий і SOURCE не відповідає йому -> reject.
3. Якщо inclusion не заданий -> не вигадуй додаткових тематичних вимог.
4. Якщо є сумнів -> publish. Моніторинг повинен краще пропустити зайве, ніж мовчки втратити цільову подію.

SOURCE NAME:
{_clean(_v(article, 'source_name', ''), 300)}
SOURCE TITLE:
{_clean(_v(article, 'title', ''), 700)}
SOURCE:
{source}

Поверни ТІЛЬКИ JSON:
{{"included":true або false,"excluded":true або false,"reason":"коротко, яке саме ручне правило спрацювало або none"}}
""".strip()

    def parse(raw: str) -> tuple[bool, bool, str]:
        obj = rc68._parse_json_object(raw)
        included = bool(obj.get("included", True))
        excluded = bool(obj.get("excluded", False))
        reason = _clean(obj.get("reason"), 500)
        return included, excluded, reason

    def validator(raw: str) -> None:
        parse(raw)

    try:
        result = production.run_ai(
            prompt,
            validator=validator,
            max_output_tokens=190,
            local_prompt=prompt,
            local_max_output_tokens=210,
            cloud_timeout_seconds=20,
            local_timeout_seconds=30,
            task_timeout_seconds=75,
            local_repair=False,
            suppress_provider_on_quota=False,
            allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
        )
        included, excluded, reason = parse(result.text)
    except Exception as exc:
        # A technical outage is not editorial permission to publish. Let the
        # upper pipeline convert SELECTOR_UNAVAILABLE into WAITING_AI/retry.
        LOG.warning("RC82 monitoring policy gate unavailable channel_id=%s; defer instead of fail-open: %s", channel_id, exc)
        raise

    rejected = bool(excluded or (bool(inclusion) and not included))
    return result, {
        "decision": "reject" if rejected else "publish",
        "fit_score": 0 if rejected else 100,
        "reason": ("RC72 MONITORING_POLICY_REJECT: " if rejected else "RC72 MONITORING_POLICY_PASS: ") + (reason or "none"),
        "angle": "" if rejected else "Передай новий факт точно, стисло і без оцінки його цікавості.",
        "topic_tags": [],
    }


def install_rc72_monitoring_policy() -> None:
    global _INSTALLED, _PREV_MONITORING_SELECTOR
    if _INSTALLED:
        return
    from . import rc68_editorial_value as rc68

    _PREV_MONITORING_SELECTOR = rc68._monitoring_selector
    rc68._monitoring_selector = _monitoring_selector_rc72
    LOG.info("RC72 installed: monitoring uses only explicitly saved per-channel inclusion/exclusion rules; no editorial-interest gate")
    _INSTALLED = True
