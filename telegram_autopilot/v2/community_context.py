from __future__ import annotations

from typing import Any, Mapping

from .domain import ChannelConfig


def _value(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def clean_source_name(value: Any, limit: int = 120) -> str:
    """Return the operator-configured donor name in a footer/prompt-safe form."""
    return " ".join(str(value or "").split()).strip()[: max(1, int(limit))]


def is_communities_channel(channel: ChannelConfig) -> bool:
    """Detect the communities output channel without pinning a mutable numeric ID."""
    return "громад" in str(channel.name or "").casefold()


def community_source_name(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    """Use the existing source name as the community name for the communities lane."""
    if not is_communities_channel(channel):
        return ""
    return clean_source_name(_value(article, "source_name", ""))


def community_footer_label(channel: ChannelConfig, article: Mapping[str, Any] | Any) -> str:
    name = community_source_name(channel, article)
    return f"Читати у «{name}»" if name else ""


def community_body_hard_limit(
    channel: ChannelConfig,
    article: Mapping[str, Any] | Any,
    *,
    telegram_limit: int = 900,
    default_body_limit: int = 880,
) -> int:
    """Reserve enough caption space for the custom clickable community footer."""
    footer = community_footer_label(channel, article)
    if not footer:
        return int(default_body_limit)
    # Two newlines separate body and footer in build_post_text().
    available = int(telegram_limit) - len(footer) - 2
    return max(200, min(int(default_body_limit), available))


def require_community_context(text: str, community_name: str) -> None:
    """Prevent an otherwise valid rewrite from becoming a contextless 'the community'."""
    name = clean_source_name(community_name)
    if not name:
        return
    if name.casefold() not in str(text or "").casefold():
        raise ValueError(f"У рерайті втрачено назву громади: {name}")


def attribution_for_article(
    channel: ChannelConfig,
    article: Mapping[str, Any] | Any,
    *,
    source_url: str,
    source_urls: list[str] | tuple[str, ...],
) -> tuple[list[str], list[str] | None]:
    """Return footer URLs/labels while leaving actionable body links untouched.

    Communities use exactly the canonical original post as attribution and display
    the operator-configured source name. Other channels keep the historical generic
    source footer behaviour and any additional evidence-source links.
    """
    label = community_footer_label(channel, article)
    if label and str(source_url or "").startswith(("http://", "https://")):
        return [str(source_url)], [label]
    return list(source_urls), None
