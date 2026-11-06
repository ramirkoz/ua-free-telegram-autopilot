"""2.3.7: bounded Ukrainian typo fixes and safe paragraph wrapping.

Only exact attested corruptions and sentence-boundary whitespace are altered.
No names, statistics, dates, quoted evidence, URLs or event claims are added.
An unrepairable incomplete sentence still fails the existing strict QA.
"""
from __future__ import annotations

import re

_CORRECTIONS = (
    (re.compile(r'(?iu)[«"]?песочникові[»"]?\s+тести\b'), "тести зі штучним заниженням результатів"),
    (re.compile(r"(?iu)\bпроектують\b"), "проєктують"),
    (re.compile(r"(?iu)\bприховування\s+справді\s+здібностей\b"), "приховування справжніх здібностей"),
    (re.compile(r"(?iu)\bверхушки\b"), "верхівки"),
    (re.compile(r"(?iu)\bцієїєї\b"), "цієї"),
    (re.compile(r"(?iu)\bтаскати\b"), "носити"),
    (re.compile(r"(?iu)\bспівпадають\b"), "збігаються"),
    # LIVE 2.3.18 #92398: repair one attested broken word, with no new facts.
    (re.compile(r"(?iu)\bви[ \t]*\n[ \t]*пав\b"), "випав"),
)


def _retain_case(old: str, new: str) -> str:
    if old.isupper():
        return new.upper()
    return new[:1].upper() + new[1:] if old[:1].isupper() else new


def copyedit_issues_237(text: str) -> tuple[str, ...]:
    return tuple("UK_ATTESTED_LIVE_COPY_ERROR_237" for pattern, _ in _CORRECTIONS
                 if pattern.search(str(text or "")))


def _split_long_paragraph(paragraph: str, limit: int) -> str:
    if len(paragraph) <= limit:
        return paragraph
    sentences = re.split(r"(?<=[.!?…])\s+(?=[А-ЯІЇЄҐA-Z0-9«])", paragraph)
    if len(sentences) <= 1 or any(len(part) > limit for part in sentences):
        return paragraph  # Original validation will still reject an unsafe sentence.
    parts: list[str] = []
    line = ""
    for sentence in sentences:
        candidate = (line + " " + sentence).strip()
        if line and len(candidate) > limit:
            parts.append(line)
            line = sentence
        else:
            line = candidate
    if line:
        parts.append(line)
    return "\n\n".join(parts)


def safe_copyedit_237(value: str, *, paragraph_limit: int = 420) -> str:
    text = str(value or "")
    for pattern, replacement in _CORRECTIONS:
        text = pattern.sub(lambda m: _retain_case(m.group(0), replacement), text)
    if not text:
        return text
    paragraphs = re.split(r"(\n\s*\n)", text)
    return "".join(_split_long_paragraph(p, paragraph_limit) if not p.startswith("\n") else p
                   for p in paragraphs)


__all__ = ["safe_copyedit_237", "copyedit_issues_237"]
