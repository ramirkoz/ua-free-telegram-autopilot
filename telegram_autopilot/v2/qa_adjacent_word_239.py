"""2.2.39: cautious deterministic repeated-word QA recovery.

Output is NEVER approved by this module. A changed draft is usable only if
the existing, complete editorial validator accepts it again, including all
factuality, polarity, source attribution, figures and media checks.
"""
from __future__ import annotations

import re

# Exactly the human-readable hard QA error observed in operator LIVE.
_ADJACENT_WORD_QA = "жорсткий qa: сусіднє слово повторено двічі"
_ADJACENT_WORDS = re.compile(
    r"(?iu)(?<![\w])([^\W\d_]{4,})([ \t]+)\1(?![\w])"
)


def repair_adjacent_repeated_word(text: str, error: Exception) -> str:
    """Delete one obviously accidental duplicate word, never alter the facts.

    Never touch quotations with uncertain semantics, model errors unrelated
    to this exact QA rule, digits, punctuation, URLs or long/short drafts.
    """
    if _ADJACENT_WORD_QA not in str(error or "").casefold():
        return ""
    source = str(text or "")
    if len(source) < 80 or len(source) > 4000:
        return ""
    if "https://" in source.casefold() or "http://" in source.casefold():
        # Avoid touching literal source URLs and embedded citations.
        return ""
    # Avoid quotations: repeated words inside direct speech may be deliberate.
    if any(char in source for char in ("«", "»", "“", "”", '"')):
        return ""
    matches = list(_ADJACENT_WORDS.finditer(source))
    if len(matches) != 1:
        return ""
    match = matches[0]
    # A clearly lowercase duplication is safe to propose for full QA.
    word = match.group(1)
    if not word.islower():
        return ""
    patched = source[:match.start()] + word + source[match.end():]
    return patched if patched != source else ""
