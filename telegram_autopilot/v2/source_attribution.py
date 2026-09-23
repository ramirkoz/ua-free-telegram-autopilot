from __future__ import annotations

import re
from typing import Any, Mapping

from .domain import ChannelConfig, SourceAttributionMode, SourceBodyAttributionMode


def _value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def clean_source_name(value: Any, limit: int = 120) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, int(limit))]


def named_source_enabled(channel: ChannelConfig) -> bool:
    try:
        return SourceAttributionMode(str(channel.source_attribution_mode)) == SourceAttributionMode.NAMED_SOURCE
    except Exception:
        return False


def source_context_name(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    if not named_source_enabled(channel):
        return ""
    return clean_source_name(_value(article, "source_name", ""))


def _body_mode(channel: ChannelConfig) -> SourceBodyAttributionMode:
    try:
        return SourceBodyAttributionMode(str(channel.policy.source_body_attribution_mode))
    except Exception:
        return SourceBodyAttributionMode.FOOTER_ONLY


def _marker_matches(name: str, marker: str) -> bool:
    marker = " ".join(str(marker or "").split()).strip()
    if not marker:
        return False
    pattern = r"(?iu)(?<![\w’'-])" + re.escape(marker) + r"(?![\w’'-])"
    return bool(re.search(pattern, clean_source_name(name)))


def source_body_attribution_allowed(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> bool:
    name = clean_source_name(_value(article, "source_name", ""))
    if not name:
        return False
    mode = _body_mode(channel)
    if mode == SourceBodyAttributionMode.ALWAYS:
        return True
    if mode == SourceBodyAttributionMode.SOURCE_NAME_MARKER:
        return _marker_matches(name, str(channel.policy.source_body_attribution_marker or ""))
    return False


def source_body_context_name(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    name = clean_source_name(_value(article, "source_name", ""))
    return name if source_body_attribution_allowed(channel, article) else ""


def source_body_instruction(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    name = clean_source_name(_value(article, "source_name", ""))
    if not name:
        return ""
    if source_body_attribution_allowed(channel, article):
        return (
            "\nАТРИБУЦІЯ ДЖЕРЕЛА В ТІЛІ: дозволена правилами цього каналу. "
            "Якщо атрибуція потрібна для ясності, використовуй SOURCE NAME природно, без канцелярського шаблону. "
        )
    mode = _body_mode(channel)
    marker = str(channel.policy.source_body_attribution_marker or "").strip()
    reason = f" (умова-маркер у назві: {marker})" if mode == SourceBodyAttributionMode.SOURCE_NAME_MARKER and marker else ""
    return (
        "\nАТРИБУЦІЯ ДЖЕРЕЛА В ТІЛІ: ЗАБОРОНЕНА правилами цього каналу" + reason + ". "
        "Не згадуй SOURCE NAME у тексті й не представляй джерело як автора повідомлення. "
        "Посилання та назву джерела система додасть окремим footer. "
    )


def _source_aliases(name: str) -> tuple[str, ...]:
    clean = clean_source_name(name)
    if not clean:
        return ()
    aliases = [clean]
    without_numeric_prefix = re.sub(r"(?u)^\s*\d+[\s:._-]+", "", clean).strip()
    if len(without_numeric_prefix) >= 3 and without_numeric_prefix.casefold() != clean.casefold():
        aliases.append(without_numeric_prefix)
    return tuple(dict.fromkeys(aliases))


def source_body_attribution_issues(
    channel: ChannelConfig, article: Mapping[str, Any] | Any, text: str
) -> tuple[str, ...]:
    if source_body_attribution_allowed(channel, article):
        return ()
    name = clean_source_name(_value(article, "source_name", ""))
    if not name:
        return ()
    body = str(text or "")
    for alias in _source_aliases(name):
        pattern = r"(?iu)(?<![\w’'-])" + r"\s+".join(re.escape(part) for part in alias.split()) + r"(?![\w’'-])"
        if re.search(pattern, body):
            return ("правила каналу забороняють згадувати/атрибутувати джерело в тілі; джерело має лишатися тільки у footer",)
    return ()


def source_footer_label(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    name = source_context_name(channel, article)
    return f"Читати у «{name}»" if name else ""


def source_body_hard_limit(
    channel: ChannelConfig,
    article: Mapping[str, Any] | Any,
    *,
    telegram_limit: int = 900,
    default_body_limit: int = 880,
) -> int:
    footer = source_footer_label(channel, article)
    if not footer:
        return int(default_body_limit)
    available = int(telegram_limit) - len(footer) - 2
    return max(200, min(int(default_body_limit), available))


def require_source_context(text: str, source_name: str) -> None:
    name = clean_source_name(source_name)
    if not name:
        return
    if name.casefold() not in str(text or "").casefold():
        raise ValueError(f"У рерайті втрачено назву джерела: {name}")


def attribution_for_article(
    channel: ChannelConfig,
    article: Mapping[str, Any] | Any,
    *,
    source_url: str,
    source_urls: list[str] | tuple[str, ...],
) -> tuple[list[str], list[str] | None]:
    label = source_footer_label(channel, article)
    if label and str(source_url or "").startswith(("http://", "https://")):
        return [str(source_url)], [label]
    return list(source_urls), None
