"""v2.3.22: prevent private lost-document notices becoming attributed news.

Only a source-owned combination of a found/lost individual's document and a
personal telephone is rejected. Official helplines and public service contact
details are not categorically banned. Do not infer guilt from nearby events.
No phone number or name is written into operator logs.
"""
from __future__ import annotations

import re
from typing import Any


_DOCUMENT_NOTICE = re.compile(
    r"(?iu)(?:"
    r"(?:знайшл\w*|знайден\w*|загубил\w*|загублен\w*|виявил\w*)"
    r"(?:\s+\S+){0,5}\s+(?:документ\w*|паспорт\w*|посвідченн\w*)"
    r"|(?:документ\w*|паспорт\w*|посвідченн\w*)"
    r"[^.!?\n]{0,90}\bна\s+ім[’']?я\b"
    r")"
)
_PHONE = re.compile(
    r"(?<!\d)(?:\+?38[\s().-]*)?0\d{2}(?:[\s().-]*\d){7}(?!\d)"
)


def _field(article: Any, name: str) -> str:
    try:
        value = article[name]
    except (KeyError, IndexError, TypeError):
        value = getattr(article, name, "")
    return str(value or "")


def private_document_contact_reason_2322(article: Any) -> str:
    """Source-only safety veto. Neither a channel name nor an AI draft is evidence."""
    source = (_field(article, "title") + "\n" + _field(article, "raw_text"))[:10000]
    if _DOCUMENT_NOTICE.search(source) and _PHONE.search(source):
        return "MONITORING_PRIVATE_DOCUMENT_CONTACT_2322"
    return ""
