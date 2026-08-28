from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any, Mapping

from .ai_router import AIRouterError
from .models import Decision

LOG = logging.getLogger("telegram_autopilot.rc49")
_INSTALLED = False


def _row_value(row: Mapping[str, Any] | Any, key: str, default: str = "") -> str:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else str(value)


def _channel_key(channel: Any) -> str:
    return re.sub(r"\s+", "", str(getattr(channel, "name", "") or "").casefold())


def is_ctrl_ua(channel: Any) -> bool:
    return _channel_key(channel) in {"ctrl+ua", "ctrlua"}


def ctrl_ua_niche_reject_reason(article: Mapping[str, Any] | Any) -> str:
    """Reject the exact narrow enthusiast-computing class confirmed by live review.

    This is deliberately about audience breadth, not a generic ban on old hardware,
    Raspberry Pi or programming languages.  Broader security, platform, scientific
    or industry stories continue through the normal assignment editor.
    """
    title = _row_value(article, "title")
    raw = _row_value(article, "raw_text")[:7000]
    text = f" {title}\n{raw} ".casefold()

    narrow_signals = (
        "thoreau basic",
        "boot to basic",
        "boot-to-basic",
        "boots to basic",
        "gw-basic",
        "amigaos",
        "amiberry",
        " aros ",
        "thea1200",
        "amiga gets a new life",
        "amiga отримує нове життя",
        "retro computing",
        "retro-computing",
    )
    if any(signal in text for signal in narrow_signals):
        return (
            "EDITORIAL_BREADTH_RC49_SKIP: вузький hobby/retro-computing матеріал для ентузіастів; "
            "для CTRL+UA потрібен ширший технологічний, безпековий, науковий або ринковий наслідок."
        )
    return ""


def _human_readability_issues(text: str) -> tuple[str, ...]:
    """Hard-only read-aloud blockers.  This is not a style score.

    RC49 intentionally avoids another generative 'humanizer'.  These checks only
    stop prose that is structurally difficult to read and let the next retry ask
    the single UA author to write a fresh version.
    """
    value = " ".join(str(text or "").split())
    if not value:
        return ("порожній текст",)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]
    word_counts = [len(re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9'’.-]+", sentence)) for sentence in sentences]
    issues: list[str] = []

    if word_counts and max(word_counts) > 50:
        issues.append("є речення довше 50 слів; його важко прочитати з першого разу")
    if len(word_counts) >= 3 and sum(word_counts) / len(word_counts) > 31:
        issues.append("середня довжина речень зависока для живого Telegram-тексту")

    overloaded = 0
    numeric_heavy = 0
    for sentence, words in zip(sentences, word_counts):
        if words >= 28 and sentence.count(",") >= 4:
            overloaded += 1
        if words >= 22 and len(re.findall(r"(?<!\w)\d", sentence)) >= 3:
            numeric_heavy += 1
    if overloaded >= 2:
        issues.append("кілька речень перевантажені підрядними конструкціями та комами")
    if numeric_heavy >= 2:
        issues.append("текст читається як каталог характеристик або звіт, а не як історія")

    return tuple(dict.fromkeys(issues))


def _build_ru_story_editor_prompt(channel: Any, article: Any, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack

    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1200]
    source = build_evidence_pack(article, char_budget=5200).text
    return f"""Ты выпускающий редактор Telegram-канала. Это НЕ текст для публикации и не перевод статьи.

Твоя единственная задача — выбрать ОДНУ историю внутри SOURCE и подготовить короткий редакторский план для украинского автора.
Напиши естественным русским 350–900 знаков: что здесь главное, какие 2–4 факта действительно держат историю и что можно безболезненно выбросить.

Не украшай текст, не делай выводов и не сочиняй 'интересный хук'. Не перечисляй характеристики ради полноты. Если сильная деталь одна — не раздувай материал.
Используй только SOURCE. Сохрани числа, неопределённость, атрибуцию и причинность точно. Не добавляй мотивы, оценки, прогнозы или факты.

Профиль канала: {profile or '(не задан)'}
SOURCE TITLE: {_row_value(article, 'title')[:320]}
SOURCE EVIDENCE PACK:
{source}

Верни ТОЛЬКО редакторский план на русском, без заголовков и комментариев.""".strip()


def _build_ua_human_writer_prompt(channel: Any, article: Any, russian_draft: str, *, hard_limit: int) -> str:
    from .evidence_pack import build_evidence_pack
    from . import rc48_learning as rc48

    profile = " ".join(str(getattr(channel, "editorial_profile", "") or "").split())[:1400]
    source = build_evidence_pack(article, char_budget=5600).text
    try:
        memory = rc48._format_memory_block(channel, article, purpose="writing")
    except Exception:
        memory = ""

    memory_block = ("\n\nРЕДАКЦІЙНА ПАМ'ЯТЬ ЦЬОГО КАНАЛУ:\n" + memory) if memory else ""
    return f"""Ти автор українського Telegram-каналу. Напиши фінальний пост З НУЛЯ.

SOURCE EVIDENCE PACK — єдине джерело фактів.
RUSSIAN EDITORIAL PLAN — лише підказка, яку історію побачив попередній редактор. Не перекладай його і не наслідуй його синтаксис.

Головна вимога — текст має легко читатися людиною вголос.
- одне речення зазвичай несе одну основну думку;
- чергуй короткі й довші речення природно, не складай кілька підрядних конструкцій в один вагон;
- не перетворюй новину на каталог характеристик, квартальний звіт або перелік усіх цифр зі SOURCE;
- залиш тільки деталі, без яких історія стане слабшою або незрозумілою;
- не пояснюй очевидні для розумного читача речі;
- починай з того місця, з якого цю історію природно почала б людина. Сильний факт часто добрий початок, але штучний 'хук' не потрібен;
- абзаци можуть бути різними за довжиною. Два абзаци нормально. Три теж. Немає шаблону;
- не додавай фінальний 'висновок', мораль або повтор уже сказаного;
- нормальна сучасна українська, без канцеляриту, кальок, службових переходів і демонстративної 'експертності';
- легка іронія можлива лише як інтонація, якщо вона не додає нового твердження.

ФАКТИЧНА БЕЗПЕКА:
- не додавай жодного факту, числа, дати, сутності, причини, мотиву, оцінки чи прогнозу поза SOURCE;
- зберігай атрибуцію та невизначеність;
- якщо згадуєш лазівку, вразливість, виняток або новий механізм, поясни саму суть;
- без заголовка, URL, хештегів, емодзі й коментарів;
- заверши повним реченням;
- жорсткий ліміт {hard_limit} символів. Не намагайся заповнити його повністю. Для більшості історій достатньо приблизно 500–850 символів.

Перед відповіддю мовчки перечитай текст так, ніби пояснюєш новину розумному знайомому. Якщо речення хочеться перечитати вдруге — спости його.

ПРОФІЛЬ КАНАЛУ:
{profile or '(не задан)'}

SOURCE TITLE:
{_row_value(article, 'title')[:320]}

SOURCE EVIDENCE PACK:
{source}

RUSSIAN EDITORIAL PLAN (NOT EVIDENCE):
{str(russian_draft or '')[:1800]}{memory_block}

Поверни ТІЛЬКИ готовий український пост.""".strip()


def balance_reject_reason_rc49(
    channel: Any,
    article: Mapping[str, Any] | Any,
    recent,
    *,
    category: str | None = None,
) -> tuple[str, str]:
    """Weights are targets/diagnostics, not quotas.  Zero remains an explicit ban."""
    from . import rc42_policy as rc42
    from . import rc46_policy as rc46

    if is_ctrl_ua(channel):
        narrow = ctrl_ua_niche_reject_reason(article)
        if narrow:
            return narrow, str(category or "")

    categories = rc42.parse_editorial_weights(channel)
    if not categories:
        return "", str(category or "")

    value = str(category or "").strip()
    if value == rc46._UNCLASSIFIED:
        raise AIRouterError("RC49 refuses unclassified editorial pass; article held for retry.")
    if value == rc46._OTHER:
        return (
            "EDITORIAL_FIT_RC49_SKIP: матеріал не відповідає редакційному профілю або жодній налаштованій категорії.",
            rc46._OTHER,
        )

    weights = {str(item["name"]): float(item["weight"]) for item in categories}
    lookup = {rc46._category_key(name): name for name in weights}
    canonical = lookup.get(rc46._category_key(value))
    if canonical is None:
        return "", value
    if weights[canonical] <= 0:
        return (
            f"EDITORIAL_WEIGHT_RC49_SKIP: категорія «{canonical}» має вагу 0 для каналу «{getattr(channel, 'name', '')}».",
            canonical,
        )

    # Keep visibility into distribution, but never reject a good story merely
    # because its category is temporarily above a target percentage.
    recent_categories = []
    for row in list(recent)[:20]:
        current = lookup.get(rc46._category_key(_row_value(row, "editorial_category")))
        if current:
            recent_categories.append(current)
    positive_total = sum(weight for weight in weights.values() if weight > 0)
    target = (weights[canonical] / positive_total * 100.0) if positive_total > 0 else 0.0
    current_count = sum(1 for item in recent_categories if item == canonical)
    LOG.info(
        "RC49 editorial balance article_id=%s category=%s decision=soft-pass current=%s/%s target=%.1f%%",
        _row_value(article, "id", "?"), canonical, current_count, len(recent_categories), target,
    )
    return "", canonical


def _validation_only_final(channel: Any, article: Any, draft: str, *, hard_limit: int):
    """RC49 removes RC47's second generative rewrite.

    The single UA author writes the copy.  This stage validates facts/language and
    only rejects severe read-aloud failures so a later retry can generate a fresh
    candidate.  It never rewrites an already accepted post.
    """
    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc47_policy as rc47

    allowed_years = rc40._rc40_allowed_years(article)
    allowed_numbers = rc40._rc40_allowed_numbers(article, draft)
    body = rc40._validated_ua_body(
        draft,
        article=article,
        allowed_years=allowed_years,
        allowed_numbers=allowed_numbers,
        hard_limit=int(hard_limit),
    )
    blockers = tuple(rc47._deterministic_editorial_blockers(body)) + _human_readability_issues(body)
    blockers = tuple(dict.fromkeys(blockers))
    if blockers:
        raise production.PostAIQAExhausted(
            "RC49 validation-only newsroom gate: " + "; ".join(blockers),
            blockers,
            provider_outage=False,
        )
    return SimpleNamespace(provider="local-rule", model="rc49-validation-only"), body


def install_rc49_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import production_pipeline as production
    from . import rc40_policy as rc40
    from . import rc42_policy as rc42
    from . import rc45_policy as rc45
    from . import rc46_policy as rc46
    from . import rc47_policy as rc47
    from . import service as service_module
    from .telegram import TelegramError

    # One story editor -> one UA author. Replace the accumulated RC47/RC48 prompt
    # stack instead of adding another paragraph of instructions on top of it.
    rc40.build_russian_editorial_prompt = _build_ru_story_editor_prompt
    rc40.build_ukrainian_bridge_prompt = _build_ua_human_writer_prompt

    # RC47 remains the factual/self-contained safety wrapper, but its second
    # generative newsroom rewrite becomes validation-only.
    rc47._trusted_final_edit = _validation_only_final

    # Operator weights remain meaningful (0 disables a category), while positive
    # values are soft targets and never veto a strong story.
    rc42.balance_reject_reason = balance_reject_reason_rc49
    rc45.balance_reject_reason_rc45 = balance_reject_reason_rc49
    rc46.balance_reject_reason_rc46 = balance_reject_reason_rc49
    rc47.balance_reject_reason_rc47 = balance_reject_reason_rc49
    rc47._RC46_BALANCE = balance_reject_reason_rc49

    # CTRL+UA keeps the historical media-required contract. Other channels may
    # publish a compact text-only post when the article has no validated visual.
    old_decide = production.decide

    def decide_rc49(channel, article, recent, *, hard_limit=production.MEDIA_POST_HARD_LIMIT, format_marker=None):
        if is_ctrl_ua(channel):
            narrow = ctrl_ua_niche_reject_reason(article)
            if narrow:
                return Decision(
                    decision="reject", duplicate_of=None, reason=narrow,
                    event_key="ctrl-ua-breadth-v1", event_summary=_row_value(article, "title")[:1000],
                    headline_uk="", telegram_teaser="", full_article_uk="", media_captions_uk={},
                    confidence=0.99, provider="local-rule", model="rc49-ctrl-ua-breadth",
                )

        requested_limit = int(hard_limit)
        inner_limit = requested_limit
        if not is_ctrl_ua(channel) and requested_limit > int(production.MEDIA_POST_HARD_LIMIT):
            inner_limit = int(production.MEDIA_POST_HARD_LIMIT)
            LOG.info(
                "RC49 media policy article_id=%s channel=%s decision=text-only-allowed requested_limit=%s writer_limit=%s",
                _row_value(article, "id", "?"), getattr(channel, "name", ""), requested_limit, inner_limit,
            )
        return old_decide(
            channel, article, recent, hard_limit=inner_limit, format_marker=format_marker
        )

    production.decide = decide_rc49
    service_module.decide = decide_rc49

    # Telegram exceptions must be visible in the normal log even when UI/audit
    # storage is unavailable. Never log the bot token.
    def wrap_sender(label: str, func):
        def sender(token, chat_id, *args, **kwargs):
            try:
                return func(token, chat_id, *args, **kwargs)
            except TelegramError as exc:
                LOG.error("RC49 Telegram send failed action=%s chat=%s error=%s", label, chat_id, exc)
                raise
        return sender

    service_module.send_text = wrap_sender("text", service_module.send_text)
    service_module.send_prepared_photo = wrap_sender("photo", service_module.send_prepared_photo)
    service_module.send_video_url = wrap_sender("video", service_module.send_video_url)

    production.POST_FORMAT_PREFIX = "telegram-post-v31:"
    service_module.POST_FORMAT_PREFIX = "telegram-post-v31:"
    LOG.info("RC49 policy installed: one UA author, validation-only final gate, soft weights, channel-specific media")
    _INSTALLED = True
