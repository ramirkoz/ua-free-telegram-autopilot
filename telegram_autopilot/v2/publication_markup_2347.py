"""Source-faithful plain-text normalization at the final Telegram boundary.

Telegram Bot API text and captions are sent without a Markdown parse_mode.
AI-generated *italics* or **inline emphasis** therefore leak literal stars
unless converted before text/caption attribution is constructed.
Keep this deliberately narrow: never delete free-standing asterisks, operators,
bullet markers, escaped literals, or unbalanced markup.
"""
from __future__ import annotations

import re

_TITLE_LINE_BOLD = re.compile(r"(?m)^([ \t]*)\*\*(.{4,180}?)\*\*([ \t]*)$")
_INLINE_BOLD = re.compile(
    r"(?<![\w*\\])\*\*([^\s*\n](?:[^*\n]{0,118}?[^\s*\n])?)\*\*(?![\w*])"
)
_INLINE_ITALIC = re.compile(
    r"(?<![\w*\\])\*([^\s*\n](?:[^*\n]{0,118}?[^\s*\n])?)\*(?![\w*])"
)


def normalize_plaintext_markup_2347(value: str) -> str:
    """Use Ukrainian guillemets for paired inline AI Markdown, not raw stars.

    Preserve existing title-line bold stripping, keep all other text byte-for-byte
    except matched balanced markup. Both text posts and media captions pass
    through this function in Publisher before the outgoing text is built.
    """
    text = str(value or "")
    text = _TITLE_LINE_BOLD.sub(r"\1\2\3", text)
    text = _INLINE_BOLD.sub(lambda m: f"«{m.group(1)}»", text)
    return _INLINE_ITALIC.sub(lambda m: f"«{m.group(1)}»", text)
