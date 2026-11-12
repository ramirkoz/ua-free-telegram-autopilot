"""2.3.28: fail closed when an AI draft visibly ends mid-sentence.

Pure source-preserving check. Never fabricate a continuation or silently add
a period: return the text to the ordinary bounded quality rewrite queue.
"""
from __future__ import annotations

import re

_BAD_END = re.compile(r"(?u)(?:[:,;–—]|[(\[{]|(?:\\b(?:і|та|але|або|що|який|яка|які|тому|зокрема|за|для|and|or|because)))[\s\u00a0]*$")
_DANGLING_LIST = re.compile(r"(?m)(?:^|\n)\s*(?:\d+[.)]|[-•])\s*$")


def incomplete_terminal_text_228(text: str) -> str:
    """Return quality code only for obvious truncated tails.

    Some legitimate news captions end in quotes/exclamation marks, so do not
    require an arbitrary final full stop for otherwise complete prose.
    """
    value = str(text or "").strip()
    if not value:
        return "TRUNCATED_EMPTY_228"
    if _DANGLING_LIST.search(value):
        return "TRUNCATED_LIST_228"
    if value.endswith((":", ";", ",", "(", "[", "{", "—", "–")):
        return "TRUNCATED_TERMINAL_PUNCTUATION_228"
    if re.search(r"(?iu)\b(?:і|та|але|або|що|оскільки|для|за|because|and|or)\s*$", value):
        return "TRUNCATED_TERMINAL_CONNECTOR_228"
    return ""


__all__ = ["incomplete_terminal_text_228"]
