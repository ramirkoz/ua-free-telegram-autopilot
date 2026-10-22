"""Source-owned, conservative identity for cross-publisher military repatriation notices.

Two publishers may caption the same Coordination HQ notice with different words
and photo albums. Do not infer a second event from a different URL/watermark.
Source-local outcomes, changed body counts, and different reporting windows
must remain distinct. This helper never reads AI-generated draft/final text.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


_RETURN = re.compile(
    r"(?iu)\b(?:повернул\w*|повернен\w*|поверта\w*|"
    r"репатріювал\w*|репатрійован\w*|репатріац\w*)\b"
)
_REMAINS = re.compile(
    r"(?iu)\b(?:тіла|тіло|тіл|останки|останків|рештки|решток)\b"
)
_MILITARY = re.compile(
    r"(?iu)\b(?:військов\w*|військовослужбовц\w*|загибл\w*|"
    r"полегл\w*|коордштаб\w*|координаційн\w*\s+штаб\w*)\b"
)
_COUNT_AFTER = re.compile(
    r"(?iu)\b(?:тіла|тіл|останків|останки|решток|рештки)"
    r"\s+(?:ще\s+)?(?P<n>\d{2,4})\b"
)
_COUNT_BEFORE = re.compile(
    r"(?iu)\b(?P<n>\d{2,4})\s+(?:тіл|тіла|останків|останки|"
    r"решток|рештки|загибл\w*|полегл\w*)\b"
)
_LOCAL = re.compile(
    r"(?iu)\b(?:запоріж\w*|запоріз\w*|мелітопол\w*|"
    r"бердянськ\w*|енергодар\w*|токмак\w*|гуляйпол\w*|"
    r"оріхів\w*|василів\w*|полог\w*|дніпрорудн\w*)\b"
)
_FINISHED_NEW_OUTCOME = re.compile(
    r"(?iu)\b(?:ідентифікувал\w*|встановил\w*\s+особ\w*|"
    r"передал\w*\s+родин\w*|поховал\w*)\b"
)


def _v(row: Any, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        value = getattr(row, key, "")
    return str(value or "")


def _original(row: Any) -> str:
    # Deliberately exclude generated final_text, title rewrites and source name.
    return (_v(row, "title") + "\n" + _v(row, "raw_text"))[:6000]


def _counts(text: str) -> set[int]:
    counts = {
        int(match.group("n"))
        for pattern in (_COUNT_AFTER, _COUNT_BEFORE)
        for match in pattern.finditer(text)
    }
    return {n for n in counts if n >= 10}


def _signature(text: str) -> set[int]:
    if not (_RETURN.search(text) and _REMAINS.search(text)
            and _MILITARY.search(text)):
        return set()
    return _counts(text)


def _time(row: Any) -> datetime | None:
    # The published ledger has published_at but often not source_published_at.
    for key in ("source_published_at", "published_at", "discovered_at"):
        raw = _v(row, key).strip()
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None:
                return None
            return value.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def repatriation_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """Compare independent news sources about the same returned remains batch.

    Distinguishing reasons starting with 'distinct repatriation' are hard
    boundaries: generic fuzzy-title similarity must not override them.
    """
    left_source = _v(current, "source_id")
    right_source = _v(candidate, "source_id")
    if left_source and right_source and left_source == right_source:
        return False, "same publisher; leave to exact-identity matcher"

    a, b = _original(current), _original(candidate)
    counts_a, counts_b = _signature(a), _signature(b)
    if not counts_a or not counts_b:
        return False, "not two body-counted military repatriation notices"
    if not (counts_a & counts_b):
        return False, "distinct repatriation count"

    # A source adding a local victim/identification outcome may be a genuinely
    # new regional follow-up. Do not collapse it into a national bulletin.
    if _LOCAL.search(a) or _LOCAL.search(b):
        return False, "distinct repatriation local follow-up"
    if _FINISHED_NEW_OUTCOME.search(a) != _FINISHED_NEW_OUTCOME.search(b):
        return False, "distinct repatriation completed identification/hand-over"

    ta, tb = _time(current), _time(candidate)
    if ta is None or tb is None:
        return False, "repatriation event time unavailable"
    if abs((ta - tb).total_seconds()) > 3 * 3600:
        return False, "distinct repatriation report window"

    return True, (
        "cross-source returned-remains batch identity "
        f"count={','.join(map(str, sorted(counts_a & counts_b)))} within=3h"
    )


def national_repatriation_without_local_outcome(article: Any) -> bool:
    """National Coordination HQ notices are not automatically regional events.

    An opted-in civic channel can still cover an actual local person's return,
    local identification, memorial, or other source-owned local development.
    """
    original = _original(article)
    return bool(_signature(original) and not _LOCAL.search(original))
