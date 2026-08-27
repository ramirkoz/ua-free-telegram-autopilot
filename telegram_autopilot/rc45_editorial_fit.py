from __future__ import annotations

import re

_INSTALLED = False

# These patterns are not global rejections. They only disable the cheap literal
# category shortcut so the RC45 semantic assignment editor must decide whether
# the material actually belongs in this particular channel profile.
_PROFILE_REVIEW_TITLE_PATTERNS = (
    r"\bhow\s+to\b",
    r"\bwhat\s+is\b",
    r"\bwhy\s+does\b",
    r"\bexplained\b",
    r"\b(?:beginner'?s?|complete|ultimate)\s+guide\b",
    r"\bguide\s+to\b",
    r"\btop\s+(?:ten|10|\d+)\b",
    r"\bbest\s+.+\b",
    r"\beverything\s+you\s+need\s+to\s+know\b",
    r"\bbook\s+review\b",
    r"\breview\s*:\s*",
    r"\bconference\b",
    r"\bworkshop\b",
    r"\bcall\s+for\s+(?:papers|abstracts)\b",
    # Ukrainian / Russian source equivalents for reverse channels.
    r"\bяк\s+(?:зробити|працює|налаштувати)\b",
    r"\bщо\s+таке\b",
    r"\bпояснюємо\b",
    r"\bгайд\b",
    r"\bтоп\s*[-–—]?\s*\d+\b",
    r"\bогляд\b",
    r"\bконференц",
    r"\bворкшоп\b",
    r"\bкак\s+(?:сделать|работает|настроить)\b",
    r"\bчто\s+такое\b",
    r"\bобъясняем\b",
    r"\bобзор\b",
)
_PROFILE_REVIEW_RE = re.compile("|".join(f"(?:{p})" for p in _PROFILE_REVIEW_TITLE_PATTERNS), re.I)


def needs_semantic_profile_review(title: str) -> bool:
    return bool(_PROFILE_REVIEW_RE.search(" ".join(str(title or "").split())))


def install_rc45_editorial_fit() -> None:
    """Keep lexical category matching cheap, except where format/title screams 'review me'."""
    global _INSTALLED
    if _INSTALLED:
        return

    from . import rc45_policy as policy

    original = policy.lexical_category

    def lexical_category_rc45(article, categories):
        try:
            title = str(article["title"] or "")
        except Exception:
            title = str(getattr(article, "title", "") or "")
        if needs_semantic_profile_review(title):
            return ""
        return original(article, categories)

    policy.lexical_category = lexical_category_rc45
    _INSTALLED = True
