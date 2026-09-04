from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from . import rc66_clusters as clusters
from . import rc66_editorial_queue as rc66
from .rc66_tags import row_tags, strong_overlap, v

LOG = logging.getLogger("telegram_autopilot.rc67")
_INSTALLED = False
_PREV: dict[str, Any] = {}
_TARGET = threading.local()


STATUS_LABELS = {
    "new": "Новий",
    "ready": "Готовий",
    "clustered": "Об'єднано",
    "duplicate": "Дубль",
    "retry": "Повторна обробка",
    "processing": "Обробка",
    "telegram_writing": "Публікація",
    "published": "Опубліковано",
    "rejected": "Відхилено",
    "error": "Помилка",
    "baseline": "Базовий",
}


def _workers(service: Any, name: str) -> dict[int, threading.Thread]:
    attr = f"_rc67_{name}_workers"
    value = getattr(service, attr, None)
    if value is None:
        value = {}
        setattr(service, attr, value)
    return value


def _worker_lock(service: Any) -> threading.RLock:
    lock = getattr(service, "_rc67_worker_lock", None)
    if lock is None:
        lock = threading.RLock()
        setattr(service, "_rc67_worker_lock", lock)
    return lock


def _pending_target(db: Any, channel_id: int, limit: int = 20):
    rows = _PREV["pending"](db, int(channel_id), max(30, int(limit)))
    target = getattr(_TARGET, "article_id", None)
    if target is None:
        return rows[:limit]
    return [row for row in rows if int(v(row, "id", 0) or 0) == int(target)][:1]


def _worth_ai(overlap: set[str]) -> bool:
    if not overlap:
        return False
    entities = [x for x in overlap if x.startswith("entity:")]
    specifics = [x for x in overlap if x.startswith("spec:")]
    minors = [x for x in overlap if x.startswith("minor:")]
    keywords = [x for x in overlap if x.startswith("keyword:")]
    if entities:
        return True
    if minors and (specifics or keywords):
        return True
    if specifics and (keywords or len(specifics) >= 2):
        return True
    if len(keywords) >= 2:
        return True
    return False


def _fast_ai_relation(current: Any, candidate: Any, overlap: set[str]) -> tuple[str, str]:
    from .production_pipeline import run_ai

    prompt = f'''Ти редакторський дедуплікатор новин. Порівняй ДВІ історії. Спільні сильні теги: {', '.join(sorted(overlap)[:10])}.
Поверни ТІЛЬКИ JSON: {{"relation":"DUPLICATE|UPDATE|RELATED|DIFFERENT","reason":"коротко"}}.
DUPLICATE = та сама конкретна подія/кейс, суттєво нового немає.
UPDATE = та сама конкретна подія, але є істотно новий факт/етап.
RELATED = одна тема/технологія/тип події, але інша конкретна історія. Різні пацієнти, люди, компанії або кейси зазвичай RELATED, не DUPLICATE.
DIFFERENT = випадковий або слабкий тематичний збіг.
A TITLE: {str(v(current,'title',''))[:700]}
A TEXT: {' '.join(str(v(current,'raw_text','')).split())[:1800]}
B TITLE: {str(v(candidate,'title',''))[:700]}
B TEXT: {' '.join(str(v(candidate,'raw_text','')).split())[:1800]}'''

    def validator(value: str) -> None:
        clusters._parse_relation(value)

    result = run_ai(
        prompt,
        validator=validator,
        max_output_tokens=160,
        local_prompt=prompt,
        local_max_output_tokens=160,
        cloud_timeout_seconds=8,
        local_timeout_seconds=6,
        task_timeout_seconds=15,
        local_repair=False,
        suppress_provider_on_quota=False,
        allowed_providers={"codex", "gemini", "groq", "nvidia", "cloudflare", "local"},
    )
    return clusters._parse_relation(result.text)


def _safe_attach(db: Any, current_id: int, candidate: Any, cluster_id: int) -> tuple[int, str]:
    canonical = clusters._canonical_for_cluster(db, cluster_id, candidate)
    canonical_id = int(v(canonical, "id", 0) or 0)
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with db.connect() as con:
        state = con.execute("SELECT status FROM articles WHERE id=?", (canonical_id,)).fetchone()
        status = str(state[0] or "") if state else ""
        if status == "published":
            return canonical_id, status
        con.execute(
            "UPDATE articles SET event_cluster_id=?,cluster_parent_id=?,status='clustered',reject_reason=NULL WHERE id=?",
            (cluster_id, canonical_id, current_id),
        )
        con.execute("UPDATE event_clusters SET updated_at=? WHERE id=?", (stamp, cluster_id))
        con.execute(
            '''UPDATE articles SET status='new',ready_at=NULL,rewrite_text='',headline_uk='',teaser_text='',full_article_uk='',
               event_key='',event_summary='',ai_provider='',ai_model='',last_error=NULL,retry_count=0,next_retry_at=NULL
               WHERE id=? AND status='ready' ''',
            (canonical_id,),
        )
    return canonical_id, status


def _fast_cluster_one(service: Any, channel: Any, row: Any) -> str:
    db = service.db
    article_id = int(v(row, "id", 0) or 0)
    if not article_id:
        return "skip"

    tags = row_tags(db, row, channel)
    ranked: list[tuple[int, int, Any, Any, set[str]]] = []
    for candidate in clusters._candidates(db, int(channel.id), article_id, int(getattr(channel, "dedupe_window_hours", 72) or 72)):
        ctags = row_tags(db, candidate, channel)
        overlap = strong_overlap(tags, ctags)
        if not _worth_ai(overlap):
            continue
        status = str(v(candidate, "status", "") or "")
        score = clusters._weight(overlap) + (8 if status == "published" else 0)
        ranked.append((score, int(v(candidate, "id", 0) or 0), candidate, ctags, overlap))

    if not ranked:
        clusters._ensure_cluster(db, int(channel.id), article_id, tags)
        return "single"

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _score, candidate_id, candidate, ctags, overlap = ranked[0]
    cached = clusters._cached(db, int(channel.id), article_id, candidate_id)
    if cached:
        relation, reason = cached
        via = "cache"
    else:
        try:
            relation, reason = _fast_ai_relation(row, candidate, overlap)
            via = "ai-fast"
        except Exception as exc:
            relation, reason = clusters._fallback_relation(row, candidate, tags, ctags)
            via = f"fallback:{exc}"
        clusters._store(db, int(channel.id), article_id, candidate_id, relation, reason)

    service._audit(
        "rc67_dedupe",
        relation.lower(),
        f"candidate={candidate_id}; overlap={','.join(sorted(overlap)[:8])}; {reason}; via={via}",
        channel_id=int(channel.id),
        article_id=article_id,
    )

    fresh_candidate = db.get_article(candidate_id) or candidate
    status = str(v(fresh_candidate, "status", "") or "")
    if status == "published" and relation == "DUPLICATE":
        db.update_article(
            article_id,
            status="duplicate",
            duplicate_of=candidate_id,
            reject_reason=f"RC67: дубль уже опублікованої події #{candidate_id}: {reason}",
            ai_provider="ai-dedupe",
            ai_model="rc67-event-judge",
        )
        return "duplicate"

    if status != "published" and relation in {"DUPLICATE", "UPDATE"}:
        cluster_id = int(v(fresh_candidate, "event_cluster_id", 0) or 0) or clusters._ensure_cluster(
            db, int(channel.id), candidate_id, ctags
        )
        canonical_id, canonical_status = _safe_attach(db, article_id, fresh_candidate, cluster_id)
        if canonical_status == "published":
            if relation == "DUPLICATE":
                db.update_article(
                    article_id,
                    status="duplicate",
                    duplicate_of=canonical_id,
                    reject_reason=f"RC67: дубль щойно опублікованої події #{canonical_id}: {reason}",
                    ai_provider="ai-dedupe",
                    ai_model="rc67-event-judge",
                )
                return "duplicate"
            clusters._ensure_cluster(db, int(channel.id), article_id, tags)
            return "single"
        service._audit(
            "rc67_cluster",
            "merged",
            f"parent={canonical_id}; relation={relation}; cluster={cluster_id}",
            channel_id=int(channel.id),
            article_id=article_id,
        )
        return "clustered"

    clusters._ensure_cluster(db, int(channel.id), article_id, tags)
    return "single"


def _prepare_one(service: Any, channel: Any) -> bool:
    rows = _PREV["pending"](service.db, int(channel.id), 30)
    if not rows:
        return False
    row = rows[0]
    article_id = int(v(row, "id", 0) or 0)
    if not article_id:
        return False

    outcome = _fast_cluster_one(service, channel, row)
    if outcome in {"duplicate", "clustered", "skip"}:
        return True

    _TARGET.article_id = article_id
    rc66._CONTEXT.preparing = True
    started = time.monotonic()
    try:
        _PREV["core_process"](service, channel)
    finally:
        rc66._CONTEXT.preparing = False
        _TARGET.article_id = None
    elapsed = time.monotonic() - started
    service._audit(
        "rc67_prepare",
        "done",
        f"article={article_id}; elapsed={elapsed:.1f}s",
        channel_id=int(channel.id),
        article_id=article_id,
    )
    return True


def _prepare_worker(service: Any, channel: Any) -> None:
    try:
        # Small bounded batch keeps the READY pool moving without allowing one
        # channel to monopolise the machine for many minutes.
        batch = max(1, min(2, int(getattr(channel, "max_posts_per_cycle", 1) or 1)))
        for _ in range(batch):
            if getattr(service, "_stop", None) is not None and service._stop.is_set():
                break
            if not _prepare_one(service, channel):
                break
    except Exception as exc:
        LOG.exception("RC67 preparation worker failed channel_id=%s: %s", getattr(channel, "id", "?"), exc)
        service._audit("rc67_prepare", "error", str(exc), channel_id=int(channel.id))
        service._emit("error", f"{channel.name}: RC67 підготовка: {exc}")


def _start_prepare_worker(service: Any, channel: Any) -> None:
    cid = int(channel.id)
    with _worker_lock(service):
        workers = _workers(service, "prepare")
        current = workers.get(cid)
        if current is not None and current.is_alive():
            return
        worker = threading.Thread(
            target=_prepare_worker,
            args=(service, channel),
            name=f"RC67-Prepare-{cid}",
            daemon=True,
        )
        workers[cid] = worker
        worker.start()


def _collect_worker(service: Any, channel: Any, force: bool) -> None:
    try:
        _PREV["collect"](service, channel, force=force)
    except Exception as exc:
        LOG.exception("RC67 collection worker failed channel_id=%s: %s", getattr(channel, "id", "?"), exc)
        service._audit("rc67_collect", "error", str(exc), channel_id=int(channel.id))
        service._emit("error", f"{channel.name}: RC67 збір: {exc}")


def _start_collect_if_due(service: Any, channel: Any, *, force: bool) -> None:
    cid = int(channel.id)
    now = time.monotonic()
    seconds = rc66.POLL_IMMEDIATE_SECONDS if bool(getattr(channel, "poll_immediate", False)) else max(1, int(channel.poll_interval_minutes or 1)) * 60
    if not force and now - service._last_collect.get(cid, 0) < seconds:
        return
    with _worker_lock(service):
        workers = _workers(service, "collect")
        current = workers.get(cid)
        if current is not None and current.is_alive():
            return
        service._last_collect[cid] = now
        worker = threading.Thread(
            target=_collect_worker,
            args=(service, channel, force),
            name=f"RC67-Collect-{cid}",
            daemon=True,
        )
        workers[cid] = worker
        worker.start()


def _run_channel(service: Any, channel: Any, *, force: bool) -> None:
    # READY is always serviced before any potentially slow network/AI work.
    rc66._publish_ready(service, channel)
    _start_collect_if_due(service, channel, force=force)
    _start_prepare_worker(service, channel)


def _process(service: Any, channel: Any) -> None:
    rc66._publish_ready(service, channel)
    _start_prepare_worker(service, channel)


def _install_history_labels() -> None:
    try:
        from .ui import MainWindow
    except Exception:
        return
    previous = MainWindow.refresh_history

    def refresh_history(self) -> None:
        previous(self)
        for item in self.history_tree.get_children():
            values = list(self.history_tree.item(item, "values"))
            if len(values) >= 5:
                raw = str(values[4] or "")
                values[4] = STATUS_LABELS.get(raw, raw)
                self.history_tree.item(item, values=values)

    MainWindow.refresh_history = refresh_history


def install_rc67_nonblocking_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import service as svc
    from .database import Database

    _PREV.update(
        pending=Database.pending_articles,
        run_channel=svc.AutopilotService._run_channel,
        process=svc.AutopilotService._process,
        collect=svc.AutopilotService._collect,
        core_process=rc66._PREV["process"],
    )

    Database.pending_articles = _pending_target
    svc.AutopilotService._run_channel = _run_channel
    svc.AutopilotService._process = _process
    _install_history_labels()

    LOG.info(
        "RC67 installed: READY-first scheduler, background collectors, per-channel preparation workers, one-story fast clustering and human status labels"
    )
    _INSTALLED = True
