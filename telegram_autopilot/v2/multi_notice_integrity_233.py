"""2.3.3: fail-closed protection for independently described lost/found pets.

Telegram bulletin messages can list seven unrelated pets under one post ID.
A writer must never merge their descriptions/locations/contacts into one animal.
Until separate source-owned item identities and per-item media can be proven,
exclude a multi-pet notice before costly generation and at prepublish.
"""
from __future__ import annotations
import re
from typing import Any

_PET = re.compile(r"(?iu)\b(?:собак[аиуие]|цуцен[яят]|лабрадор[аі]?|кішк[а-яіїєґ]*|киц[яію]|кошен[яят]|кот[а-яіїєґ]*)\b")
_MARKER = re.compile(r"(?u)[🐕🐶🐈🐱]", re.UNICODE)
_CONTACT = re.compile(r"(?u)(?:\+?38)?0\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
_BULLETIN = re.compile(r"(?iu)(?:дошка\s+оголошень|шукають\s+(?:господарів|дім)|віддають\s+(?:кицю|кошенят|собак)|знайшли\s+(?:собаку|цуценя))")


def _value(item: Any, key: str) -> str:
    try:
        return str(item[key] or '')
    except (KeyError, IndexError, TypeError):
        return str(getattr(item, key, '') or '')


def multi_pet_bulletin_reason(article: Any) -> str:
    """Narrow source-side gate, not a language model or subjective topic veto."""
    raw = _value(article, 'raw_text') or _value(article, 'title')
    if not raw or not _BULLETIN.search(raw):
        return ''
    # Distinct post entries can be separated by emoji despite HTML flattening.
    # Never infer entities from only the fact that an article mentions many pets.
    markers = _MARKER.findall(raw)
    if len(markers) >= 3 and len(_PET.findall(raw)) >= 3:
        return 'SOURCE_MULTIPLE_PET_NOTICES_UNSPLIT_233'
    # Explicitly separated unrelated lost-dog notices with incompatible collars
    # are another strong real-world indicator of multiple animals.
    if (len(markers) >= 2 and re.search(r'(?iu)без\s+нашийника', raw)
            and re.search(r'(?iu)з\s+(?:жовтим|червоним|синім|зеленим|чорним)\s+нашийником', raw)
            and len(_PET.findall(raw)) >= 2):
        return 'SOURCE_MULTIPLE_PET_NOTICES_UNSPLIT_233'
    if len(_CONTACT.findall(raw)) >= 3 and len(markers) >= 2 and len(_PET.findall(raw)) >= 3:
        return 'SOURCE_MULTIPLE_PET_NOTICES_UNSPLIT_233'
    return ''
