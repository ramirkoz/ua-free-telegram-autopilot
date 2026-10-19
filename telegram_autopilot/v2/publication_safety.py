"""Fail-closed detection of internal AI rejection messages in final publication text."""
from __future__ import annotations
import re

_REJECTION = re.compile(
    r"(?:не\s+(?:стосується|відповідає)\s+(?:тематиц[іи]|запорізьк)|"
    r"не\s+відповідає\s+тематиц[іи]|"
    r"(?:матеріал|новин[ау]|публікаці[яю])\s+(?:не\s+)?(?:відхилен[ао]|нерелевантн[ао])|"
    r"(?:відхилити|не\s+публікувати)\s+(?:цей\s+)?матеріал|"
    r"не\s+(?:підходить|придатн[ао])\s+для\s+(?:цього\s+)?канал[уа])", re.I,
)
_PREFIX = re.compile(r"^\s*(?:відповідь\s*:|answer\s*:|decision\s*:|reject\s*:)", re.I)

def is_ai_rejection_text(text: str) -> bool:
    """Block selector explanations, not ordinary news quoting a refusal.

    The specific off-topic rejection is blocked regardless of length; other
    rejection phrases are blocked only for short, self-referential AI outputs.
    """
    value = str(text or "").strip()
    if not value:
        return False  # Existing TEXT_MISSING guard handles empty text.
    low = value.casefold()
    if re.search(r"(?:цей\s+матеріал|ця\s+новина|цей\s+текст).{0,100}(?:не\s+стосується|не\s+відповідає|не\s+підходить)", low, re.S):
        return True
    if _PREFIX.search(value) and (_REJECTION.search(value) or len(value) < 90):
        return True
    if len(value) <= 320 and _REJECTION.search(value) and any(
        word in low for word in ("темати", "канал", "матеріал", "публікац")
    ):
        return True
    return False
