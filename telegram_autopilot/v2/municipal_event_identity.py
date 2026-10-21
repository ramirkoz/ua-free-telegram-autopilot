"""Conservative same-event identity for Ukrainian local civic construction news.

Media URLs/hashes never determine article identity; construction stage matters.
Use a corroborated district or exact site, plus a short news window. Distinct
streets or parks are not silently treated as one site.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_DISTRICTS = ("олександрівськ", "вознесенівськ", "дніпровськ", "комунарськ", "хортицьк", "шевченківськ", "заводськ")
_SHELTER = re.compile(r"(?iu)\bмодульн\w*\b.{0,70}\bукрит\w*|\bукрит\w*\b.{0,70}\bмодульн\w*")
_STREET = re.compile(r"(?iu)\b(?:вул(?:иц[іяєю])?\.?|провул(?:ок|ку)|проспект(?:і|у)?)\s+[«\"]?([а-яіїєґ'’\-]{5,})")
_PARK = re.compile(r"(?iu)\bпарк(?:у|ом|а|і)?\s+[«\"]?([а-яіїєґ'’\-]{4,})(?:\s+([а-яіїєґ'’\-]{3,}))?")


def _field(row: Any, key: str) -> str:
    try:
        v = row[key]
    except (KeyError, TypeError, IndexError):
        v = getattr(row, key, "")
    return str(v or "")


def _text(row: Any) -> str:
    return "\n".join(_field(row, key) for key in ("title", "raw_text", "event_summary", "final_text"))[:10000].casefold()


def _phase(text: str) -> str:
    if re.search(r"(?iu)відкри(?:ли|то|вається|вся)\s+.{0,35}укрит|укрит.{0,45}відкри(?:ли|то)", text):
        return "opened"
    if re.search(r"(?iu)заверш(?:или|ено|илися).{0,65}(?:монтаж|встанов|будівництв)|встановлене\s+укритт", text):
        return "completed"
    if re.search(r"(?iu)\b(?:встановлю\w*|встановлення|монтаж\w*|монту\w*|тривають\s+робот\w*|монтажні\s+робот\w*)\b", text):
        return "installing"
    if re.search(r"(?iu)\b(?:планую\w*|запланован\w*|проєктую\w*|проектую\w*)\b", text):
        return "planned"
    return ""


def _site(text: str, pattern: re.Pattern[str]) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    value = " ".join(x for x in m.groups() if x)
    return re.sub(r"[^а-яіїєґ]", "", value.casefold())[:64]


def _published_time(row: Any) -> datetime | None:
    for key in ("source_published_at", "published_at", "discovered_at"):
        raw = _field(row, key).strip()
        if not raw:
            continue
        try:
            date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return date if date.tzinfo else date.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def municipal_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """Return positive only when object, phase, place and timing corroborate."""
    if int(_field(current, "source_id") or 0) == int(_field(candidate, "source_id") or -1):
        return False, ""
    a, b = _text(current), _text(candidate)
    if not (_SHELTER.search(a) and _SHELTER.search(b)):
        return False, ""
    stage_a, stage_b = _phase(a), _phase(b)
    if not stage_a or stage_a != stage_b:
        return False, ""
    time_a, time_b = _published_time(current), _published_time(candidate)
    if time_a and time_b and abs((time_a - time_b).total_seconds()) > 72 * 3600:
        return False, ""
    streets = (_site(a, _STREET), _site(b, _STREET))
    parks = (_site(a, _PARK), _site(b, _PARK))
    # Strong negative evidence must overrule generic shared district vocabulary.
    if all(streets) and streets[0] != streets[1]:
        return False, ""
    if all(parks) and parks[0] != parks[1]:
        return False, ""
    same_specific_site = bool(streets[0] and streets[0] == streets[1]) or bool(parks[0] and parks[0] == parks[1])
    districts_a = {p for p in _DISTRICTS if p in a}
    districts_b = {p for p in _DISTRICTS if p in b}
    same_district = bool(districts_a & districts_b)
    if not same_specific_site and not same_district:
        return False, ""
    # Within a district, admit street-to-nearby-park reports only when neither
    # provides *conflicting comparable* street/park addresses, and both say Zaporizhzhia.
    if not same_specific_site and not (any(root in a for root in ("запоріж", "запоріз")) and any(root in b for root in ("запоріж", "запоріз"))):
        return False, ""
    site = ("street:" + streets[0]) if same_specific_site and streets[0] else (
        "park:" + parks[0] if same_specific_site else "district:" + ",".join(sorted(districts_a & districts_b))
    )
    return True, f"municipal event identity object=modular_shelter phase={stage_a} site={site}"
