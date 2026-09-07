from __future__ import annotations

import difflib
import logging
import re
from typing import Any

LOG = logging.getLogger("telegram_autopilot.rc80")
_INSTALLED = False

_GENERIC = {
    "the","and","for","with","from","this","that","into","about","after","before","new","how","why","what",
    "ad","ads","advert","advertising","campaign","campaigns","creative","creatives","brand","brands","marketing",
    "media","design","story","stories","work","launch","launches","latest","live","says","say","reveals","revealed",
    "про","для","та","або","що","цей","ця","це","новий","нова","нове","реклама","кампанія","бренд","маркетинг",
}
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9][A-Za-zА-Яа-яІіЇїЄєҐґ0-9'’.-]{2,}")
_CODE_RE = re.compile(r"\b(?:[A-Za-zА-Яа-яІіЇїЄєҐґ]{1,12}[-_ ]?\d+[A-Za-z0-9-]*|\d+[A-Za-z]{1,8}\d*)\b", re.I)


def _v(row: Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _words(value: str) -> set[str]:
    out: set[str] = set()
    for token in _WORD_RE.findall(str(value or "")):
        low = token.casefold().strip(".'’-_")
        if len(low) >= 3 and low not in _GENERIC:
            out.add(low)
    return out


def _title_words(row: Any) -> set[str]:
    words = _words(str(_v(row, "title", "")))
    source_words = _words(str(_v(row, "source_name", "")))
    return words - source_words


def _body_words(row: Any) -> set[str]:
    text = str(_v(row, "raw_text", "") or _v(row, "teaser_text", "") or _v(row, "event_summary", ""))
    return _words(text[:5000])


def _codes(row: Any) -> set[str]:
    text = f"{_v(row,'title','')} {_v(row,'raw_text','')}"
    out: set[str] = set()
    for token in _CODE_RE.findall(text[:3000]):
        normalized = re.sub(r"[\s_-]+", "", token).casefold()
        if len(normalized) >= 3 and not re.fullmatch(r"(?:19|20)\d{2}", normalized):
            out.add(normalized)
    return out


def _local_duplicate_hit(current: Any, candidate: Any):
    from .event_dedupe import find_event_duplicate
    fake = [{
        "id": int(_v(candidate, "id", 0) or 0),
        "title": str(_v(candidate, "title", "")),
        "event_summary": str(_v(candidate, "raw_text", "") or _v(candidate, "event_summary", "")),
        "teaser_text": str(_v(candidate, "raw_text", "") or _v(candidate, "teaser_text", "")),
    }]
    try:
        return find_event_duplicate(
            str(_v(current, "title", "")),
            str(_v(current, "raw_text", "") or _v(current, "teaser_text", "") or _v(current, "event_summary", "")),
            fake,
        )
    except Exception:
        return None


def _guard_relation_rc80(current: Any, candidate: Any, relation: str, reason: str) -> tuple[str, str]:
    """AI may suggest a merge, but local evidence must confirm the same concrete event."""
    relation = str(relation or "").upper()
    if relation not in {"DUPLICATE", "UPDATE"}:
        return relation, reason

    au = str(_v(current, "normalized_url", "") or _v(current, "url", "")).strip()
    bu = str(_v(candidate, "normalized_url", "") or _v(candidate, "url", "")).strip()
    if au and bu and au == bu:
        return relation, f"{reason}; RC80 confirmed: same normalized URL"

    hit = _local_duplicate_hit(current, candidate)
    if hit is not None:
        return relation, f"{reason}; RC80 confirmed locally: {hit.reason}"

    # One source normally emits separate rows for separate stories. Do not allow
    # a broad AI/topic match to collapse them unless the high-precision local
    # duplicate detector above confirmed the event.
    sid_a = int(_v(current, "source_id", 0) or 0)
    sid_b = int(_v(candidate, "source_id", 0) or 0)
    if sid_a and sid_b and sid_a == sid_b:
        return "RELATED", f"RC80 blocked merge: different rows from the same source without local event confirmation; AI={relation}: {reason}"

    ac, bc = _codes(current), _codes(candidate)
    shared_codes = ac & bc
    if shared_codes and (ac - shared_codes) and (bc - shared_codes):
        return "RELATED", (
            "RC80 blocked merge: shared topic/version but conflicting strong event codes; "
            f"shared={','.join(sorted(shared_codes)[:4])}; A={','.join(sorted(ac-shared_codes)[:4])}; "
            f"B={','.join(sorted(bc-shared_codes)[:4])}; AI={relation}: {reason}"
        )

    at, bt = _title_words(current), _title_words(candidate)
    shared_title = at & bt
    title_containment = len(shared_title) / max(1, min(len(at), len(bt)))
    title_ratio = difflib.SequenceMatcher(
        None,
        " ".join(sorted(at)),
        " ".join(sorted(bt)),
    ).ratio() if at and bt else 0.0

    if len(shared_title) >= 3 and title_ratio >= 0.78:
        return relation, f"{reason}; RC80 confirmed by title anchors ratio={title_ratio:.2f}"
    if len(shared_title) >= 4 and title_containment >= 0.72:
        return relation, f"{reason}; RC80 confirmed by title containment={title_containment:.2f}"

    ab, bb = _body_words(current), _body_words(candidate)
    shared_body = ab & bb
    body_containment = len(shared_body) / max(1, min(len(ab), len(bb)))
    if len(shared_title) >= 2 and len(shared_body) >= 12 and body_containment >= 0.68:
        return relation, f"{reason}; RC80 confirmed by title+body event overlap={body_containment:.2f}"

    return "RELATED", (
        "RC80 blocked merge: AI/topic similarity did not prove the same concrete event; "
        f"title_shared={len(shared_title)}, title_containment={title_containment:.2f}, body_containment={body_containment:.2f}; "
        f"AI={relation}: {reason}"
    )


def _cluster_one_rc80(service: Any, channel: Any, row: Any) -> str:
    from . import rc66_clusters as clusters
    from .rc66_tags import row_tags, strong_overlap, v

    db = service.db
    article_id = int(v(row, "id", 0) or 0)
    if not article_id:
        return "skip"
    tags = row_tags(db, row, channel)
    matched = []
    for candidate in clusters._candidates(db, int(channel.id), article_id, int(getattr(channel, "dedupe_window_hours", 72) or 72)):
        status = str(v(candidate, "status", "") or "")
        # Never use a child of another cluster as a bridge into that cluster.
        if status == "clustered" or int(v(candidate, "cluster_parent_id", 0) or 0):
            continue
        ctags = row_tags(db, candidate, channel)
        overlap = strong_overlap(tags, ctags)
        if not overlap or all(x.startswith("minor:") for x in overlap):
            continue
        cid = int(v(candidate, "id", 0) or 0)
        bonus = 6 if status == "published" else 0
        matched.append((clusters._weight(overlap) + bonus, cid, candidate, ctags, overlap))
    matched.sort(key=lambda x: (x[0], x[1]), reverse=True)

    for _score, candidate_id, candidate, ctags, overlap in matched[:6]:
        cached = clusters._cached(db, int(channel.id), article_id, candidate_id)
        if cached:
            relation, reason = cached
            via = "cache"
        else:
            try:
                relation, reason = clusters._ai_relation(row, candidate, overlap)
                via = "ai"
            except Exception as exc:
                relation, reason = clusters._fallback_relation(row, candidate, tags, ctags)
                via = f"fallback:{exc}"

        original = relation
        relation, reason = _guard_relation_rc80(row, candidate, relation, reason)
        clusters._store(db, int(channel.id), article_id, candidate_id, relation, reason)
        service._audit(
            "rc80_dedupe", relation.lower(),
            f"candidate={candidate_id}; original={original}; overlap={','.join(sorted(overlap)[:8])}; {reason}; via={via}",
            channel_id=int(channel.id), article_id=article_id,
        )

        status = str(v(candidate, "status", "") or "")
        if status == "published" and relation == "DUPLICATE":
            db.update_article(
                article_id, status="duplicate", duplicate_of=candidate_id,
                reject_reason=f"RC80: дубль уже опублікованої події #{candidate_id}: {reason}",
                ai_provider="ai-dedupe", ai_model="rc80-event-guard",
            )
            return "duplicate"
        if status != "published" and relation in {"DUPLICATE", "UPDATE"}:
            cluster_id = int(v(candidate, "event_cluster_id", 0) or 0) or clusters._ensure_cluster(db, int(channel.id), candidate_id, ctags)
            canonical_id = clusters._attach(db, article_id, candidate, cluster_id)
            service._audit(
                "rc80_cluster", "merged",
                f"parent={canonical_id}; relation={relation}; cluster={cluster_id}; locally_confirmed=1",
                channel_id=int(channel.id), article_id=article_id,
            )
            return "clustered"

    clusters._ensure_cluster(db, int(channel.id), article_id, tags)
    return "single"


def repair_rc80_recent_clusters(db: Any, hours: int = 72) -> int:
    """One-time requeue of recent RC79 clustered children for stricter re-evaluation."""
    key = "rc80_recent_cluster_repair_done"
    with db.connect() as con:
        row = con.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        if row:
            return 0
        count_row = con.execute(
            "SELECT COUNT(*) FROM articles WHERE status='clustered' AND datetime(discovered_at)>=datetime('now', ?)",
            (f"-{max(1, int(hours))} hours",),
        ).fetchone()
        count = int(count_row[0] or 0) if count_row else 0
        con.execute(
            """UPDATE articles
               SET status='new', event_cluster_id=NULL, cluster_parent_id=NULL, duplicate_of=NULL,
                   reject_reason=NULL, last_error=NULL, processing_started_at=NULL, next_retry_at=NULL
               WHERE status='clustered' AND datetime(discovered_at)>=datetime('now', ?)""",
            (f"-{max(1, int(hours))} hours",),
        )
        con.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES(?,?)", (key, str(count)))
    LOG.info("RC80 repair: requeued %s recent clustered articles for strict event re-evaluation", count)
    return count


def install_rc80_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from . import rc66_clusters as clusters
    clusters.cluster_one = _cluster_one_rc80
    LOG.info(
        "RC80 installed: every AI/cache/fallback DUPLICATE or UPDATE must pass local event confirmation; "
        "same-source rows and clustered bridge candidates cannot be merged on topic similarity alone"
    )
    _INSTALLED = True
