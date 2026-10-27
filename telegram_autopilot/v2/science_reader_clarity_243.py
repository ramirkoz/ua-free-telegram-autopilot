"""Fail-closed, high-precision reader-first sentinel for general science news.

This deliberately only checks patterns that are reliably harmful without trying to
judge scientific importance from keywords. All semantic rewrites stay source-grounded
in the existing final editor; this gate adds NO paid AI calls.
"""
from __future__ import annotations

import re

_VAGUE_EXPERIMENT_LEAD = re.compile(
    r"^\s*[«“\"']?\s*(?:автор(?:и|ка)?|учасник(?:и)?)\s+"
    r"(?:експерименту|дослідження|статті|роботи)\b",
    re.IGNORECASE,
)
_FINDING = re.compile(
    r"\b(?:виявил\w*|з'ясува\w*|з’ясува\w*|"
    r"довел\w*|спростува\w*|підтвердил\w*|"
    r"показал\w*|встановил\w*)\b", re.IGNORECASE
)


def science_plain_language_issue(text: str) -> str:
    """Return an actionable reason for certain abstract, empty news openings.

    Only targeted general-science channels use this, both when final-editing and
    just before Telegram.  False-confidence semantic 'understanding' scores are
    intentionally avoided: source quality and factual QA are independently enforced.
    """
    body = str(text or "").strip()
    first = re.split(r"(?<=[.!?])\s+|\n+", body, maxsplit=1)[0].strip()
    if _VAGUE_EXPERIMENT_LEAD.search(first) and not _FINDING.search(first):
        return (
            "SCIENCE_READER_LEAD: безіменний «автор експерименту» описує "
            "процес замість суті відкриття. Почни з підтвердженого результату "
            "і поясни значення простими словами."
        )
    return ""
