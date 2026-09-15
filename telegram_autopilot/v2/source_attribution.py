from __future__ import annotations

from typing import Any, Mapping

from .domain import ChannelConfig, SourceAttributionMode


def _value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def clean_source_name(value: Any, limit: int = 120) -> str:
    """Return the operator-configured source name in a footer/prompt-safe form."""
    return " ".join(str(value or "").split()).strip()[: max(1, int(limit))]


def named_source_enabled(channel: ChannelConfig) -> bool:
    """Use named attribution only when the operator explicitly enabled it for this channel."""
    try:
        return SourceAttributionMode(str(channel.source_attribution_mode)) == SourceAttributionMode.NAMED_SOURCE
    except Exception:
        return False


def source_context_name(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    """Return the configured donor/source name only for explicit named-source mode."""
    if not named_source_enabled(channel):
        return ""
    return clean_source_name(_value(article, "source_name", ""))


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
    """Reserve caption space for a custom named-source footer when enabled."""
    footer = source_footer_label(channel, article)
    if not footer:
        return int(default_body_limit)
    available = int(telegram_limit) - len(footer) - 2
    return max(200, min(int(default_body_limit), available))


def require_source_context(text: str, source_name: str) -> None:
    """Keep the explicitly configured source context in the final rewrite."""
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
    """Return footer URLs/labels without changing reader-action links in the body.

    ``named_source`` uses the exact primary original-post URL and the configured source
    name. ``standard`` keeps the historical ``Джерело`` / ``Джерело N`` contract.
    """
    label = source_footer_label(channel, article)
    if label and str(source_url or "").startswith(("http://", "https://")):
        return [str(source_url)], [label]
    return list(source_urls), None
