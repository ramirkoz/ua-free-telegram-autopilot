from __future__ import annotations

import logging

from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc36")
_INSTALLED = False


def install_rc36_policy() -> None:
    """RC36 editorial hardening without replacing the stable RC35 source layer."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import media_pipeline as media_module
    from . import production_pipeline as production_module
    from . import service as service_module

    marker = "telegram-post-v21:"
    production_module.POST_FORMAT_PREFIX = marker
    service_module.POST_FORMAT_PREFIX = marker

    # 1) Featured/OG media is not trusted merely because the publisher marked it
    # as featured. With media-required publication, no visual is safer than a
    # confident but unrelated visual.
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

    # 2) Strengthen the first writer contract before the final human copy-edit.
    original_build_prompt = production_module.build_rewrite_prompt

    def build_rewrite_prompt(*args, **kwargs):
        prompt = original_build_prompt(*args, **kwargs)
        return prompt + (
            "\n\nRC36 HUMAN NEWSROOM STYLE:\n"
            "- do not use the same four-paragraph template for every story; paragraph length and sentence count must follow the material;\n"
            "- do not explain obvious concepts merely to sound complete; explain only what a smart non-specialist needs here;\n"
            "- avoid formulaic transitions such as «це важливо, тому що», «окремо варто зазначити», «для користувачів це означає» unless the source relation genuinely requires them;\n"
            "- use concrete verbs, direct attribution and varied natural sentence rhythm; do not add a concluding paragraph that repeats the story."
        )

    production_module.build_rewrite_prompt = build_rewrite_prompt

    # 3) Media-required contract. The stable service chooses 900-char media mode
    # or 4096-char text mode before calling decide(). Reject the text mode before
    # any AI call. This also converts the old media-to-text QA fallback into SKIP.
    original_decide = production_module.decide

    def decide(channel, article, recent, *, hard_limit=production_module.MEDIA_POST_HARD_LIMIT, format_marker=None):
        if int(hard_limit) > int(production_module.MEDIA_POST_HARD_LIMIT):
            title = str(article["title"] or "") if article is not None else ""
            return Decision(
                decision="reject",
                duplicate_of=None,
                reason="SKIP_NO_MEDIA: не знайдено релевантного фото/відео; CTRL+UA не публікує текстові новини без медіа.",
                event_key="media-required",
                event_summary=title[:1000],
                headline_uk="",
                telegram_teaser="",
                full_article_uk="",
                media_captions_uk={},
                confidence=1.0,
                provider="local-rule",
                model="rc36-media-required",
            )

        decision_result = original_decide(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )
        if decision_result.decision != "publish" or not str(decision_result.telegram_teaser or "").strip():
            return decision_result

        accepted_body = str(decision_result.telegram_teaser).strip()
        allowed_years = production_module._allowed_output_years(article)
        allowed_numbers = production_module._source_numbers(article)
        source_prompt = original_build_prompt(channel, article, local=False, hard_limit=hard_limit)
        human_prompt = (
            source_prompt
            + "\n\nHUMAN STYLE PASS. Copy-edit the ACCEPTED DRAFT so it reads like a human Ukrainian tech-news editor, not a model summary. "
              "Keep the strongest verified fact first. Break predictable paragraph symmetry. Do not explain the obvious. "
              "Remove filler transitions and repeated conclusions. Use concrete verbs and natural Ukrainian syntax. "
              "Preserve attribution and uncertainty exactly. Do not add any fact, number, year, entity, cause, forecast or conclusion. "
              "Return ONLY the final body.\n\nACCEPTED DRAFT:\n"
            + accepted_body[: int(hard_limit)]
        )

        def human_validator(raw: str) -> dict[str, str]:
            checked = production_module.validate_rewrite(
                raw,
                allowed_years=allowed_years,
                allowed_numbers=allowed_numbers,
                hard_limit=hard_limit,
                enforce_readability=False,
            )
            candidate = production_module.apply_safe_ukrainian_fixes(checked["body"])
            candidate = production_module.remove_source_author_meta_sentences(candidate)
            candidate = production_module.remove_unattributed_editorial_sentences(candidate)
            if candidate != checked["body"]:
                checked = production_module.validate_rewrite(
                    candidate,
                    allowed_years=allowed_years,
                    allowed_numbers=allowed_numbers,
                    hard_limit=hard_limit,
                    enforce_readability=False,
                )
                candidate = checked["body"]
            production_module.validate_fact_guard(article, checked["post"])
            if not production_module.preserves_human_copyedit(accepted_body, candidate):
                raise production_module.ProductionPipelineError(
                    "Human style pass змінив зміст або додав нові сутності/числа."
                )
            language_blockers = production_module.final_language_blockers(candidate)
            if language_blockers or not production_module.looks_ukrainian(candidate):
                raise production_module.ProductionPipelineError(
                    "Human style український gate: " + "; ".join(language_blockers or ["текст не визначено як природну українську прозу"])
                )
            editorial_blockers = production_module.hard_editorial_blockers(candidate)
            if editorial_blockers:
                raise production_module.ProductionPipelineError(
                    "Human style editorial blocker: " + "; ".join(editorial_blockers)
                )
            quality = production_module.assess_rewrite(candidate, hard_limit=hard_limit)
            if not quality.publishable:
                raise production_module.ProductionPipelineError(
                    f"Human style quality {quality.score}/100: " + "; ".join(quality.issues[:5])
                )
            return {"body": candidate}

        try:
            human_result, humanized = production_module._route_with_post_qa(
                human_prompt,
                human_prompt,
                human_validator,
                max_output_tokens=380,
                local_max_output_tokens=380,
                cloud_timeout_seconds=18,
                local_timeout_seconds=8,
                task_timeout_seconds=45,
                allowed_providers={"codex", "gemini"},
                max_candidates=2,
            )
            human_body = str(humanized["body"] or "").strip()
        except (production_module.AIRouterError, production_module.PostAIQAExhausted) as exc:
            LOG.warning("Human style pass unavailable/rejected; keeping already-safe candidate: %s", exc)
            return decision_result

        if not human_body or human_body == accepted_body:
            return decision_result

        LOG.info(
            "Human style pass success provider=%s model=%s chars=%s",
            human_result.provider,
            human_result.model,
            len(human_body),
        )
        return Decision(
            decision="publish",
            duplicate_of=decision_result.duplicate_of,
            reason=decision_result.reason + " Human style pass: trusted copy-edit + full factual revalidation.",
            event_key=decision_result.event_key,
            event_summary=human_body[:1000],
            headline_uk=decision_result.headline_uk,
            telegram_teaser=human_body,
            full_article_uk=human_body,
            media_captions_uk=dict(decision_result.media_captions_uk or {}),
            confidence=decision_result.confidence,
            provider=human_result.provider,
            model=human_result.model,
        )

    production_module.decide = decide
    service_module.decide = decide

    # 4) Absolute no-text fallback. Normally decide() rejects text mode before
    # this point. These wrappers also stop Telegram media rejection from silently
    # turning into a text-only publication.
    original_photo = service_module.send_prepared_photo
    original_video = service_module.send_video_url

    def media_only_photo(*args, **kwargs):
        try:
            return original_photo(*args, **kwargs)
        except service_module.TelegramError as exc:
            if exc.media_rejected:
                raise service_module.TelegramError(
                    "SKIP_MEDIA_REJECTED: Telegram відхилив релевантне фото; текст без медіа не публікується.",
                    retryable=False,
                    media_rejected=False,
                ) from exc
            raise

    def media_only_video(*args, **kwargs):
        try:
            return original_video(*args, **kwargs)
        except service_module.TelegramError as exc:
            if exc.media_rejected:
                raise service_module.TelegramError(
                    "SKIP_MEDIA_REJECTED: Telegram відхилив релевантне відео; текст без медіа не публікується.",
                    retryable=False,
                    media_rejected=False,
                ) from exc
            raise

    def no_text_publish(*args, **kwargs):
        raise service_module.TelegramError(
            "SKIP_NO_MEDIA: text-only Telegram publication is disabled by RC36.",
            retryable=False,
            media_rejected=False,
        )

    service_module.send_prepared_photo = media_only_photo
    service_module.send_video_url = media_only_video
    service_module.send_text = no_text_publish

    _INSTALLED = True
