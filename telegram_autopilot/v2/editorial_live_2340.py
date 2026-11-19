"""2.3.40: source-only same-milestone and region-scope safeguards.

Do not use generated Ukrainian drafts as evidence of event identity. A new
confirmed update or a distinct historical discovery must remain publishable.
"""
from __future__ import annotations
import re
from typing import Any


def _field(row: Any, name: str) -> str:
    try:
        return str(row[name] or "")
    except (KeyError, IndexError, TypeError):
        return str(getattr(row, name, "") or "")


_VOYAGER_ONE = re.compile(r"(?i)\bvoyager[ -]?1\b|\bвояджер[- ]?1\b")
_ONE_LIGHT_DAY = re.compile(r"(?i)\b(?:one[ -]light[ -]day|a light[ -]day|1[ -]light[ -]day)\b|од[иі]н\s+світлов\w*\s+д[еє]н\w*")
_DIFFERENT_DISCOVERY = re.compile(r"(?i)golden[ -]record|\bhistorian\b|\bphonograph\b|\binstructions?\b|золот\w*\s+платівк\w*|історик\w*|інструкц\w*")
_MATERIAL_UPDATE = re.compile(r"(?i)\bnasa\s+(?:has\s+)?confirm(?:s|ed)\b|\bconfirmed\s+(?:by\s+)?nasa\b|\bnew\s+(?:data|measurements|transmission|signal)\b|підтвердил\w*|нов\w*\s+дан\w*")


def same_science_milestone_without_new_facts(current: Any, prior: Any) -> bool:
    """Conservative original-title fingerprint for the reported Voyager milestone.

    The two news items have divergent body wording and unrelated supplementary
    numbers. Only this precise milestone, not Voyager history generally, collides.
    """
    a = _field(current, "title")
    b = _field(prior, "title")
    if not (a and b and _VOYAGER_ONE.search(a) and _VOYAGER_ONE.search(b)):
        return False
    if not (_ONE_LIGHT_DAY.search(a) and _ONE_LIGHT_DAY.search(b)):
        return False
    if _DIFFERENT_DISCOVERY.search(a) or _DIFFERENT_DISCOVERY.search(b):
        return False
    if _MATERIAL_UPDATE.search(a) and not _MATERIAL_UPDATE.search(b):
        return False
    return True
