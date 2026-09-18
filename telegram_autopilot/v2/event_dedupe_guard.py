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

# Advanced fingerprints are generic capabilities. Whether they are enabled is read
# from the current channel configuration; no channel name or concrete story is used
# by runtime matching.
_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:\s*%|\s*відсот(?:ок|ки|ків)?)?", re.I)
_BINOMIAL_RE = re.compile(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z-]{2,})\b")
_DISCOVERY_MARKERS = (
    "new species", "species described", "species discovered", "new taxon", "taxonomic",
    "новий вид", "нового виду", "описали вид", "відкрили вид", "новий таксон", "таксоном",
)
_RARE_STOP = {
    "дослідники", "дослідження", "науковці", "вчені", "результати", "показали",
    "researchers", "research", "scientists", "study", "results", "using", "based",
}


def _raw_text(row: Any) -> str:
    return "\n".join(
        str(_value(row, key, "") or "")
        for key in ("title", "raw_text", "final_text", "event_summary")
    )[:14000]


def _text(row: Any) -> str:
    return _raw_text(row).casefold()


def _numbers(value: str) -> list[float]:
    out: list[float] = []
    for match in _NUMBER_RE.finditer(value):
        token = (
            match.group(0)
            .casefold()
            .replace("відсотків", "")
            .replace("відсотки", "")
            .replace("відсоток", "")
            .replace("%", "")
            .strip()
        )
        try:
            number = float(token.replace(",", "."))
        except ValueError:
            continue
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


def _scientific_names(row: Any) -> set[str]:
    return {
        f"{match.group(1).casefold()} {match.group(2).casefold()}"
        for match in _BINOMIAL_RE.finditer(_raw_text(row))
    }


def _has_discovery_context(row: Any) -> bool:
    value = _text(row)
    return any(marker in value for marker in _DISCOVERY_MARKERS)


def _rare_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in _concept_sequence(value):
        term = str(token or "").casefold().strip(".'’-_")
        if len(term) < 7 or term in _RARE_STOP:
            continue
        if term.isdigit():
            continue
        terms.add(term)
    return terms


def event_fingerprint_same_event(
    current: Any,
    candidate: Any,
    *,
    scientific_names: bool = False,
    compound_events: bool = False,
    rare_terms: bool = False,
) -> tuple[bool, str]:
    """Configurable high-precision event equivalence.

    Baseline semantic matching remains global. Advanced scientific fingerprints are
    enabled only by the current channel settings. Concrete event names belong in
    regression fixtures, never in production rules.
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

    if scientific_names:
        shared_names = _scientific_names(current) & _scientific_names(candidate)
        if shared_names and _has_discovery_context(current) and _has_discovery_context(candidate):
            return True, "scientific-name event fingerprint " + ",".join(sorted(shared_names))

    concepts_a = set(_concept_sequence(left))
    concepts_b = set(_concept_sequence(right))
    shared = concepts_a & concepts_b
    containment = len(shared) / max(1, min(len(concepts_a), len(concepts_b)))
    long_shared = {item for item in shared if len(item) >= 6}
    numeric_pairs = _near_numeric_pairs(left, right)

    title_a = set(_concept_sequence(str(_value(current, "title", "") or "")))
    title_b = set(_concept_sequence(str(_value(candidate, "title", "") or "")))
    title_shared = title_a & title_b
    title_containment = len(title_shared) / max(1, min(len(title_a), len(title_b)))

    rare_shared: set[str] = set()
    if rare_terms:
        rare_shared = _rare_terms(left) & _rare_terms(right)

    if compound_events:
        corroboration = bool(numeric_pairs) or len(rare_shared) >= 3
        if (
            title_shared
            and len(shared) >= 8
            and containment >= 0.20
            and len(long_shared) >= 4
            and corroboration
        ):
            return True, (
                "compound subject+method+mechanism fingerprint "
                f"title={len(title_shared)}/{title_containment:.2f} "
                f"concepts={len(shared)}/{containment:.2f} "
                f"rare={len(rare_shared)} numbers={numeric_pairs[:3]}"
            )

        # Heavy paraphrases can lose the headline anchor. In that case demand a
        # substantially denser body fingerprint and independent corroboration.
        if (
            len(shared) >= 12
            and containment >= 0.28
            and len(long_shared) >= 6
            and corroboration
        ):
            return True, (
                "compound body event fingerprint "
                f"concepts={len(shared)}/{containment:.2f} "
                f"long={len(long_shared)} rare={len(rare_shared)} numbers={numeric_pairs[:3]}"
            )

    return False, (
        f"{reason}; advanced fingerprint "
        f"title={len(title_shared)}/{title_containment:.2f} "
        f"concepts={len(shared)}/{containment:.2f} long={len(long_shared)} "
        f"rare={len(rare_shared)} numbers={numeric_pairs[:3]}"
    )


class EventFingerprintDedupeEngine(SemanticDedupeEngine):
    """Semantic dedupe plus channel-configured advanced fingerprints."""

    def _find_duplicate(self, article_id: int, *, published_only: bool = False) -> DedupeResult:
        current = self.store.get_article(article_id)
        if current is None:
            raise KeyError(article_id)
        channel = self.store.get_channel(int(current["channel_id"]))
        configured_hours = int(channel.dedupe_window_hours if channel else 72)
        published_hours = int(
            channel.published_dedupe_window_hours
            if channel else 168
        )
        hours = max(1, published_hours if published_only else configured_hours)

        if published_only:
            age = f"-{hours} hours"
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

        scientific_names = bool(channel.dedupe_scientific_names) if channel else False
        compound_events = bool(channel.dedupe_compound_events) if channel else False
        rare_terms = bool(channel.dedupe_rare_terms) if channel else False

        for candidate in candidates:
            if str(candidate["decision"]) == str(Decision.DUPLICATE):
                continue
            same, match_reason = event_fingerprint_same_event(
                current,
                candidate,
                scientific_names=scientific_names,
                compound_events=compound_events,
                rare_terms=rare_terms,
            )
            if same:
                return DedupeResult("DUPLICATE", int(candidate["id"]), match_reason)
        return DedupeResult("SINGLE", None, "no confirmed same event")


__all__ = [
    "EventFingerprintDedupeEngine",
    "SemanticGuardedPublisher",
    "event_fingerprint_same_event",
]
