from __future__ import annotations

import re
from typing import Any

from .dedupe import DedupeResult
from .domain import Decision
from .semantic_dedupe import (
    SemanticDedupeEngine,
    SemanticGuardedPublisher,
    _concept_sequence,
    _value,
    semantic_same_event,
)

# RC52: the old semantic lane is intentionally conservative, but it still relies on
# literal word order/phrase overlap. Independent publishers can describe one concrete
# study with almost no shared bigrams. This guard adds a second, event-level fingerprint
# using concept roots plus compatible numeric anchors. It is cross-source only.
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:\s*%|\s*відсот(?:ок|ки|ків)?)?", re.I)

_EVENT_FAMILIES: dict[str, tuple[str, ...]] = {
    "human": ("людськ", "human"),
    "mouse": ("миш", "mouse", "mice"),
    "brain_cortex": ("кортик", "кори головн", "cortex", "cortical"),
    "neural_tissue": ("нейрон", "нервов", "органоїд", "neuron", "neural", "organoid"),
    "transfer": ("пересад", "трансплант", "інтегр", "transplant", "graft", "integrat"),
    "stem_cell": ("стовбур", "stem cell"),
    "growth": ("заповн", "зайня", "розріс", "збільш", "вирос", "occup", "fill", "grow"),
    "brain": ("мозк", "brain"),
}


def _text(row: Any) -> str:
    return "\n".join(
        str(_value(row, key, "") or "")
        for key in ("title", "raw_text", "final_text", "event_summary")
    ).casefold()[:14000]


def _numbers(value: str) -> list[float]:
    out: list[float] = []
    for match in _NUMBER_RE.finditer(value):
        token = match.group(0).casefold().replace("відсотків", "").replace("відсотки", "").replace("відсоток", "").replace("%", "").strip()
        try:
            number = float(token.replace(",", "."))
        except ValueError:
            continue
        # Calendar years are poor event anchors and create false matches.
        if 1900 <= number <= 2100 and number.is_integer():
            continue
        if 0 < number < 1:
            continue
        out.append(number)
    return out[:24]


def _near_numeric_pairs(left: str, right: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for a in _numbers(left):
        for b in _numbers(right):
            tolerance = max(2.0, 0.04 * max(abs(a), abs(b)))
            if abs(a - b) <= tolerance:
                pairs.append((a, b))
                break
    return pairs


def _family_hits(value: str) -> set[str]:
    return {
        family
        for family, roots in _EVENT_FAMILIES.items()
        if any(root in value for root in roots)
    }


def event_fingerprint_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """High-precision event equivalence after the normal semantic matcher.

    The generic rule requires both shared concept density and compatible numbers.
    A narrow biomedical lane additionally catches heavy paraphrases such as the
    observed human-cortical-tissue mouse study where 90% and 92% describe the same
    result but wording and imagery differ almost completely.
    """
    same, reason = semantic_same_event(current, candidate)
    if same:
        return True, reason
    if reason.startswith("conflicting strong event/version/product codes"):
        return False, reason

    if int(_value(current, "source_id", 0) or 0) == int(_value(candidate, "source_id", 0) or -1):
        return False, reason

    left = _text(current)
    right = _text(candidate)
    concepts_a = set(_concept_sequence(left))
    concepts_b = set(_concept_sequence(right))
    shared = concepts_a & concepts_b
    containment = len(shared) / max(1, min(len(concepts_a), len(concepts_b)))
    long_shared = {item for item in shared if len(item) >= 6}
    numeric_pairs = _near_numeric_pairs(left, right)

    families_a = _family_hits(left)
    families_b = _family_hits(right)
    shared_families = families_a & families_b
    research_core = {"human", "mouse", "brain_cortex", "neural_tissue"}

    # Concrete biomedical-study fingerprint. It does not merge generic neuroscience
    # stories: both sides must mention the human/mouse/cortical/neural core plus one
    # of transplant/stem-cell/growth anchors, with numeric or lexical corroboration.
    if research_core <= shared_families and len(shared_families) >= 5:
        if numeric_pairs or (len(long_shared) >= 7 and containment >= 0.20):
            return True, (
                "biomedical event fingerprint "
                f"families={','.join(sorted(shared_families))} "
                f"concepts={len(shared)}/{containment:.2f} numbers={numeric_pairs[:3]}"
            )

    # Generic cross-source event fingerprint. Numbers alone never decide equivalence;
    # they only corroborate a substantial shared concept set.
    if numeric_pairs and len(shared) >= 12 and containment >= 0.28 and len(long_shared) >= 6:
        return True, (
            "concept+numeric event fingerprint "
            f"concepts={len(shared)}/{containment:.2f} long={len(long_shared)} numbers={numeric_pairs[:3]}"
        )

    return False, (
        f"{reason}; event fingerprint concepts={len(shared)}/{containment:.2f} "
        f"long={len(long_shared)} families={','.join(sorted(shared_families)) or '-'} "
        f"numbers={numeric_pairs[:3]}"
    )


class EventFingerprintDedupeEngine(SemanticDedupeEngine):
    """Semantic dedupe plus a seven-day published-history safety net."""

    def _find_duplicate(self, article_id: int, *, published_only: bool = False) -> DedupeResult:
        current = self.store.get_article(article_id)
        if current is None:
            raise KeyError(article_id)
        channel = self.store.get_channel(int(current["channel_id"]))
        configured_hours = int(channel.dedupe_window_hours if channel else 72)
        # Final publication protection deliberately sees a longer history than ingest.
        hours = max(configured_hours, 168) if published_only else configured_hours

        if published_only:
            age = f"-{max(1, hours)} hours"
            with self.store.connect() as con:
                candidates = con.execute(
                    """SELECT a.*,s.name AS source_name
                       FROM articles a JOIN sources s ON s.id=a.source_id
                       WHERE a.channel_id=? AND a.id<>?
                         AND a.stage='PUBLISHED' AND a.decision<>'DUPLICATE'
                         AND datetime(CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END)>=datetime('now',?)
                       ORDER BY datetime(CASE WHEN a.published_at<>'' THEN a.published_at ELSE a.discovered_at END) DESC,a.id DESC
                       LIMIT 500""",
                    (int(current["channel_id"]), int(article_id), age),
                ).fetchall()
        else:
            candidates = self._candidate_rows(int(current["channel_id"]), int(article_id), hours)

        for candidate in candidates:
            if str(candidate["decision"]) == str(Decision.DUPLICATE):
                continue
            same, match_reason = event_fingerprint_same_event(current, candidate)
            if same:
                return DedupeResult("DUPLICATE", int(candidate["id"]), match_reason)
        return DedupeResult("SINGLE", None, "no confirmed same event")


__all__ = [
    "EventFingerprintDedupeEngine",
    "SemanticGuardedPublisher",
    "event_fingerprint_same_event",
]
