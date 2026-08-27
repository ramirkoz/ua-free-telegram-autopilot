from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from .ai_router import AIRouterError, run_ai
from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc47")
_INSTALLED = False
_UNCLASSIFIED = "__UNCLASSIFIED__"
_OTHER = "__OTHER__"
_CHEAP_CLASSIFIER = None
_RC46_BALANCE = None


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else str(value)


def _trusted_category_prompt(channel: Any, article: Any, categories: list[dict[str, Any]]) -> str:
    names = "\n".join(f"- {item['name']}" for item in categories)
    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:2400]
    return f"""You are the FINAL assignment editor for one Telegram channel.
Decide whether ONE source item genuinely belongs in this channel, then assign ONE operator-defined category.
The source may be English, Ukrainian or Russian. Category labels are semantic, not literal keyword requirements.

QUALITY-FIRST RULES:
- The CHANNEL PROFILE is a publication contract, not a hint.
- Do not force a story into the nearest category merely because a keyword overlaps.
- A story must contain a real event, result, discovery, release, incident, policy change or other concrete development that this channel would actually publish.
- Reject generic politics, healthcare policy, finance, corporate housekeeping, opinion columns, evergreen explainers, reviews/listicles and adjacent-domain stories unless the profile explicitly asks for them.
- If no category genuinely fits BOTH the story and the profile, return __OTHER__.
- Return only one configured category name or __OTHER__. JSON {{"category":"..."}} is accepted.

CHANNEL PROFILE:
{profile or '(not specified)'}

CATEGORIES:
{names}

SOURCE TITLE:
{_row_value(article, 'title')[:900]}

SOURCE EXCERPT:
{_row_value(article, 'raw_text')[:5200]}
""".strip()


def classify_category_rc47(channel: Any, article: Any, categories: list[dict[str, Any]]) -> str:
    """RC47: cheap RC46 first, then trusted fail-closed retry."""
    if not categories:
        return ""

    from . import rc45_policy as rc45
    from . import rc46_policy as rc46

    cheap_classifier = _CHEAP_CLASSIFIER or rc46.classify_category_rc46
    lexical = rc45.lexical_category(article, categories)
    category = cheap_classifier(channel, article, categories)
    # RC46's semantic cloud classifier is profile-aware. Its lexical shortcut is
    # intentionally cheap and is not. RC47 therefore asks the trusted assignment
    # editor to confirm lexical matches as well as infrastructure failures.
    if category != _UNCLASSIFIED and not lexical:
        return category
    if category == _OTHER:
        return category

    prompt = _trusted_category_prompt(channel, article, categories)

    def validator(value: str) -> None:
        rc46.extract_category_rc46(value, categories)

    try:
        result = run_ai(
            prompt,
            validator=validator,
            max_output_tokens=80,
            cloud_timeout_seconds=22,
            task_timeout_seconds=38,
            local_repair=False,
            skip_providers={"local"},
            suppress_provider_on_quota=False,
            allowed_providers={"codex", "gemini"},
        )
        category = rc46.extract_category_rc46(result.text, categories)
        LOG.info(
            "RC47 editorial gate article_id=%s category=%s decision=trusted-classified provider=%s model=%s",
            _row_value(article, "id", "?"), category, result.provider, result.model,
        )
        return category
    except Exception as exc:
        LOG.warning(
            "RC47 editorial gate article_id=%s decision=hold-for-retry reason=classifier-unavailable error=%s",
            _row_value(article, "id", "?"), str(exc)[:900],
        )
        raise AIRouterError(
            "RC47 editorial classifier unavailable after trusted fallback; article held for retry. "
            + str(exc)[:1200]
        ) from exc


def balance_reject_reason_rc47(channel: Any, article: Any, recent, *, category: str | None = None):
    from . import rc46_policy as rc46

    value = str(category or "").strip()
    if value == _UNCLASSIFIED:
        raise AIRouterError("RC47 refuses unclassified editorial pass; article held for retry.")
    balance = _RC46_BALANCE or rc46.balance_reject_reason_rc46
    return balance(channel, article, recent, category=value or None)


_RU_EDITOR_ADDENDUM = """RC47 QUALITY-FIRST EDITOR OVERRIDE.
Your job is not to summarize the source. Your job is to decide what ONE concrete story a human editor would actually tell.
- The draft must be self-contained: a reader should understand the central event without clicking the source.
- If the central claim is that there is a loophole, vulnerability, restriction, exception, problem or new mechanism, state WHAT it actually is. Never tease a missing payload with phrases like 'there is a loophole' and then withhold the loophole.
- Do not describe the source/article/column itself. Never write 'the article says', 'the outlet presents this as', 'the author argues' unless the author is part of the news event.
- Prefer 2-5 decisive facts. Do not dump every quarterly number, specification or named subsystem merely because it is available.
- For corporate announcements, identify the concrete change and scale; do not reproduce PR framing.
- For technical stories, explain or omit jargon that a smart non-specialist does not need. Acronym density is not expertise.
- If the source is too thin or off-profile to make a useful self-contained story, do not manufacture an angle.
"""

_UA_EDITOR_ADDENDUM = """RC47 FINAL NEWSROOM OVERRIDE.
Це має бути готовий пост, який редактор без сорому залишив би в стрічці, а не анонс чужої статті.
- Текст повинен бути САМОДОСТАТНІМ: читач має зрозуміти головну подію без переходу за посиланням.
- Якщо пишеш, що «є лазівка», «є проблема», «є виняток», «є новий механізм», «є вразливість» або «змінили правила», ОБОВ'ЯЗКОВО конкретно поясни, у чому саме це полягає. Не приховуй головну суть за тизером.
- Не описуй сам матеріал чи видання: без «стаття подає», «авторська колонка», «видання пише як...», якщо автор не є учасником події.
- Вибери 2-5 фактів, які тримають історію. Не перетворюй пост на квартальний звіт, список характеристик або перелік усіх чисел зі SOURCE.
- Технічні абревіатури й жаргон або коротко поясни нормальною українською, або прибери, якщо без них суть не втрачається.
- Для корпоративного анонсу розкажи, ЩО реально змінилося і який масштаб, а не переписуй пресреліз.
- Перше речення мусить бути повним і граматично нормальним. Перед відповіддю перечитай кожне речення на природність української; дивні кальки й випадкові слова неприпустимі.
- Не роби пост «цікавим» порожніми метафорами. Конкретний факт сильніший за декоративну фразу.
"""


def _final_editor_prompt(channel: Any, article: Any, draft: str, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack

    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1800]
    pack = build_evidence_pack(article, char_budget=5200).text
    return f"""Ти фінальний випусковий редактор українського Telegram-каналу.
SOURCE EVIDENCE PACK є ЄДИНИМ джерелом фактів. DRAFT — лише попередній варіант і НЕ є джерелом фактів.

Завдання: випусти один самодостатній, природний український пост. Не просто виправляй слова: якщо DRAFT вибрав слабкий кут, перебудуй текст із SOURCE навколо сильнішої конкретної події. Якщо DRAFT нормальний, зроби лише потрібну редактуру.

ЖОРСТКІ ПРАВИЛА:
- одна головна історія;
- читач повинен зрозуміти, що саме сталося, без кліку на джерело;
- якщо згадана лазівка/вразливість/зміна/виняток/механізм, поясни саму суть, а не тільки факт її існування;
- 2-5 вирішальних фактів за замовчуванням; не вивантажуй усі цифри й характеристики;
- прибери мета-фрази про статтю, автора чи видання;
- прибери або коротко поясни непотрібний жаргон;
- природна сучасна українська без кальок, дивних словосполучень і канцеляриту;
- без заголовка, URL, джерела, хештегів, емодзі та коментарів;
- не додавати жодного факту, числа, дати, причини, оцінки чи висновку поза SOURCE;
- завершити повним реченням;
- жорсткий ліміт {hard_limit} символів.

ПРОФІЛЬ КАНАЛУ:
{profile or '(not specified)'}

SOURCE TITLE:
{_row_value(article, 'title')[:320]}

SOURCE EVIDENCE PACK:
{pack}

DRAFT (NOT EVIDENCE):
{str(draft or '')[:2600]}

Поверни ТІЛЬКИ фінальний український текст.""".strip()


def _deterministic_editorial_blockers(body: str) -> tuple[str, ...]:
    text = str(body or "").strip()
    issues: list[str] = []
    if not text:
        return ("порожній фінальний текст",)

    alpha = re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", text)
    if alpha and alpha.group(0).islower():
        issues.append("перше речення починається з малої літери або обрізаного слова")

    low = " ".join(text.casefold().split())
    source_meta = (
        "автор матеріалу", "авторськ", "стаття подає", "матеріал подає",
        "видання подає", "подає це як", "у статті йдеться", "ця стаття", "цей матеріал",
    )
    if any(token in low for token in source_meta):
        issues.append("текст описує статтю/видання замість самої події")

    teaser_signals = (
        "є лазівка", "є нюанс", "є одна проблема", "деталь у правилах",
        "але є лазівка", "але є нюанс",
    )
    if any(token in low for token in teaser_signals):
        issues.append("пост використовує тизер замість прямого пояснення головної суті")

    if "у новій хваті" in low:
        issues.append("неприродна або пошкоджена українська фраза «у новій хваті»")

    number_tokens = re.findall(r"(?<!\w)\d+(?:[ \u00a0\u202f,.]\d+)*(?:\s?%)?", text)
    if len(number_tokens) >= 7:
        issues.append("пост перевантажений числами замість редакторського відбору фактів")

    return tuple(dict.fromkeys(issues))


def _trusted_final_edit(channel: Any, article: Any, draft: str, *, hard_limit: int):
    from . import production_pipeline as production
    from . import rc40_policy as rc40

    prompt = _final_editor_prompt(channel, article, draft, hard_limit=hard_limit)
    allowed_years = rc40._rc40_allowed_years(article)
    allowed_numbers = rc40._rc40_allowed_numbers(article)

    def validator(raw: str) -> None:
        body = rc40._validated_ua_body(
            raw,
            article=article,
            allowed_years=allowed_years,
            allowed_numbers=allowed_numbers,
            hard_limit=hard_limit,
        )
        blockers = _deterministic_editorial_blockers(body)
        if blockers:
            raise production.ProductionPipelineError("RC47 final editor: " + "; ".join(blockers))

    try:
        result = run_ai(
            prompt,
            validator=validator,
            max_output_tokens=620,
            cloud_timeout_seconds=34,
            task_timeout_seconds=75,
            local_repair=False,
            skip_providers={"local"},
            suppress_provider_on_quota=False,
            allowed_providers={"codex", "gemini"},
        )
        body = rc40._validated_ua_body(
            result.text,
            article=article,
            allowed_years=allowed_years,
            allowed_numbers=allowed_numbers,
            hard_limit=hard_limit,
        )
        blockers = _deterministic_editorial_blockers(body)
        if blockers:
            raise production.ProductionPipelineError("RC47 final editor: " + "; ".join(blockers))
        return result, body
    except Exception as exc:
        raise production.PostAIQAExhausted(
            "RC47 final newsroom gate did not produce a publishable self-contained post: " + str(exc)[:1500],
            (str(exc),),
            provider_outage="Немає доступного AI-провайдера" in str(exc),
        ) from exc


def install_rc47_policy() -> None:
    global _INSTALLED, _CHEAP_CLASSIFIER, _RC46_BALANCE
    if _INSTALLED:
        return

    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc42_policy as rc42
    from . import rc45_policy as rc45
    from . import rc46_policy as rc46
    from . import service as service

    _CHEAP_CLASSIFIER = rc46.classify_category_rc46
    _RC46_BALANCE = rc46.balance_reject_reason_rc46

    rc46.classify_category_rc46 = classify_category_rc47
    rc46.balance_reject_reason_rc46 = balance_reject_reason_rc47
    rc45.classify_category_rc45 = classify_category_rc47
    rc45.balance_reject_reason_rc45 = balance_reject_reason_rc47
    rc42.classify_category = classify_category_rc47
    rc42.balance_reject_reason = balance_reject_reason_rc47

    old_ru_prompt = rc40.build_russian_editorial_prompt
    old_ua_prompt = rc40.build_ukrainian_bridge_prompt

    def build_ru_rc47(channel, article, *, hard_limit: int):
        return _RU_EDITOR_ADDENDUM + "\n\n" + old_ru_prompt(channel, article, hard_limit=hard_limit)

    def build_ua_rc47(channel, article, russian_draft: str, *, hard_limit: int):
        return _UA_EDITOR_ADDENDUM + "\n\n" + old_ua_prompt(
            channel, article, russian_draft, hard_limit=hard_limit
        )

    rc40.build_russian_editorial_prompt = build_ru_rc47
    rc40.build_ukrainian_bridge_prompt = build_ua_rc47

    old_production_run_ai = production.run_ai

    def production_run_ai_rc47(prompt, *args, **kwargs):
        prompt_text = str(prompt or "")
        if prompt_text.startswith("RC47 QUALITY-FIRST EDITOR OVERRIDE."):
            allowed = kwargs.get("allowed_providers")
            if allowed is not None:
                allowed = set(allowed)
                allowed.discard("local")
                kwargs["allowed_providers"] = allowed
            skipped = set(kwargs.get("skip_providers") or set())
            skipped.add("local")
            kwargs["skip_providers"] = skipped
            kwargs["local_timeout_seconds"] = min(int(kwargs.get("local_timeout_seconds", 8) or 8), 8)
        if "RC40 NOTE: внутрішній RU bridge цього разу недоступний" in prompt_text:
            raise AIRouterError("RC47 source-only rewrite disabled; RU editorial bridge must succeed before publication.")
        return old_production_run_ai(prompt, *args, **kwargs)

    production.run_ai = production_run_ai_rc47
    original_decide = production.decide

    def decide_rc47(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        result: Decision = original_decide(
            channel, article, recent, hard_limit=hard_limit, format_marker=format_marker
        )
        if result.decision != "publish":
            return result

        if rc45.content_direction(channel) != rc45.DIRECTION_EN_TO_UK:
            return result

        if "bridge=bypass/source-only" in str(result.reason or ""):
            raise production.PostAIQAExhausted(
                "RC47: RU editorial bridge was unavailable; source-only publication is disabled. Article held for retry.",
                (str(result.reason or ""),),
                provider_outage=False,
            )

        draft = str(result.telegram_teaser or result.full_article_uk or "").strip()
        final_result, body = _trusted_final_edit(
            channel, article, draft, hard_limit=int(hard_limit)
        )

        blockers = _deterministic_editorial_blockers(body)
        if blockers:
            raise production.PostAIQAExhausted(
                "RC47 final newsroom blockers: " + "; ".join(blockers),
                blockers,
            )

        LOG.info(
            "RC47 publish-ready article_id=%s final_editor=%s/%s chars=%s",
            _row_value(article, "id", "?"), final_result.provider, final_result.model, len(body),
        )
        return Decision(
            decision="publish",
            duplicate_of=None,
            reason=(
                str(result.reason or "")
                + f" RC47 final newsroom pass={final_result.provider}/{final_result.model}; self-contained editorial gate PASS."
            ).strip(),
            event_key=str(result.event_key or ""),
            event_summary=body[:1000],
            headline_uk=result.headline_uk,
            telegram_teaser=body,
            full_article_uk=body,
            media_captions_uk=result.media_captions_uk,
            confidence=max(float(result.confidence or 0), 0.92),
            provider=final_result.provider,
            model=final_result.model,
        )

    production.decide = decide_rc47
    service.decide = decide_rc47
    production.POST_FORMAT_PREFIX = "telegram-post-v29:"
    service.POST_FORMAT_PREFIX = "telegram-post-v29:"
    _INSTALLED = True
