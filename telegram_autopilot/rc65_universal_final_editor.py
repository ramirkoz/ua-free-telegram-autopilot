from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any, Mapping

LOG = logging.getLogger("telegram_autopilot.rc65")
_INSTALLED = False

_PREV_SELECTOR = None
_PREV_DECIDE = None

_SELECTOR_CACHE_TTL_SECONDS = 6 * 60 * 60
_SELECTOR_CACHE_MAX = 500
_SELECTOR_CACHE: dict[tuple[int, int, str], tuple[float, Any, dict[str, Any]]] = {}


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _selector_key(article: Any, channel_id: int) -> tuple[int, int, str]:
    try:
        article_id = int(_v(article, "id", 0) or 0)
    except Exception:
        article_id = 0
    title = " ".join(str(_v(article, "title", "") or "").split()).casefold()[:240]
    return int(channel_id or 0), article_id, title


def _prune_selector_cache(now: float | None = None) -> None:
    stamp = time.monotonic() if now is None else float(now)
    expired = [key for key, value in _SELECTOR_CACHE.items() if stamp - value[0] > _SELECTOR_CACHE_TTL_SECONDS]
    for key in expired:
        _SELECTOR_CACHE.pop(key, None)
    if len(_SELECTOR_CACHE) <= _SELECTOR_CACHE_MAX:
        return
    ordered = sorted(_SELECTOR_CACHE.items(), key=lambda item: item[1][0])
    for key, _value in ordered[: len(_SELECTOR_CACHE) - _SELECTOR_CACHE_MAX]:
        _SELECTOR_CACHE.pop(key, None)


def _marketing_route(data: Mapping[str, Any]) -> str:
    fit = int(data.get("fit_score", 0) or 0)
    human = int(data.get("human_interest_score", 0) or 0)
    share = int(data.get("friend_share_score", 0) or 0)
    creative = int(data.get("creative_surprise_score", 0) or 0)
    mechanic = int(data.get("marketing_mechanic_score", 0) or 0)
    hook = " ".join(str(data.get("non_marketer_hook") or "").split())

    # Three independent editorial routes. A story does not need Cannes-style
    # creativity when the real hook is a concrete mechanism that changes how
    # people buy, pay, subscribe, return, watch or share.
    if fit >= 50 and human >= 68 and share >= 62 and creative >= 62 and mechanic >= 48:
        return "creative"
    if fit >= 45 and human >= 80 and share >= 68 and mechanic >= 42 and hook:
        return "human"
    if fit >= 40 and human >= 50 and share >= 35 and mechanic >= 70 and hook:
        return "behavior"
    if fit >= 48 and human >= 66 and share >= 50 and mechanic >= 62 and hook:
        return "behavior-balanced"
    return ""


def _run_selector_rc65(policy: Any, article: Any, *, channel_id: int = 0):
    from . import rc62_editorial_control as rc62

    key = _selector_key(article, int(channel_id or 0))
    stamp = time.monotonic()
    _prune_selector_cache(stamp)
    cached = _SELECTOR_CACHE.get(key)
    if cached is not None and stamp - cached[0] <= _SELECTOR_CACHE_TTL_SECONDS:
        result, parsed = cached[1], dict(cached[2])
        LOG.info(
            "RC65 SELECTOR_CACHE_HIT channel_id=%s article_id=%s fit=%s; retry resumes after selector",
            int(channel_id or 0), _v(article, "id", "?"), int(parsed.get("fit_score", 0) or 0),
        )
        return result, parsed

    result, parsed = _PREV_SELECTOR(policy, article, channel_id=channel_id)
    data = dict(parsed)
    route = ""

    if rc62._marketing(policy):
        try:
            raw = rc62._parse_marketing(result.text)
        except Exception:
            raw = dict(data)
        route = _marketing_route(raw)
        if raw.get("decision") == "publish" and data.get("decision") != "publish" and route:
            data = dict(raw)
            data["decision"] = "publish"
            data["reason"] = (
                f"RC65 MARKETING_ROUTE_PASS route={route}: матеріал проходить окремим редакційним маршрутом "
                f"(fit={int(data.get('fit_score', 0) or 0)}, human={int(data.get('human_interest_score', 0) or 0)}, "
                f"share={int(data.get('friend_share_score', 0) or 0)}, creative={int(data.get('creative_surprise_score', 0) or 0)}, "
                f"mechanic={int(data.get('marketing_mechanic_score', 0) or 0)})."
            )

    if data.get("decision") == "publish":
        if not route and rc62._marketing(policy):
            route = _marketing_route(data) or "legacy-pass"
        _SELECTOR_CACHE[key] = (stamp, result, dict(data))
        _prune_selector_cache(stamp)
        LOG.info(
            "RC65 SELECTOR_PASS channel_id=%s article_id=%s route=%s fit=%s",
            int(channel_id or 0), _v(article, "id", "?"), route or "channel-policy",
            int(data.get("fit_score", 0) or 0),
        )
    else:
        LOG.info(
            "RC65 SELECTOR_REJECT channel_id=%s article_id=%s fit=%s reason=%s",
            int(channel_id or 0), _v(article, "id", "?"), int(data.get("fit_score", 0) or 0),
            " ".join(str(data.get("reason") or "").split())[:500],
        )
    return result, data


def _policy_for(channel: Any):
    from . import rc51_feedback as rc51
    from .rc59_universal_policy import default_policy

    db = rc51._ACTIVE_DB
    if db is not None:
        try:
            return db.rc59_get_channel_policy(int(channel.id))
        except Exception:
            pass
    return default_policy(channel)


def _final_editor_prompt(channel: Any, article: Any, decision: Any, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack

    policy = _policy_for(channel)
    source = build_evidence_pack(article, char_budget=6200).text
    writing_rules = " ".join(str(getattr(policy, "writing_rules", "") or "").split())
    style_rules = " ".join(str(getattr(policy, "style_rules", "") or "").split())
    extra = " ".join(str(getattr(policy, "extra_instructions", "") or "").split())
    draft = str(getattr(decision, "telegram_teaser", "") or "")

    return f"""Ти УНІВЕРСАЛЬНИЙ ФІНАЛЬНИЙ РЕДАКТОР українського Telegram-каналу. Це останній copy-edit після фактичного writer-а.

ТВОЯ РОБОТА:
1. Зроби текст природним, легким і людським українським письмом: коротші речення, ясна логіка, нормальний ритм, без канцелярщини, буквального машинного перекладу, повторів і зайвих пояснень.
2. ЗБЕРЕЖИ голос саме цього каналу. Не перетворюй різні канали на один стиль.
3. НЕ змінюй і НЕ додавай жодного факту, числа, дати, імені, бренду, причинного зв'язку, атрибуції, ступеня певності чи висновку. SOURCE EVIDENCE є єдиним джерелом фактів.
4. Не вигадуй контекст, якого немає у SOURCE. Не роби текст сенсаційнішим за джерело.
5. Імена людей та усталені загальні назви подавай природною українською; бренди, продукти, моделі, абревіатури, формули й технічні позначення не перекручуй.
6. Не додавай заголовок, службові пояснення, коментар редактора або слово «Джерело». Поверни ТІЛЬКИ готове тіло поста.
7. Максимум {int(hard_limit)} символів.

ПОЛІТИКА КАНАЛУ:
WRITING: {writing_rules or 'природний короткий Telegram-текст'}
STYLE: {style_rules or 'ясно, без штучної урочистості та канцеляризмів'}
EXTRA: {extra or 'немає'}

SOURCE EVIDENCE:
{source}

FACT-SAFE DRAFT:
{draft}

Поверни ТІЛЬКИ фінально відредагований український текст."""


def _universal_final_edit(channel: Any, article: Any, decision: Any, *, hard_limit: int):
    from . import production_pipeline as production
    from . import rc40_policy as rc40

    if getattr(decision, "decision", "") != "publish":
        return decision
    original = str(getattr(decision, "telegram_teaser", "") or "")
    if not original.strip():
        return decision

    article_id = _v(article, "id", "?")
    channel_id = int(getattr(channel, "id", 0) or 0)
    original_quality = production.assess_rewrite(original, hard_limit=hard_limit)
    allowed_years = rc40._rc40_allowed_years(article)
    allowed_numbers = rc40._rc40_allowed_numbers(article)
    prompt = _final_editor_prompt(channel, article, decision, hard_limit=hard_limit)

    def validator(raw: str) -> None:
        candidate = rc40._validated_ua_body(
            raw, article=article, allowed_years=allowed_years,
            allowed_numbers=allowed_numbers, hard_limit=hard_limit,
        )
        quality = production.assess_rewrite(candidate, hard_limit=hard_limit)
        floor = max(68, int(original_quality.score) - 4)
        if quality.score < floor:
            raise production.ProductionPipelineError(
                f"RC65 final editor quality regression {quality.score}/100 < {floor}/100"
            )

    LOG.info(
        "RC65 FINAL_EDITOR_START channel_id=%s article_id=%s original_provider=%s/%s quality=%s",
        channel_id, article_id, getattr(decision, "provider", ""), getattr(decision, "model", ""), original_quality.score,
    )
    try:
        result = production.run_ai(
            prompt, validator=validator,
            max_output_tokens=720, local_prompt=prompt, local_max_output_tokens=720,
            cloud_timeout_seconds=28, local_timeout_seconds=16, task_timeout_seconds=85,
            local_repair=False, suppress_provider_on_quota=False,
            allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
        )
        edited = rc40._validated_ua_body(
            result.text, article=article, allowed_years=allowed_years,
            allowed_numbers=allowed_numbers, hard_limit=hard_limit,
        )
        edited_quality = production.assess_rewrite(edited, hard_limit=hard_limit)
    except Exception as exc:
        # The input Decision has already passed the existing fact/language gates.
        # The final editor improves copy but must never become a new throughput kill switch.
        LOG.warning(
            "RC65 FINAL_EDITOR_DEGRADED channel_id=%s article_id=%s keep_original=1 error=%s",
            channel_id, article_id, exc,
        )
        return replace(
            decision,
            reason=str(getattr(decision, "reason", "")) + " RC65 universal final editor degraded; safe original kept.",
        )

    changed = edited != original
    LOG.info(
        "RC65 FINAL_EDITOR_PASS channel_id=%s article_id=%s changed=%s editor=%s/%s quality=%s->%s chars=%s",
        channel_id, article_id, int(changed), result.provider, result.model,
        original_quality.score, edited_quality.score, len(edited),
    )
    if not changed:
        return replace(
            decision,
            reason=str(getattr(decision, "reason", "")) + " RC65 universal final editor PASS (no textual change).",
        )
    return replace(
        decision,
        telegram_teaser=edited,
        full_article_uk=edited,
        event_summary=edited[:1000],
        provider=result.provider,
        model=result.model,
        reason=(
            str(getattr(decision, "reason", ""))
            + f" RC65 universal final editor PASS via {result.provider}/{result.model}; "
              f"quality {original_quality.score}->{edited_quality.score}."
        ),
    )


def _decide_rc65(channel: Any, article: Any, recent: list[Any], *, hard_limit: int, format_marker: str | None = None):
    key = _selector_key(article, int(getattr(channel, "id", 0) or 0))
    try:
        decision = _PREV_DECIDE(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )
    except Exception as exc:
        stage = "WRITER_OR_QA" if key in _SELECTOR_CACHE else "PRESELECT_OR_SELECTOR"
        LOG.warning(
            "RC65 PIPELINE_FAIL channel_id=%s article_id=%s stage=%s error=%s",
            int(getattr(channel, "id", 0) or 0), _v(article, "id", "?"), stage, exc,
        )
        raise

    if getattr(decision, "decision", "") != "publish":
        LOG.info(
            "RC65 PIPELINE_END channel_id=%s article_id=%s decision=%s",
            int(getattr(channel, "id", 0) or 0), _v(article, "id", "?"), getattr(decision, "decision", ""),
        )
        return decision
    return _universal_final_edit(channel, article, decision, hard_limit=hard_limit)


def install_rc65_universal_final_editor() -> None:
    global _INSTALLED, _PREV_SELECTOR, _PREV_DECIDE
    if _INSTALLED:
        return

    from . import production_pipeline as prod
    from . import rc59_universal_policy as rc59
    from . import service as svc

    _PREV_SELECTOR = rc59._run_selector
    _PREV_DECIDE = prod.decide

    rc59._run_selector = _run_selector_rc65

    def wrapped(channel, article, recent, *, hard_limit=prod.MEDIA_POST_HARD_LIMIT, format_marker=None):
        return _decide_rc65(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )

    prod.decide = wrapped
    svc.decide = wrapped
    prod.POST_FORMAT_PREFIX = "telegram-post-v40:"
    svc.POST_FORMAT_PREFIX = "telegram-post-v40:"

    LOG.info(
        "RC65 installed: universal final editor for every channel, three-route ПРОДАНО! selector, "
        "selector-pass resume cache and explicit pipeline stage diagnostics; source set unchanged"
    )
    _INSTALLED = True
