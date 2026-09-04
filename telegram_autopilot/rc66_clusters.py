from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from .rc66_tags import StoryTags, row_tags, strong_overlap, v

LOG = logging.getLogger("telegram_autopilot.rc66.cluster")
RELATIONS = {"DUPLICATE", "UPDATE", "RELATED", "DIFFERENT"}
MAX_CLUSTER_SOURCES = 4


def _parse_relation(raw: str) -> tuple[str, str]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw or "").strip(), flags=re.I)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("RC66 dedupe judge: invalid JSON")
    obj = json.loads(text[a:b + 1])
    relation = str(obj.get("relation") or "").upper().strip()
    if relation not in RELATIONS:
        raise ValueError("RC66 dedupe judge: invalid relation")
    return relation, " ".join(str(obj.get("reason") or "").split())[:600]


def _ai_relation(current: Any, candidate: Any, overlap: set[str]) -> tuple[str, str]:
    from .production_pipeline import run_ai
    prompt = f'''Ти редакторський дедуплікатор новин. Порівняй ДВІ історії. Спільні сильні теги: {', '.join(sorted(overlap)[:12])}.
Поверни ТІЛЬКИ JSON: {{"relation":"DUPLICATE|UPDATE|RELATED|DIFFERENT","reason":"коротко"}}.
DUPLICATE = та сама конкретна подія/кейс, суттєво нового немає.
UPDATE = та сама конкретна подія, але є істотно новий факт/етап.
RELATED = одна тема/технологія/тип події, але інша конкретна історія. Різні пацієнти, люди, компанії або кейси зазвичай RELATED, не DUPLICATE.
DIFFERENT = випадковий або слабкий тематичний збіг.
A TITLE: {str(v(current,'title',''))[:700]}
A TEXT: {' '.join(str(v(current,'raw_text','')).split())[:2200]}
B TITLE: {str(v(candidate,'title',''))[:700]}
B TEXT: {' '.join(str(v(candidate,'raw_text','')).split())[:2200]}'''
    def validator(value: str) -> None:
        _parse_relation(value)
    result = run_ai(
        prompt, validator=validator, max_output_tokens=180, local_prompt=prompt, local_max_output_tokens=180,
        cloud_timeout_seconds=18, local_timeout_seconds=12, task_timeout_seconds=45, local_repair=False,
        suppress_provider_on_quota=False, allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
    )
    return _parse_relation(result.text)


def _fallback_relation(current: Any, candidate: Any, a: StoryTags, b: StoryTags) -> tuple[str, str]:
    from .event_dedupe import find_event_duplicate
    fake = [{
        "id": int(v(candidate, "id", 0) or 0), "title": str(v(candidate, "title", "")),
        "event_summary": str(v(candidate, "event_summary", "") or v(candidate, "raw_text", "")),
        "teaser_text": str(v(candidate, "teaser_text", "") or v(candidate, "raw_text", "")),
        "published_at": str(v(candidate, "published_at", "") or v(candidate, "discovered_at", "")),
    }]
    try:
        hit = find_event_duplicate(str(v(current, "title", "")), str(v(current, "raw_text", "")), fake)
    except Exception:
        hit = None
    if hit is not None:
        return "DUPLICATE", "локальний semantic fallback вважає матеріали тією самою подією"
    if a.minor and a.minor == b.minor:
        return "RELATED", "спільна вузька тема без доказу тієї самої конкретної події"
    return "DIFFERENT", "AI недоступний; локальний fallback не підтвердив ту саму подію"


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _cached(db: Any, channel_id: int, a: int, b: int) -> tuple[str, str] | None:
    low, high = _pair(a, b)
    try:
        with db.connect() as con:
            row = con.execute("SELECT relation,reason FROM event_relations WHERE channel_id=? AND article_low=? AND article_high=?", (channel_id, low, high)).fetchone()
        if row and str(row[0] or "") in RELATIONS:
            return str(row[0]), str(row[1] or "")
    except Exception:
        pass
    return None


def _store(db: Any, channel_id: int, a: int, b: int, relation: str, reason: str) -> None:
    if relation not in RELATIONS:
        return
    low, high = _pair(a, b)
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        with db.connect() as con:
            con.execute(
                '''INSERT INTO event_relations(channel_id,article_low,article_high,relation,reason,checked_at) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(channel_id,article_low,article_high) DO UPDATE SET relation=excluded.relation,reason=excluded.reason,checked_at=excluded.checked_at''',
                (channel_id, low, high, relation, str(reason or "")[:1000], stamp),
            )
    except Exception:
        pass


def _weight(overlap: set[str]) -> int:
    score = 0
    for item in overlap:
        score += 5 if item.startswith("entity:") else 4 if item.startswith("spec:") else 3 if item.startswith("minor:") else 2
    return score


def _candidates(db: Any, channel_id: int, article_id: int, hours: int) -> list[Any]:
    with db.connect() as con:
        return con.execute(
            '''SELECT a.*,s.name AS source_name FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.channel_id=? AND a.id<>? AND a.status IN ('published','new','retry','processing','ready','clustered')
                 AND datetime(a.discovered_at)>=datetime('now', ?) ORDER BY a.id DESC LIMIT 80''',
            (channel_id, article_id, f"-{max(1, hours)} hours"),
        ).fetchall()


def _ensure_cluster(db: Any, channel_id: int, article_id: int, tags: StoryTags) -> int:
    with db.connect() as con:
        row = con.execute("SELECT event_cluster_id FROM articles WHERE id=?", (article_id,)).fetchone()
        if row and int(row[0] or 0):
            return int(row[0])
        basis = "|".join(sorted(tags.strong())[:20]) or f"article:{article_id}"
        key = hashlib.sha1(f"{channel_id}|{basis}|{article_id}".encode()).hexdigest()
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        cur = con.execute("INSERT INTO event_clusters(channel_id,cluster_key,canonical_article_id,created_at,updated_at) VALUES(?,?,?,?,?)", (channel_id, key, article_id, stamp, stamp))
        cluster_id = int(cur.lastrowid)
        con.execute("UPDATE articles SET event_cluster_id=?,cluster_parent_id=NULL WHERE id=?", (cluster_id, article_id))
        return cluster_id


def _canonical_for_cluster(db: Any, cluster_id: int, fallback: Any) -> Any:
    try:
        with db.connect() as con:
            row = con.execute(
                '''SELECT a.*,s.name AS source_name FROM event_clusters e JOIN articles a ON a.id=e.canonical_article_id
                   JOIN sources s ON s.id=a.source_id WHERE e.id=?''', (cluster_id,),
            ).fetchone()
        return row or fallback
    except Exception:
        return fallback


def _attach(db: Any, current_id: int, candidate: Any, cluster_id: int) -> int:
    canonical = _canonical_for_cluster(db, cluster_id, candidate)
    canonical_id = int(v(canonical, "id", 0) or 0)
    canonical_status = str(v(canonical, "status", "") or "")
    with db.connect() as con:
        con.execute("UPDATE articles SET event_cluster_id=?,cluster_parent_id=?,status='clustered',reject_reason=NULL WHERE id=?", (cluster_id, canonical_id, current_id))
        con.execute("UPDATE event_clusters SET updated_at=? WHERE id=?", (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), cluster_id))
        if canonical_status == "ready":
            con.execute(
                '''UPDATE articles SET status='new',ready_at=NULL,rewrite_text='',headline_uk='',teaser_text='',full_article_uk='',
                   event_key='',event_summary='',ai_provider='',ai_model='',last_error=NULL,retry_count=0,next_retry_at=NULL WHERE id=?''', (canonical_id,),
            )
    return canonical_id


def cluster_one(service: Any, channel: Any, row: Any) -> str:
    db = service.db
    article_id = int(v(row, "id", 0) or 0)
    if not article_id:
        return "skip"
    tags = row_tags(db, row, channel)
    matched = []
    for candidate in _candidates(db, int(channel.id), article_id, int(getattr(channel, "dedupe_window_hours", 72) or 72)):
        ctags = row_tags(db, candidate, channel)
        overlap = strong_overlap(tags, ctags)
        if not overlap:
            continue
        status = str(v(candidate, "status", "") or "")
        cid = int(v(candidate, "id", 0) or 0)
        bonus = 6 if status == "published" else 0
        matched.append((_weight(overlap) + bonus, cid, candidate, ctags, overlap))
    matched.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for _score, candidate_id, candidate, ctags, overlap in matched[:6]:
        cached = _cached(db, int(channel.id), article_id, candidate_id)
        if cached:
            relation, reason = cached; via = "cache"
        else:
            try:
                relation, reason = _ai_relation(row, candidate, overlap); via = "ai"
            except Exception as exc:
                relation, reason = _fallback_relation(row, candidate, tags, ctags); via = f"fallback:{exc}"
            _store(db, int(channel.id), article_id, candidate_id, relation, reason)
        service._audit("rc66_dedupe", relation.lower(), f"candidate={candidate_id}; overlap={','.join(sorted(overlap)[:8])}; {reason}; via={via}", channel_id=int(channel.id), article_id=article_id)
        status = str(v(candidate, "status", "") or "")
        if status == "published" and relation == "DUPLICATE":
            db.update_article(article_id, status="duplicate", duplicate_of=candidate_id, reject_reason=f"RC66: дубль уже опублікованої події #{candidate_id}: {reason}", ai_provider="ai-dedupe", ai_model="rc66-event-judge")
            return "duplicate"
        if status != "published" and relation in {"DUPLICATE", "UPDATE"}:
            cluster_id = int(v(candidate, "event_cluster_id", 0) or 0) or _ensure_cluster(db, int(channel.id), candidate_id, ctags)
            canonical_id = _attach(db, article_id, candidate, cluster_id)
            service._audit("rc66_cluster", "merged", f"parent={canonical_id}; relation={relation}; cluster={cluster_id}", channel_id=int(channel.id), article_id=article_id)
            return "clustered"
    _ensure_cluster(db, int(channel.id), article_id, tags)
    return "single"


def prepare_clusters(service: Any, channel: Any) -> None:
    try:
        rows = service.db.pending_articles(int(channel.id), limit=24)
    except Exception:
        return
    for row in list(rows)[:16]:
        if str(v(row, "status", "") or "") not in {"new", "retry"}:
            continue
        try:
            cluster_one(service, channel, row)
        except Exception as exc:
            LOG.warning("RC66 cluster failed channel_id=%s article_id=%s: %s", channel.id, v(row, "id", "?"), exc)


def cluster_members(db: Any, row: Any, limit: int = MAX_CLUSTER_SOURCES) -> list[Any]:
    cluster_id = int(v(row, "event_cluster_id", 0) or 0)
    if not cluster_id:
        return [row]
    with db.connect() as con:
        rows = con.execute(
            '''SELECT a.*,s.name AS source_name,s.priority AS source_priority FROM articles a JOIN sources s ON s.id=a.source_id
               WHERE a.event_cluster_id=? ORDER BY COALESCE(a.source_published_at,a.discovered_at) DESC,a.id DESC LIMIT ?''',
            (cluster_id, max(1, limit)),
        ).fetchall()
    return list(rows) or [row]


def composite_row(db: Any, row: Any) -> Any:
    members = cluster_members(db, row)
    if len(members) <= 1:
        return row
    data = dict(row)
    blocks = []
    for i, member in enumerate(members, 1):
        blocks.append(f"SOURCE {i}: {v(member,'source_name','')}\nURL: {v(member,'url','')}\nTITLE: {v(member,'title','')}\nTEXT: {' '.join(str(v(member,'raw_text','')).split())[:3600]}")
    data["raw_text"] = "\n\n".join(blocks)
    data["source_name"] = f"{len(members)} джерела"
    for member in members:
        if v(member, "source_published_at", ""):
            data["source_published_at"] = v(member, "source_published_at", ""); break
    return data


def source_urls(db: Any, row: Any) -> list[str]:
    urls: list[str] = []
    for member in cluster_members(db, row):
        url = str(v(member, "url", "") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls[:MAX_CLUSTER_SOURCES]
