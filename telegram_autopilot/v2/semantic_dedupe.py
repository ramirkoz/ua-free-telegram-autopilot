from __future__ import annotations

import re
from datetime import datetime, timezone
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

# RC49: municipal/community sites often republish the same ministry service notice
# with a different community name, photo and locally rewritten headline. Exact URL,
# title and phrase matching cannot catch those reliably. The extra lane below removes
# local-government wrapper vocabulary and compares conservative Ukrainian concept
# stems. It is deliberately restricted to cross-source community notices.
_COMMUNITY_MARKERS = (
    "громад", "міськ", "селищ", "сільськ", "район", "територіальн",
)
_COMMUNITY_WRAPPER = {
    "громад", "громада", "громади", "громаді", "громадою",
    "міськ", "міська", "міської", "міській", "міською",
    "селищн", "селищна", "селищної", "сільськ", "сільська", "сільської",
    "нагад", "нагадує", "розясню", "роз'ясню", "роз’ясню", "повідомл", "повідомляє",
    "інформ", "інформує", "мешкан", "жител", "уваг", "важлив", "актуальн",
    "можуть", "можна", "потрібно", "необхідно", "щодо", "порядок", "отриман",
}
_UK_SUFFIXES = (
    "уваннями", "юваннями", "ування", "ювання", "еннями", "аннями", "іннями",
    "ського", "ському", "ською", "ській", "ських", "ськими", "ський", "ська", "ське", "ські",
    "ними", "ного", "ному", "ною", "ній", "них", "ний", "на", "не", "ні",
    "ення", "ання", "іння", "енню", "анню", "інню",
    "ами", "ями", "ого", "ому", "ими", "ої", "ою", "ові", "еві", "ами", "ями",
    "ів", "їв", "ах", "ях", "ам", "ям", "ом", "ем", "ою", "ею",
    "и", "і", "ї", "а", "я", "у", "ю", "е",
)


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


def _concept_stem(token: str) -> str:
    value = str(token or "").casefold().strip(".'’-_")
    if len(value) < 4:
        return ""
    for suffix in _UK_SUFFIXES:
        if value.endswith(suffix) and len(value) - len(suffix) >= 4:
            value = value[:-len(suffix)]
            break
    return value


def _concept_sequence(value: str) -> list[str]:
    out: list[str] = []
    for token in _phrase_tokens(value):
        stem = _concept_stem(token)
        if len(stem) < 4 or stem in _COMMUNITY_WRAPPER:
            continue
        if any(stem.startswith(wrapper) and len(wrapper) >= 5 for wrapper in _COMMUNITY_WRAPPER):
            continue
        out.append(stem)
    return out


def _concept_overlap(left: str, right: str) -> tuple[int, float]:
    a = set(_concept_sequence(left))
    b = set(_concept_sequence(right))
    if not a or not b:
        return 0, 0.0
    shared = a & b
    return len(shared), len(shared) / max(1, min(len(a), len(b)))


def _concept_ngrams(value: str, size: int) -> set[tuple[str, ...]]:
    tokens = _concept_sequence(value)
    if len(tokens) < size:
        return set()
    return {tuple(tokens[index:index + size]) for index in range(0, len(tokens) - size + 1)}


def _looks_like_community_notice(row: Any) -> bool:
    head = (
        str(_value(row, "source_name", "")) + "\n" +
        str(_value(row, "title", ""))
    ).casefold()
    return any(marker in head for marker in _COMMUNITY_MARKERS)


def _community_notice_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    """Catch cross-community rewrites of one public-service/official notice.

    This is intentionally not a generic topic-similarity rule. Both rows must look
    like municipal/community notices, come from different sources, share the same
    substantive concept fingerprint, and have body/final-text corroboration.
    """
    if not (_looks_like_community_notice(current) and _looks_like_community_notice(candidate)):
        return False, "not a pair of community notices"
    if int(_value(current, "source_id", 0) or 0) == int(_value(candidate, "source_id", 0) or -1):
        return False, "same source"

    title_a = str(_value(current, "title", "") or "")
    title_b = str(_value(candidate, "title", "") or "")
    title_shared, title_containment = _concept_overlap(title_a, title_b)

    body_a = str(_value(current, "raw_text", "") or "")[:5000]
    body_b = str(_value(candidate, "raw_text", "") or "")[:5000]
    body_shared, body_containment = _concept_overlap(body_a, body_b)
    body_bigrams = len(_concept_ngrams(body_a, 2) & _concept_ngrams(body_b, 2))

    # Different municipalities commonly change the first sentence and photo while
    # copying/paraphrasing the same ministry instruction. Three topical headline
    # concepts plus substantial body agreement is strong evidence in this narrow lane.
    if (
        title_shared >= 3
        and title_containment >= 0.38
        and body_shared >= 8
        and body_containment >= 0.30
        and body_bigrams >= 1
    ):
        return True, (
            "cross-community public-service fingerprint "
            f"title={title_shared}/{title_containment:.2f} "
            f"body={body_shared}/{body_containment:.2f} bigrams={body_bigrams}"
        )

    # At READY/PUBLISHED time both rows have normalized Ukrainian copy. This catches
    # heavier paraphrases where source pages differ structurally but the actual notice
    # is still the same. Keep the threshold high enough not to merge ordinary local
    # stories that merely concern the same audience.
    final_a = str(_value(current, "final_text", "") or "")
    final_b = str(_value(candidate, "final_text", "") or "")
    if final_a.strip() and final_b.strip():
        final_shared, final_containment = _concept_overlap(final_a, final_b)
        final_bigrams = len(_concept_ngrams(final_a, 2) & _concept_ngrams(final_b, 2))
        if (
            final_shared >= 7
            and final_containment >= 0.38
            and final_bigrams >= 2
            and (title_shared >= 2 or body_shared >= 6)
        ):
            return True, (
                "final-text cross-community notice duplicate "
                f"final={final_shared}/{final_containment:.2f} bigrams={final_bigrams} "
                f"title={title_shared} body={body_shared}"
            )

    return False, (
        "community notices differ "
        f"title={title_shared}/{title_containment:.2f} "
        f"body={body_shared}/{body_containment:.2f} bigrams={body_bigrams}"
    )


_INCIDENT_ACTION_GROUPS = {
    "attack": ("атак","удар","обстр","прильот","влуч","дрон","шахед","ракет","strike","attack","shell","drone","missile"),
    "damage": ("пошкод","зруйн","руйнув","вибит","damage","destroy"),
    "fire": ("пожеж","займан","fire","burn"),
    "casualty": ("поран","постраж","загин","евакую","injur","wound","evacuat","killed"),
}
_INCIDENT_TARGET_GROUPS = {
    "medical": ("медич","лікар","лікарн","шпитал","клінік","hospital","medical","clinic"),
    "residential": ("житлов","будин","квартир","residential","house","apartment"),
    "infrastructure": ("інфраструкт","енерг","підстанц","об'єкт","об’єкт","infrastructure","energy"),
    "education": ("школ","універс","освіт","school","university","education"),
}
_INCIDENT_GENERIC = {"російськ","росіян","ворож","військ","міст","област","район","сьогодні","вранц","зранк","наслідк","інформац","уточню","служб","місц","людин","допомог","атака","удар","обстріл"}

def _incident_groups(value: str, groups: dict[str, tuple[str, ...]]) -> set[str]:
    low = str(value or "").casefold()
    return {name for name, roots in groups.items() if any(root in low for root in roots)}

def _incident_time(row: Any) -> datetime | None:
    raw = str(_value(row, "source_published_at", "") or _value(row, "discovered_at", "") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def _breaking_incident_same_event(current: Any, candidate: Any) -> tuple[bool, str]:
    same_source = int(_value(current, "source_id", 0) or 0) == int(_value(candidate, "source_id", 0) or -1)
    left = str(_value(current, "title", "")) + "\n" + str(_value(current, "raw_text", ""))[:2200]
    right = str(_value(candidate, "title", "")) + "\n" + str(_value(candidate, "raw_text", ""))[:2200]
    shared_actions = _incident_groups(left, _INCIDENT_ACTION_GROUPS) & _incident_groups(right, _INCIDENT_ACTION_GROUPS)
    shared_targets = _incident_groups(left, _INCIDENT_TARGET_GROUPS) & _incident_groups(right, _INCIDENT_TARGET_GROUPS)
    if not shared_actions or not shared_targets:
        return False, "incident action/target mismatch"
    ta, tb = _incident_time(current), _incident_time(candidate)
    if ta is not None and tb is not None and abs((ta - tb).total_seconds()) > 3 * 3600:
        return False, "incident outside three-hour clustering window"
    ca = set(_concept_sequence(str(_value(current, "title", "")) + " " + str(_value(current, "raw_text", ""))[:1800]))
    cb = set(_concept_sequence(str(_value(candidate, "title", "")) + " " + str(_value(candidate, "raw_text", ""))[:1800]))
    shared = {x for x in (ca & cb) if len(x) >= 5 and x not in _INCIDENT_GENERIC and not any(x.startswith(g) for g in _INCIDENT_GENERIC)}
    required = 3 if same_source else 2
    if len(shared) >= required:
        return True, (
            "breaking-incident cluster "
            f"actions={','.join(sorted(shared_actions))} targets={','.join(sorted(shared_targets))} "
            f"anchors={','.join(sorted(shared)[:6])}"
        )
    return False, f"incident anchors insufficient: {len(shared)}"


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

    incident_same, incident_reason = _breaking_incident_same_event(current, candidate)
    if incident_same:
        return True, incident_reason

    same_source = int(_value(current, "source_id", 0) or 0) == int(_value(candidate, "source_id", 0) or -1)
    if same_source:
        return False, reason

    community_same, community_reason = _community_notice_same_event(current, candidate)
    if community_same:
        return True, community_reason

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
        f"{reason}; {community_reason}; semantic phrase overlap title={title_shared} "
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
