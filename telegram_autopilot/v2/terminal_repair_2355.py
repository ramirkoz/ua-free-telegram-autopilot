"""Source-preserving repair of orphaned final headings after a full sentence.

Do not complete a statement by guessing. Keep the last *complete* sentence,
only when an isolated dangling callout can be removed without violating the
minimum source-backed content floor. Any other broken ending stays blocked.
"""
from __future__ import annotations
import re
from .terminal_text_guard_228 import incomplete_terminal_text_228

_COMPLETED_SENTENCE = re.compile(r"[.!?…](?:[»”'\"])?(?=\s|$)")


def remove_orphaned_terminal_callout_2355(text: str, *, min_chars: int) -> str:
    value = str(text or "").strip()
    if not incomplete_terminal_text_228(value):
        return value
    if not value.endswith((':', ';', ',', '—', '–')):
        return value
    matches = list(_COMPLETED_SENTENCE.finditer(value))
    if not matches:
        return value
    cut = matches[-1].end()
    orphan = value[cut:].strip()
    if not (2 <= len(orphan) <= 130):
        return value
    # No URL, phone, named service or multi-line contact line can be silently
    # discarded.  These must be handled by an author with the original source.
    if re.search(r"(?:https?://|www\.|\+?\d[\d\s-]{6,}|@\w+)", orphan, re.I):
        return value
    clean = value[:cut].rstrip()
    if len(re.sub(r"\s+", " ", clean).strip()) < int(min_chars):
        return value
    return clean


__all__ = ["remove_orphaned_terminal_callout_2355"]
