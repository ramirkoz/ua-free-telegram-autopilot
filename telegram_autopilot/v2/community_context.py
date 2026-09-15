"""Compatibility aliases for RC34 imports.

Named attribution is generic since RC35 and is controlled by an explicit channel setting.
There is intentionally no runtime detection based on the channel name.
"""

from .source_attribution import (
    attribution_for_article,
    clean_source_name,
    named_source_enabled,
    require_source_context,
    source_body_hard_limit,
    source_context_name,
    source_footer_label,
)

community_source_name = source_context_name
community_footer_label = source_footer_label
community_body_hard_limit = source_body_hard_limit
require_community_context = require_source_context

__all__ = [
    "attribution_for_article",
    "clean_source_name",
    "named_source_enabled",
    "require_source_context",
    "source_body_hard_limit",
    "source_context_name",
    "source_footer_label",
    "community_source_name",
    "community_footer_label",
    "community_body_hard_limit",
    "require_community_context",
]
