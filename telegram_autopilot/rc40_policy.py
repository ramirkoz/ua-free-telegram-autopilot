from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from .models import Decision
from .rc39_policy import anti_slop_issues, build_russian_editorial_prompt, build_ukrainian_bridge_prompt, _clean_model_text, _looks_russian_prose

LOG = logging.getLogger("telegram_autopilot.rc40")
_INSTALLED = False


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else str(value)


_GENERIC_LATIN_TECH = {
    "email", "web", "app", "online", "offline", "cloud", "server", "client",
    "browser", "chatbot", "startup", "internet", "mobile", "desktop", "software",
    "hardware", "open", "source",
}


def _rc40_allowed_years(article) -> set[int]:
    from . import production_pipeline as production_module
    years = set(production_module._allowed_output_years(article))
    published = _row_value(article, "source_published_at")
    match = re.search(r"\b(20\d{2})\b", published)
    if match:
        years.add(int(match.group(1)))
    return years


def _rc40_format_numbers(value: str) -> set[str]:
    """Formatting-only numeric fragments that are not factual quantities."""
    from . import production_pipeline as production_module
    text = str(value or "")
    ignored: set[str] = set()
    for match in production_module._NUMBER_RE.finditer(text):
        raw = match.group(0)
        normalized = production_module._normalize_number(raw)
        start, end = match.span()
        before = text[max(0, start - 2):start]
        after = text[end:min(len(text), end + 2)]
        if ":" in before or ":" in after:
            ignored.add(normalized)
            continue
        if re.fullmatch(r"0\d", raw.strip()) and not raw.strip().endswith("%"):
            ignored.add(normalized)
            continue
        if (before[-1:] in {"/", "-"} or after[:1] in {"/", "-"}) and len(raw.strip()) <= 2:
            ignored.add(normalized)
    return ignored


def _rc40_allowed_numbers(article, candidate: str = "") -> set[str]:
    from . import production_pipeline as production_module
    return set(production_module._source_numbers(article)) | _rc40_format_numbers(candidate)


def _scrub_generic_latin_for_fact_guard(value: str) -> str:
    text = str(value or "")
    if not text:
        return text
    pattern = re.compile(r"\b(" + "|".join(re.escape(item) for item in sorted(_GENERIC_LATIN_TECH, key=len, reverse=True)) + r")\b", re.I)
    return pattern.sub("term", text)


def _validate_fact_guard_rc40(article, output: str):
    from . import production_pipeline as production_module
    return production_module.validate_fact_guard(article, _scrub_generic_latin_for_fact_guard(output))


def validate_russian_editorial_rc40(
    raw: str,
    *,
    allowed_years: set[int],
    allowed_numbers: set[str],
) -> str:
    """Validate bridge facts/language without turning draft length into a publish gate."""
    from . import production_pipeline as production_module

    text = _clean_model_text(raw)
    cyr = len(re.findall(r"[А-Яа-яЁёІіЇїЄєҐґ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    low = f" {text.casefold()} "
    russian_markers = (
        " что ", " это ", " для ", " из ", " но ", " уже ", " который ", " которая ",
        " потому ", " чтобы ", " если ", " при этом ", " после ", " когда ", " можно ",
    )
    marker_hits = sum(1 for marker in russian_markers if marker in low)
    ua_only = len(re.findall(r"[іїєґ]", text, re.I))
    if cyr < 90 or cyr < latin * 2 or ua_only > max(3, cyr // 45) or marker_hits < 2:
        raise production_module.ProductionPipelineError(
            "RC40 RU bridge: модель не повернула достатню природну російську редакторську прозу."
        )
    production_module._validate_years(text, allowed_years)
    production_module._validate_numbers(text, set(allowed_numbers) | _rc40_format_numbers(text))
    return text


def _validated_ua_body(raw: str, *, article, allowed_years: set[int], allowed_numbers: set[str], hard_limit: int) -> str:
    """Hard publication safety only: facts, completeness, language and corruption."""
    from . import production_pipeline as production_module

    checked = production_module.validate_rewrite(
        raw,
        allowed_years=allowed_years,
        allowed_numbers=set(allowed_numbers) | _rc40_format_numbers(raw),
        hard_limit=hard_limit,
        enforce_readability=False,
    )
    body = production_module.apply_safe_ukrainian_fixes(checked["body"])
    body = production_module.remove_source_author_meta_sentences(body)
    if body != checked["body"]:
        checked = production_module.validate_rewrite(
            body,
            allowed_years=allowed_years,
            allowed_numbers=set(allowed_numbers) | _rc40_format_numbers(body),
            hard_limit=hard_limit,
            enforce_readability=False,
        )
        body = checked["body"]
    try:
        _validate_fact_guard_rc40(article, checked["post"])
    except production_module.FactGuardError as exc:
        raise production_module.ProductionPipelineError(str(exc)) from exc
    blockers = production_module.final_language_blockers(body)
    if blockers or not production_module.looks_ukrainian(body):
        raise production_module.ProductionPipelineError(
            "RC40 UA hard gate: " + "; ".join(blockers or ["текст не визначено як природну українську прозу"])
        )
    editorial = production_module.hard_editorial_blockers(body)
    if editorial:
        raise production_module.ProductionPipelineError(
            "RC40 structural blocker: " + "; ".join(editorial)
        )
    quality = production_module.assess_rewrite(body, hard_limit=hard_limit)
    if quality.score < 60:
        raise production_module.ProductionPipelineError(
            f"RC40 unusable editorial quality {quality.score}/100: " + "; ".join(quality.issues[:5])
        )
    return body


def _repair_prompt(base_prompt: str, body: str, issues: tuple[str, ...], score: int) -> str:
    detail = "; ".join(issues[:6]) or "зроби ритм природнішим"
    return (
        base_prompt
        + "\n\nRC40 TARGETED COPY-EDIT. Попередній кандидат ФАКТИЧНО БЕЗПЕЧНИЙ, але стилістично неідеальний. "
          "Виправ ТІЛЬКИ зазначені проблеми. Не додавай і не змінюй жодного факту, числа, дати, назви, причинного зв'язку чи атрибуції. "
          f"Поточна редакторська оцінка: {score}/100. Проблеми: {detail}. "
          "Поверни тільки відредагований український текст.\n\nPREVIOUS SAFE CANDIDATE:\n"
        + body[:2400]
    )


def install_rc40_policy() -> None:
    """RC40: keep factual hard gates, make editorial quality repairable/soft."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production_module
    from . import rc37_policy as rc37_module
    from . import rc38_policy as rc38_module
    from . import service as service_module

    marker = "telegram-post-v25:"
    production_module.POST_FORMAT_PREFIX = marker
    service_module.POST_FORMAT_PREFIX = marker

    def decide(channel, article, recent, *, hard_limit=production_module.MEDIA_POST_HARD_LIMIT, format_marker=None):
        article_id = _row_value(article, "id", "?")
        LOG.info("RC40 stage article_id=%s stage=START hard_limit=%s", article_id, hard_limit)

        if int(hard_limit) > int(production_module.MEDIA_POST_HARD_LIMIT):
            title = _row_value(article, "title")
            LOG.info("RC40 stage article_id=%s stage=REJECT reason=SKIP_NO_MEDIA", article_id)
            return Decision(
                decision="reject", duplicate_of=None,
                reason="SKIP_NO_MEDIA: не знайдено релевантного фото/відео; CTRL+UA не публікує текстові новини без медіа.",
                event_key="media-required", event_summary=title[:1000], headline_uk="", telegram_teaser="",
                full_article_uk="", media_captions_uk={}, confidence=1.0,
                provider="local-rule", model="rc40-media-required",
            )

        reason = rc37_module.newsworthiness_reject_reason(article)
        if reason:
            LOG.info("RC40 stage article_id=%s stage=REJECT reason=NEWSWORTHINESS", article_id)
            return Decision(
                decision="reject", duplicate_of=None, reason=reason,
                event_key="ctrl-ua-newsworthiness-v2", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.99, provider="local-rule", model="newsworthiness-v2",
            )

        balance_reason = rc38_module.topic_balance_reject_reason(article, recent)
        if balance_reason:
            LOG.info("RC40 stage article_id=%s stage=REJECT reason=TOPIC_BALANCE", article_id)
            return Decision(
                decision="reject", duplicate_of=None, reason=balance_reason,
                event_key="ctrl-ua-topic-balance-v1", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.98, provider="local-rule", model="topic-balance-v1",
            )

        duplicate_id = production_module._title_duplicate(article, recent)
        if duplicate_id is not None:
            LOG.info("RC40 stage article_id=%s stage=DUPLICATE duplicate_of=%s", article_id, duplicate_id)
            return Decision(
                decision="duplicate", duplicate_of=duplicate_id,
                reason=f"Дуже близький заголовок до вже опублікованого матеріалу #{duplicate_id}.",
                event_key="title-duplicate", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.99, provider="local-rule", model="title-dedupe",
            )

        deterministic = production_module._deterministic_reject_reason(article)
        if deterministic:
            LOG.info("RC40 stage article_id=%s stage=REJECT reason=EDITORIAL_FILTER", article_id)
            return Decision(
                decision="reject", duplicate_of=None, reason=deterministic,
                event_key="editorial-filter", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.95, provider="local-rule", model="editorial-gate",
            )

        allowed_years = _rc40_allowed_years(article)
        allowed_numbers = _rc40_allowed_numbers(article)
        ru_prompt = build_russian_editorial_prompt(channel, article, hard_limit=hard_limit)
        russian_draft = ""
        bridge_result = None

        def ru_validator(raw: str) -> None:
            validate_russian_editorial_rc40(raw, allowed_years=allowed_years, allowed_numbers=allowed_numbers)

        LOG.info("RC40 stage article_id=%s stage=RU_BRIDGE_START", article_id)
        try:
            bridge_result = production_module.run_ai(
                ru_prompt, validator=ru_validator,
                max_output_tokens=900, local_prompt=ru_prompt, local_max_output_tokens=900,
                cloud_timeout_seconds=20, local_timeout_seconds=40, task_timeout_seconds=75,
                local_repair=False, skip_providers={"codex"},
                suppress_provider_on_quota=False,
                allowed_providers={"gemini", "groq", "nvidia", "cloudflare", "local"},
            )
            russian_draft = validate_russian_editorial_rc40(
                bridge_result.text, allowed_years=allowed_years, allowed_numbers=allowed_numbers
            )
            LOG.info(
                "RC40 stage article_id=%s stage=RU_BRIDGE_PASS provider=%s model=%s chars=%s",
                article_id, bridge_result.provider, bridge_result.model, len(russian_draft),
            )
        except production_module.AIRouterError as first_exc:
            LOG.warning("RC40 stage article_id=%s stage=RU_BRIDGE_PRIMARY_FAIL error=%s", article_id, first_exc)
            try:
                bridge_result = production_module.run_ai(
                    ru_prompt, validator=ru_validator,
                    max_output_tokens=900, local_prompt=ru_prompt, local_max_output_tokens=900,
                    cloud_timeout_seconds=24, local_timeout_seconds=30, task_timeout_seconds=60,
                    local_repair=False, suppress_provider_on_quota=False,
                    allowed_providers={"codex", "gemini"},
                )
                russian_draft = validate_russian_editorial_rc40(
                    bridge_result.text, allowed_years=allowed_years, allowed_numbers=allowed_numbers
                )
                LOG.info(
                    "RC40 stage article_id=%s stage=RU_BRIDGE_PASS provider=%s model=%s chars=%s",
                    article_id, bridge_result.provider, bridge_result.model, len(russian_draft),
                )
            except production_module.AIRouterError as second_exc:
                LOG.warning(
                    "RC40 stage article_id=%s stage=RU_BRIDGE_BYPASS error=%s",
                    article_id, second_exc,
                )
                russian_draft = ""

        ua_prompt = build_ukrainian_bridge_prompt(channel, article, russian_draft, hard_limit=hard_limit)
        if not russian_draft:
            ua_prompt += (
                "\n\nRC40 NOTE: внутрішній RU bridge цього разу недоступний. Самостійно знайди редакторський кут у SOURCE; "
                "SOURCE лишається єдиним джерелом фактів."
            )

        def ua_hard_validator(raw: str) -> None:
            _validated_ua_body(
                raw, article=article, allowed_years=allowed_years,
                allowed_numbers=allowed_numbers, hard_limit=hard_limit,
            )

        LOG.info("RC40 stage article_id=%s stage=UA_FINAL_START providers=codex,gemini", article_id)
        try:
            final_result = production_module.run_ai(
                ua_prompt, validator=ua_hard_validator,
                max_output_tokens=560, local_prompt=ua_prompt, local_max_output_tokens=560,
                cloud_timeout_seconds=32, local_timeout_seconds=12, task_timeout_seconds=90,
                local_repair=False, suppress_provider_on_quota=False,
                allowed_providers={"codex", "gemini"},
            )
        except production_module.AIRouterError as primary_exc:
            LOG.warning(
                "RC40 stage article_id=%s stage=UA_PRIMARY_FAIL fallback=groq,nvidia error=%s",
                article_id, primary_exc,
            )
            try:
                final_result = production_module.run_ai(
                    ua_prompt, validator=ua_hard_validator,
                    max_output_tokens=560, local_prompt=ua_prompt, local_max_output_tokens=560,
                    cloud_timeout_seconds=24, local_timeout_seconds=10, task_timeout_seconds=75,
                    local_repair=False, suppress_provider_on_quota=False,
                    allowed_providers={"groq", "nvidia"},
                )
            except production_module.AIRouterError as fallback_exc:
                raise production_module.PostAIQAExhausted(
                    "RC40: жоден фінальний UA-провайдер не дав фактично безпечний текст. " + str(fallback_exc),
                    (str(primary_exc), str(fallback_exc)),
                    provider_outage="Немає доступного AI-провайдера" in str(fallback_exc),
                ) from fallback_exc

        body = _validated_ua_body(
            final_result.text, article=article, allowed_years=allowed_years,
            allowed_numbers=allowed_numbers, hard_limit=hard_limit,
        )
        quality = production_module.assess_rewrite(body, hard_limit=hard_limit)
        slop = anti_slop_issues(body)
        soft_issues = tuple(dict.fromkeys(tuple(quality.issues) + tuple(slop)))
        LOG.info(
            "RC40 stage article_id=%s stage=UA_SAFE provider=%s model=%s chars=%s score=%s soft_issues=%s",
            article_id, final_result.provider, final_result.model, len(body), quality.score, len(soft_issues),
        )

        if quality.score < 82 or slop:
            repair = _repair_prompt(ua_prompt, body, soft_issues, quality.score)
            try:
                repair_result = production_module.run_ai(
                    repair, validator=ua_hard_validator,
                    max_output_tokens=560, local_prompt=repair, local_max_output_tokens=560,
                    cloud_timeout_seconds=28, local_timeout_seconds=10, task_timeout_seconds=55,
                    local_repair=False, suppress_provider_on_quota=False,
                    allowed_providers={final_result.provider},
                )
                repaired_body = _validated_ua_body(
                    repair_result.text, article=article, allowed_years=allowed_years,
                    allowed_numbers=allowed_numbers, hard_limit=hard_limit,
                )
                repaired_quality = production_module.assess_rewrite(repaired_body, hard_limit=hard_limit)
                repaired_slop = anti_slop_issues(repaired_body)
                better = (repaired_quality.score, -len(repaired_slop)) > (quality.score, -len(slop))
                if better:
                    body = repaired_body
                    quality = repaired_quality
                    slop = repaired_slop
                    final_result = repair_result
                    LOG.info(
                        "RC40 stage article_id=%s stage=TARGETED_REPAIR_APPLIED score=%s soft_issues=%s",
                        article_id, quality.score, len(tuple(quality.issues) + tuple(slop)),
                    )
                else:
                    LOG.info(
                        "RC40 stage article_id=%s stage=TARGETED_REPAIR_KEPT_ORIGINAL old_score=%s new_score=%s",
                        article_id, quality.score, repaired_quality.score,
                    )
            except Exception as repair_exc:
                LOG.warning(
                    "RC40 stage article_id=%s stage=TARGETED_REPAIR_FAILED keep_original=1 error=%s",
                    article_id, repair_exc,
                )

        lt_result = production_module.apply_local_languagetool_detailed(
            body, timeout=1.8, max_changes=24, require_ready=False
        )
        polished = production_module.apply_safe_ukrainian_fixes(lt_result.text)
        if polished != body:
            try:
                polished_body = _validated_ua_body(
                    polished, article=article, allowed_years=allowed_years,
                    allowed_numbers=allowed_numbers, hard_limit=hard_limit,
                )
                body = polished_body
                quality = production_module.assess_rewrite(body, hard_limit=hard_limit)
                slop = anti_slop_issues(body)
            except Exception as exc:
                LOG.warning("RC40 stage article_id=%s stage=LANGUAGETOOL_REJECTED error=%s", article_id, exc)

        body = _validated_ua_body(
            body, article=article, allowed_years=allowed_years,
            allowed_numbers=allowed_numbers, hard_limit=hard_limit,
        )
        quality = production_module.assess_rewrite(body, hard_limit=hard_limit)
        slop = anti_slop_issues(body)

        title_key = " ".join(sorted(production_module._norm_words(_row_value(article, "title"))))[:430] or "news"
        event_marker = format_marker or f"{marker}{hard_limit}:"
        bridge_label = "bypass/source-only" if bridge_result is None or not russian_draft else f"{bridge_result.provider}/{bridge_result.model}"
        LOG.info(
            "RC40 publish-ready article_id=%s bridge=%s final=%s/%s chars=%s score=%s soft_slop=%s lt_changes=%s",
            article_id, bridge_label, final_result.provider, final_result.model,
            len(body), quality.score, len(slop), lt_result.changes,
        )
        return Decision(
            decision="publish", duplicate_of=None,
            reason=(
                f"RC40: bridge={bridge_label} → UA author {final_result.provider}/{final_result.model} → hard SOURCE Fact Guard PASS; "
                f"editorial quality {quality.score}/100; soft issues={len(tuple(quality.issues) + tuple(slop))}; "
                f"LanguageTool fixes={lt_result.changes}."
            ),
            event_key=(event_marker + title_key)[:500], event_summary=body[:1000],
            headline_uk=production_module.BODY_ONLY_SENTINEL,
            telegram_teaser=body, full_article_uk=body, media_captions_uk={},
            confidence=0.92, provider=final_result.provider, model=final_result.model,
        )

    production_module.decide = decide
    service_module.decide = decide
    LOG.info("RC40 policy installed: marker=%s", marker)
    _INSTALLED = True
