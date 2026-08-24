from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .models import Decision
from .rc37_style import interest_style_issues, preserves_story_reedit, style_prompt_examples

LOG = logging.getLogger("telegram_autopilot.rc37")
_INSTALLED = False


_HARD_LOW_VALUE_TITLE = (
    "accessor", "buying guide", "gift guide", "our picks", "best ", "best-", "review",
    "how to ", "how-to", "tips", "reasons", "fixes", "troubleshoot", "worth it",
    "should you", "what's the difference", "what is the difference", " vs ", "explained",
    "stop siri", "is it actually", "is .* actually", "poetry", "poem", "opinion", "roundup",
)

_SOFT_FORMAT_SIGNALS = (
    "conference recap", "conference highlights", "talks from", "videos from", "videos about",
    "weekly roundup", "week in review", "things you need to know", "software should work",
    "hot chips",
)

_STRONG_NEWS_SIGNALS = (
    "vulnerability", "cve-", "zero-day", "zero day", "breach", "ransomware", "malware", "hack",
    "actively exploited", "lawsuit", "sues", "court", "regulator", "ban", "investigation", "recall",
    "outage", "crash", "bug", "patch", "fixes a", "security update", "launches", "launched", "releases",
    "released", "unveils", "unveiled", "announces", "announced", "discovered", "discovery", "finds",
    "found", "study finds", "researchers", "scientists", "trial", "phase 3", "record", "first ",
    "raises", "raised", "funding", "acquires", "acquired", "acquisition", "delays", "delayed",
)

_TOPIC_GROUPS = (
    ("ai", (" ai ", "artificial intelligence", "chatgpt", "claude", "gemini", "llm", "agent")),
    ("software", ("windows", "linux", "macos", "software", "database", "developer", "github")),
    ("cyber", ("vulnerability", "cve-", "breach", "malware", "ransomware", "security")),
    ("chips", ("gpu", "cpu", "hbm", "chip", "semiconductor", "memory", "transistor")),
    ("space", ("nasa", "space", "moon", "galaxy", "astronom", "telescope", "orbit")),
    ("science", ("study", "research", "scientist", "physics", "biology", "medical", "medicine")),
    ("industry", ("robot", "factory", "data center", "datacenter", "battery", "energy", "grid")),
)


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        return default
    return default if value is None else str(value)


def _topic_set(text: str) -> set[str]:
    low = f" {str(text or '').casefold()} "
    return {name for name, terms in _TOPIC_GROUPS if any(term in low for term in terms)}


def newsworthiness_reject_reason(article: Mapping[str, Any] | Any) -> str:
    title = " ".join(_row_value(article, "title").split())
    raw = " ".join(_row_value(article, "raw_text")[:9000].split())
    low_title = f" {title.casefold()} "
    low_all = f" {title}\n{raw} ".casefold()
    strong = any(signal in low_title for signal in _STRONG_NEWS_SIGNALS)

    # Guides, explainers, shopping/service pieces and soft editorial formats are
    # useful on their original sites but are not automatic-news slots for CTRL+UA.
    for signal in _HARD_LOW_VALUE_TITLE:
        if signal.startswith("is .*"):
            if re.search(r"\bis\b.+\bactually\b", low_title) and not strong:
                return "NEWSWORTHINESS_SKIP: пояснювальний/сервісний матеріал без достатньої нової події."
            continue
        if signal in low_title and not strong:
            return "NEWSWORTHINESS_SKIP: гайд, добірка, огляд або пояснювач без достатньої нової події."

    if any(signal in low_title for signal in _SOFT_FORMAT_SIGNALS) and not strong:
        return "NEWSWORTHINESS_SKIP: конференційний/колонковий/добірковий матеріал, а не самостійна новина."

    # Pure shopping ecosystems are especially noisy in tech feeds.
    if any(word in low_title for word in ("kindle", "charger", "case", "dock", "power bank")) and any(
        word in low_title for word in ("accessor", "best", "our picks", "guide")
    ):
        return "NEWSWORTHINESS_SKIP: купівельна добірка/аксесуари не займають автоматичний слот новин."

    # Catch editorial mashups: two independent topical clauses glued together by
    # 'as/while/meanwhile' with no concrete event. This is the exact shape that
    # produced the AI-hardware + Windows taskbar collage in live output.
    if not strong:
        parts = re.split(r"\s+(?:as|while|meanwhile)\s+|\s+[—–]\s+", low_title, maxsplit=1)
        if len(parts) == 2:
            left, right = _topic_set(parts[0]), _topic_set(parts[1])
            if left and right and not (left & right):
                return "NEWSWORTHINESS_SKIP: заголовок змішує дві незалежні теми без однієї чіткої новинної події."

    return ""


def _adaptive_source_backoff_seconds(health: Mapping[str, Any]) -> int:
    error = str(health.get("last_error") or "").casefold()
    if not error:
        return 0
    total_errors = max(1, int(health.get("total_errors") or 1))
    # Chronic failures grow the pause, but a successful check clears last_error
    # and immediately returns the source to the normal schedule.
    factor = min(8, 1 + total_errors // 3)
    if "http 429" in error:
        return min(6 * 3600, 30 * 60 * factor)
    if "http 403" in error:
        return min(6 * 3600, 20 * 60 * factor)
    if "text/html" in error or "unexpected content type" in error or "expected" in error and "feed" in error:
        return min(24 * 3600, 2 * 3600 * factor)
    if "network request failed" in error or "no dns result" in error or "timed out" in error or "timeout" in error:
        return min(90 * 60, 8 * 60 * factor)
    return 0


def install_rc37_policy() -> None:
    """RC37: newsroom-quality gate + trusted production routing + source backoff."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import media_pipeline as media_module
    from . import production_pipeline as production_module
    from . import service as service_module

    marker = "telegram-post-v22:"
    production_module.POST_FORMAT_PREFIX = marker
    service_module.POST_FORMAT_PREFIX = marker

    # 1) Keep RC36's strict media semantics. Featured/OG metadata alone is not
    # enough; an image without story-specific semantic evidence is rejected.
    original_semantic_match = media_module._semantic_media_match

    def semantic_media_match(item, *, title: str, article_text: str) -> bool:
        if bool(getattr(item, "featured", False)):
            _title_overlap, _article_overlap, token_count = media_module._semantic_media_evidence(
                item, title=title, article_text=article_text
            )
            if token_count == 0:
                return False
        return original_semantic_match(item, title=title, article_text=article_text)

    media_module._semantic_media_match = semantic_media_match

    # 2) Production AI is deliberately small: Codex first, Gemini second. The
    # other provider integrations stay available in Diagnostics/LAB, but an
    # unattended writer has no reason to spend a minute walking through providers
    # whose drafts still require Codex/Gemini before publication anyway.
    original_route = production_module._route_with_post_qa

    def trusted_route(*args, allowed_providers=None, **kwargs):
        if allowed_providers is None:
            allowed_providers = {"codex", "gemini"}
        return original_route(*args, allowed_providers=allowed_providers, **kwargs)

    production_module._route_with_post_qa = trusted_route

    # 3) Teach the FIRST writer the desired house style, with topic-near synthetic
    # examples. Facts from examples are explicitly quarantined from current-story
    # evidence and Fact Guard remains authoritative.
    original_build_prompt = production_module.build_rewrite_prompt

    def build_rewrite_prompt(channel, article, *, local=False, hard_limit=production_module.MEDIA_POST_HARD_LIMIT):
        prompt = original_build_prompt(channel, article, local=local, hard_limit=hard_limit)
        examples = style_prompt_examples(article, limit=2)
        return prompt + (
            "\n\nRC37 CTRL+UA NEWSROOM CONTRACT:\n"
            "Do NOT retell the article. Find the story inside it. The first sentence must give the reader a reason to read the second.\n"
            "Start with the strongest verified surprise, consequence, conflict, number, human detail or concrete change. "
            "Do not start with 'the company announced', 'researchers found', 'Microsoft confirmed' or similar institutional scaffolding when a stronger fact exists.\n"
            "Use only 3-6 memorable details from SOURCE. Throw away the rest. Smart readers already know what Windows, AI, GPU, NASA, Telegram and smartphones are; explain only genuinely necessary specialist terms.\n"
            "Vary structure between stories. Two paragraphs are fine. One short standalone sentence is fine. A compact list is fine when the facts naturally form a list. Never force four equal paragraphs.\n"
            "A light human turn of phrase or restrained irony is allowed when SOURCE supports the underlying fact, but never invent a claim, emotion, motive, analogy presented as fact, or clickbait superlative.\n"
            "End on the last useful fact or consequence. No moral, no recap, no 'this demonstrates', no 'for a broad audience this matters'.\n"
            "Before answering, silently ask: would a human editor say every sentence out loud to a smart friend? If not, rewrite it.\n\n"
            + examples
        )

    production_module.build_rewrite_prompt = build_rewrite_prompt

    # 4) Strict newsworthiness + media-required gate, then one mandatory final
    # human editor pass. A style-provider outage becomes a normal retry instead of
    # publishing the already-safe but boring draft.
    original_decide = production_module.decide

    def decide(channel, article, recent, *, hard_limit=production_module.MEDIA_POST_HARD_LIMIT, format_marker=None):
        if int(hard_limit) > int(production_module.MEDIA_POST_HARD_LIMIT):
            title = _row_value(article, "title")
            return Decision(
                decision="reject", duplicate_of=None,
                reason="SKIP_NO_MEDIA: не знайдено релевантного фото/відео; CTRL+UA не публікує текстові новини без медіа.",
                event_key="media-required", event_summary=title[:1000], headline_uk="", telegram_teaser="",
                full_article_uk="", media_captions_uk={}, confidence=1.0,
                provider="local-rule", model="rc37-media-required",
            )

        reason = newsworthiness_reject_reason(article)
        if reason:
            return Decision(
                decision="reject", duplicate_of=None, reason=reason,
                event_key="ctrl-ua-newsworthiness-v2", event_summary=_row_value(article, "title")[:1000],
                headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                confidence=0.99, provider="local-rule", model="newsworthiness-v2",
            )

        decision_result = original_decide(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )
        if decision_result.decision != "publish" or not str(decision_result.telegram_teaser or "").strip():
            return decision_result

        accepted_body = str(decision_result.telegram_teaser).strip()
        allowed_years = production_module._allowed_output_years(article)
        allowed_numbers = production_module._source_numbers(article)
        source_prompt = build_rewrite_prompt(channel, article, local=False, hard_limit=hard_limit)
        examples = style_prompt_examples(article, limit=2)
        human_prompt = (
            source_prompt
            + "\n\nFINAL HUMAN EDITOR — MANDATORY. The draft below is fact-checked but may be dull. "
              "Do not merely polish grammar. Re-edit it as a sharp Ukrainian Telegram editor. Find the strongest factual hook and lead with it. "
              "Compress to the 3-6 details a reader will remember. Break predictable paragraph symmetry. Remove explanations of obvious things, filler transitions and recap endings. "
              "Use concrete verbs and natural spoken-news rhythm. A restrained witty formulation is allowed only if it does not add a factual claim. "
              "Do not add any fact, number, year, entity, cause, motive, forecast or conclusion. Preserve attribution and uncertainty exactly. "
              "Return ONLY the final body.\n\n"
            + examples
            + "\n\nFACT-CHECKED DRAFT TO RE-EDIT:\n"
            + accepted_body[: int(hard_limit)]
        )

        def human_validator(raw: str) -> dict[str, str]:
            checked = production_module.validate_rewrite(
                raw, allowed_years=allowed_years, allowed_numbers=allowed_numbers,
                hard_limit=hard_limit, enforce_readability=False,
            )
            candidate = production_module.apply_safe_ukrainian_fixes(checked["body"])
            candidate = production_module.remove_source_author_meta_sentences(candidate)
            candidate = production_module.remove_unattributed_editorial_sentences(candidate)
            if candidate != checked["body"]:
                checked = production_module.validate_rewrite(
                    candidate, allowed_years=allowed_years, allowed_numbers=allowed_numbers,
                    hard_limit=hard_limit, enforce_readability=False,
                )
                candidate = checked["body"]
            production_module.validate_fact_guard(article, checked["post"])
            if not preserves_story_reedit(accepted_body, candidate):
                raise production_module.ProductionPipelineError(
                    "Human editor змінив зміст або додав нові сутності/числа."
                )
            language_blockers = production_module.final_language_blockers(candidate)
            if language_blockers or not production_module.looks_ukrainian(candidate):
                raise production_module.ProductionPipelineError(
                    "Human editor UA gate: " + "; ".join(language_blockers or ["текст не визначено як природну українську прозу"])
                )
            editorial_blockers = production_module.hard_editorial_blockers(candidate)
            if editorial_blockers:
                raise production_module.ProductionPipelineError(
                    "Human editor editorial blocker: " + "; ".join(editorial_blockers)
                )
            quality = production_module.assess_rewrite(candidate, hard_limit=hard_limit)
            if not quality.publishable:
                raise production_module.ProductionPipelineError(
                    f"Human editor quality {quality.score}/100: " + "; ".join(quality.issues[:5])
                )
            style_issues = interest_style_issues(candidate)
            if style_issues:
                raise production_module.ProductionPipelineError(
                    "Human-interest style gate: " + "; ".join(style_issues)
                )
            return {"body": candidate}

        try:
            human_result, humanized = production_module._route_with_post_qa(
                human_prompt, human_prompt, human_validator,
                max_output_tokens=420, local_max_output_tokens=420,
                cloud_timeout_seconds=35, local_timeout_seconds=8,
                task_timeout_seconds=80, allowed_providers={"codex", "gemini"}, max_candidates=3,
            )
        except (production_module.AIRouterError, production_module.PostAIQAExhausted) as exc:
            LOG.warning("Mandatory human editor unavailable/rejected; story will retry: %s", exc)
            if isinstance(exc, production_module.PostAIQAExhausted):
                raise
            raise production_module.PostAIQAExhausted(
                "Mandatory human editor (Codex/Gemini) не сформував живий безпечний фінальний текст. " + str(exc),
                (str(exc),), provider_outage=True,
            ) from exc

        human_body = str(humanized["body"] or "").strip()
        LOG.info(
            "RC37 mandatory human editor success provider=%s model=%s chars=%s",
            human_result.provider, human_result.model, len(human_body),
        )
        return Decision(
            decision="publish", duplicate_of=decision_result.duplicate_of,
            reason=decision_result.reason + " RC37: mandatory human-interest edit + full factual revalidation.",
            event_key=decision_result.event_key, event_summary=human_body[:1000],
            headline_uk=decision_result.headline_uk, telegram_teaser=human_body, full_article_uk=human_body,
            media_captions_uk=dict(decision_result.media_captions_uk or {}), confidence=decision_result.confidence,
            provider=human_result.provider, model=human_result.model,
        )

    production_module.decide = decide
    service_module.decide = decide

    # 5) Preserve media-only delivery. Telegram rejecting the media must not turn
    # the story into a naked text post.
    original_photo = service_module.send_prepared_photo
    original_video = service_module.send_video_url

    def media_only_photo(*args, **kwargs):
        try:
            return original_photo(*args, **kwargs)
        except service_module.TelegramError as exc:
            if exc.media_rejected:
                raise service_module.TelegramError(
                    "SKIP_MEDIA_REJECTED: Telegram відхилив релевантне фото; текст без медіа не публікується.",
                    retryable=False, media_rejected=False,
                ) from exc
            raise

    def media_only_video(*args, **kwargs):
        try:
            return original_video(*args, **kwargs)
        except service_module.TelegramError as exc:
            if exc.media_rejected:
                raise service_module.TelegramError(
                    "SKIP_MEDIA_REJECTED: Telegram відхилив релевантне відео; текст без медіа не публікується.",
                    retryable=False, media_rejected=False,
                ) from exc
            raise

    def no_text_publish(*args, **kwargs):
        raise service_module.TelegramError(
            "SKIP_NO_MEDIA: text-only Telegram publication is disabled by RC37.",
            retryable=False, media_rejected=False,
        )

    service_module.send_prepared_photo = media_only_photo
    service_module.send_video_url = media_only_video
    service_module.send_text = no_text_publish

    # 6) Long adaptive backoff for chronically broken feeds. Manual Run Once still
    # bypasses it intentionally; normal autopilot collection does not hammer 429s
    # or HTML pages pretending to be feeds every few minutes.
    def source_backoff_remaining(self, source_id: int) -> int:
        try:
            health = self.db.source_health(source_id)
            window = _adaptive_source_backoff_seconds(health)
            stamp = str(health.get("last_error_at") or "")
            if not window or not stamp:
                return 0
            failed_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if failed_at.tzinfo is None:
                failed_at = failed_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - failed_at.astimezone(timezone.utc)).total_seconds()
            return max(0, int(window - age))
        except Exception:
            return 0

    service_module.AutopilotService._source_backoff_remaining = source_backoff_remaining

    _INSTALLED = True
