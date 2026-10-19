"""One post per named initiative (programme, contest, campaign) per channel window.

Communities re-post the same centrally prepared announcement ("ВідНОВА:UA",
"Вікі любить пам'ятки") in different words, so text/event fingerprints do not
match. The stable identity is the quoted initiative name next to an initiative
word. A quoted name alone is not enough: brands and institutions in quotes
("Укрзалізниця", "Дія") are ordinary news subjects, not initiatives.

The window is a channel setting (``ChannelPolicy.initiative_dedupe_days``);
0 disables the rule. A repeat is still new when the community adds its own
logistics (a street address or a phone number) that the published post lacks.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

_QUOTED = re.compile(r"[«\"“„]([^«»\"“”„]{3,60})[»\"”“]")
_INITIATIVE_WORDS = re.compile(
    r"(?iu)\b(?:програм\w*|проєкт\w*|проект\w*|ініціатив\w*|конкурс\w*|фотоконкурс\w*|акці\w*|марафон\w*|"
    r"кампані\w*|обмін\w*|грант\w*|форум\w*|фестивал\w*|набір|набору|реєстрац\w*|челендж\w*|олімпіад\w*)"
)
_ADDRESS = re.compile(r"(?iu)\b(?:вул\.|вулиц\w+|просп\.|проспект\w*|пров\.|провулок|площ\w+)\s*[\w'’-]+")
_PHONE = re.compile(r"(?:\+?38)?0\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
_NEAR = 90


def _norm(name: str) -> str:
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", name.casefold())
    text = re.sub(r"[^0-9a-zа-яіїєґ]+", "", text)
    return text


def initiative_keys(text: str) -> set[str]:
    raw = str(text or "")
    keys: set[str] = set()
    for match in _QUOTED.finditer(raw):
        start, end = match.span()
        window = raw[max(0, start - _NEAR):min(len(raw), end + _NEAR)]
        if not _INITIATIVE_WORDS.search(window):
            continue
        key = _norm(match.group(1))
        if len(key) >= 4:
            keys.add(key)
    return keys


def _local_logistics(text: str) -> set[str]:
    raw = str(text or "")
    found = {m.group(0).casefold() for m in _ADDRESS.finditer(raw)}
    found |= {re.sub(r"\D", "", m.group(0))[-9:] for m in _PHONE.finditer(raw)}
    return found


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).astimezone().isoformat(timespec="seconds")


def find_initiative_duplicate(store: Any, current: Any, channel: Any) -> tuple[int, str] | None:
    """Return (article_id, reason) of an earlier post about the same initiative."""
    try:
        days = int(getattr(channel.policy, "initiative_dedupe_days", 0) or 0)
    except Exception:
        days = 0
    if days <= 0:
        return None
    text = f"{current['title'] or ''}\n{current['raw_text'] or ''}"
    keys = initiative_keys(text)
    if not keys:
        return None
    logistics = _local_logistics(text)
    with store.connect() as con:
        rows = con.execute(
            """SELECT id,title,raw_text FROM articles
                WHERE channel_id=? AND id<>?
                  AND ((stage='PUBLISHED' AND published_at>=?)
                       OR (stage='READY' AND decision='PUBLISH' AND ready_at>=?))
                ORDER BY id DESC LIMIT 400""",
            (int(current["channel_id"]), int(current["id"]), _cutoff(days), _cutoff(days)),
        ).fetchall()
    for row in rows:
        other = f"{row['title'] or ''}\n{row['raw_text'] or ''}"
        shared = keys & initiative_keys(other)
        if not shared:
            continue
        if logistics - _local_logistics(other):
            # The community added its own address/phone: a local event of the initiative.
            continue
        name = sorted(shared)[0]
        return int(row["id"]), f"INITIATIVE_DUPLICATE: same initiative '{name}' within {days} days"
    return None
