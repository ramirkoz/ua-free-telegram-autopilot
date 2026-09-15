from __future__ import annotations

import re
from typing import Any

from .dedupe import DedupeEngine, DedupeResult, _merge_media, _same_event, _title_words
from .domain import Decision, Stage
from .loghub import event
from .publisher import Publisher
from .storage import V2Store

_PHRASE_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9][A-Za-zА-Яа-яІіЇїЄєҐґ0-9'’.-]{1,}")
_PHRASE_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "into", "about", "after", "before", "new", "how", "why",
    "what", "who", "where", "when", "a", "an", "of", "to", "in", "on", "is", "are", "was", "were", "be", "been",
    "being", "as", "at", "by", "or", "but", "if", "then", "than", "their", "there", "they", "it", "its", "his",
    "her", "he", "she", "you", "your", "we", "our", "not", "no", "do", "does", "did", "can", "could", "would",
    "should", "may", "might", "will", "just", "over", "under", "up", "out", "more", "most", "less",
    "та", "і", "й", "або", "але", "що", "це", "цей", "ця", "ці", "для", "про", "від", "до", "у", "в", "на",
    "з", "із", "за", "як", "не", "такий", "нова", "новий", "нове",
}


def _value(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _phrase_tokens(value: str) -> list[str]:
    out: list[str] = []
    for token in _PHRASE_WORD_RE.findall(str(value or "").casefold()):
        normalized = token.strip(".'’-_")
        if len(normalized) >= 3 and normalized not in _PHRASE_STOP:
            out.append(normalized)
    return out


def _phrase_ngrams(value: str, size: int) -> set[tuple[str, ...]]:
    tokens = _phrase_tokens(value)
    if len(tokens) < size:
        return set()
    return {tuple(tokens[index:index + size]) for index in range(0, len(tokens) - size + 1)}


def _word_overlap(left: str, right: str) -> tuple[int, float]:
    a = set(_phrase_tokens(left))
    b = set(_phrase_tokens(right))
    if not a or not b:
        return 0, 0.0
    shared = a & b
    return len(shared), len(shared) / max(1, min(len(a), len(b)))


def semantic_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """High-precision event matching layered on top of the RC31 deterministic guard.

    The extra lane is deliberately phrase-based. It catches two publishers describing
    the same concrete study/court case/event while refusing broad same-topic stories
    that merely share a product or category.
    """
    same, reason = _same_event(current, candidate)
    if same:
        return True, reason
    if reason.startswith("conflicting strong event/version/product codes"):
        return False, reason

    same_source = int(_value(current, "source_id", 0) or 0) == int(_value(candidate, "source_id", 0) or -1)
    if same_source:
        return False, reason

    title_shared = len(_title_words(current) & _title_words(candidate))
    raw_a = str(_value(current, "raw_text", "") or "")
    raw_b = str(_value(candidate, "raw_text", "") or "")
    body_shared, body_containment = _word_overlap(raw_a, raw_b)
    shared_bigrams = len(_phrase_ngrams(raw_a, 2) & _phrase_ngrams(raw_b, 2))
    shared_trigrams = len(_phrase_ngrams(raw_a, 3) & _phrase_ngrams(raw_b, 3))

    # Same research, court case, incident or announcement described independently.
    if (
        title_shared >= 3
        and body_shared >= 40
        and body_containment >= 0.28
        and shared_bigrams >= 10
        and shared_trigrams >= 3
    ):
        return True, (
            "semantic event phrase overlap "
            f"title={title_shared} body={body_shared}/{body_containment:.2f} "
            f"bigrams={shared_bigrams} trigrams={shared_trigrams}"
        )

    # Two-anchor headlines need stronger body evidence. This catches a concrete
    # court ruling/regulatory action reported with different headlines without
    # collapsing ordinary same-product coverage.
    if (
        title_shared >= 2
        and body_shared >= 50
        and body_containment >= 0.32
        and shared_bigrams >= 16
        and shared_trigrams >= 6
    ):
        return True, (
            "two-anchor event fingerprint "
            f"title={title_shared} body={body_shared}/{body_containment:.2f} "
            f"bigrams={shared_bigrams} trigrams={shared_trigrams}"
        )

    # Syndicated/re-written reports can have almost unrelated headlines. Require a
    # much stronger body phrase fingerprint before treating them as one event.
    if (
        body_shared >= 60
        and body_containment >= 0.35
        and shared_bigrams >= 24
        and shared_trigrams >= 10
    ):
        return True, (
            "strong syndicated event fingerprint "
            f"body={body_shared}/{body_containment:.2f} "
            f"bigrams={shared_bigrams} trigrams={shared_trigrams}"
        )

    # READY articles already have the Ukrainian final text. Use it only as a
    # corroborating signal and never without meaningful overlap in the source copy.
    final_a = str(_value(current, "final_text", "") or "")
    final_b = str(_value(candidate, "final_text", "") or "")
    if final_a.strip() and final_b.strip() and title_shared >= 1 and shared_bigrams >= 5:
        final_shared, final_containment = _word_overlap(final_a, final_b)
        final_bigrams = len(_phrase_ngrams(final_a, 2) & _phrase_ngrams(final_b, 2))
        final_trigrams = len(_phrase_ngrams(final_a, 3) & _phrase_ngrams(final_b, 3))
        if (
            final_shared >= 14
            and final_containment >= 0.17
            and final_bigrams >= 4
            and final_trigrams >= 1
        ):
            return True, (
                "final-text corroborated event duplicate "
                f"final={final_shared}/{final_containment:.2f} "
                f"bigrams={final_bigrams} trigrams={final_trigrams}"
            )

    return False, (
        f"{reason}; semantic phrase overlap title={title_shared} "
        f"body={body_shared}/{body_containment:.2f} "
        f"bigrams={shared_bigrams} trigrams={shared_trigrams}"
    )


class SemanticDedupeEngine(DedupeEngine):
    """Deduplicate both during ingest and again at the final publication gate."""

    def _find_duplicate(self, article_id: int, *, published_only: bool = False) -> DedupeResult:
        current = self.store.get_article(article_id)
        if current is None:
            raise KeyError(article_id)
        channel = self.store.get_channel(int(current["channel_id"]))
        hours = int(channel.dedupe_window_hours if channel else 72)

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
                       LIMIT 350""",
                    (int(current["channel_id"]), int(article_id), age),
                ).fetchall()
        else:
            candidates = self._candidate_rows(int(current["channel_id"]), int(article_id), hours)

        for candidate in candidates:
            if str(candidate["decision"]) == str(Decision.DUPLICATE):
                continue
            same, reason = semantic_same_event(current, candidate)
            if same:
                return DedupeResult("DUPLICATE", int(candidate["id"]), reason)
        return DedupeResult("SINGLE", None, "no confirmed same event")

    def evaluate(self, article_id: int) -> DedupeResult:
        result = self._find_duplicate(article_id, published_only=False)
        if result.relation == "DUPLICATE" and result.duplicate_of:
            current = self.store.get_article(article_id)
            candidate = self.store.get_article(result.duplicate_of)
            self._mark_duplicate(article_id, result.duplicate_of, result.reason)
            if current is not None and candidate is not None:
                _merge_media(self.store, result.duplicate_of, current)
            event(
                "editorial", "semantic duplicate confirmed",
                channel_id=int(current["channel_id"] if current else 0),
                article_id=article_id, duplicate_of=result.duplicate_of, reason=result.reason,
            )
            return result
        self.store.update_article(article_id, stage=str(Stage.DEDUPED))
        return result

    def prepublish(self, article_id: int) -> DedupeResult:
        current = self.store.get_article(article_id)
        if current is None:
            raise KeyError(article_id)
        if str(current["stage"]) != str(Stage.READY) or str(current["decision"]) != str(Decision.PUBLISH):
            return DedupeResult("SINGLE", None, "article is not READY/PUBLISH")
        result = self._find_duplicate(article_id, published_only=True)
        if result.relation == "DUPLICATE" and result.duplicate_of:
            self.store.mark_duplicate(
                article_id,
                result.duplicate_of,
                f"Pre-publish semantic duplicate of #{result.duplicate_of}: {result.reason}",
            )
            event(
                "publish", "semantic duplicate publication blocked", level=30,
                channel_id=int(current["channel_id"]), article_id=article_id,
                duplicate_of=result.duplicate_of, reason=result.reason,
            )
        return result

    def reconcile_ready_against_published(self, *, limit_per_channel: int = 350) -> int:
        blocked = 0
        for channel in self.store.list_channels(enabled_only=True):
            channel_id = int(channel["id"])
            with self.store.connect() as con:
                rows = con.execute(
                    """SELECT id FROM articles
                       WHERE channel_id=? AND stage='READY' AND decision='PUBLISH'
                       ORDER BY datetime(CASE WHEN ready_at<>'' THEN ready_at ELSE discovered_at END) ASC,id ASC
                       LIMIT ?""",
                    (channel_id, max(1, int(limit_per_channel))),
                ).fetchall()
            for row in rows:
                result = self.prepublish(int(row["id"]))
                if result.relation == "DUPLICATE":
                    blocked += 1
        if blocked:
            event("publish", "stale READY duplicates reconciled", level=30, count=blocked)
        return blocked


class SemanticGuardedPublisher(Publisher):
    def __init__(self, store: V2Store, dedupe: SemanticDedupeEngine | None = None):
        super().__init__(store)
        self.semantic_dedupe = dedupe or SemanticDedupeEngine(store)

    def publish_one(self, article_id: int, heartbeat=None) -> str:
        result = self.semantic_dedupe.prepublish(article_id)
        if result.relation == "DUPLICATE":
            return "DUPLICATE_PUBLISHED"
        return super().publish_one(article_id, heartbeat=heartbeat)
