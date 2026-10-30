"""Single owner of article lifecycle transitions.

An article's lifecycle state is the tuple ``stage / decision / blocked_by`` plus
the blocker evidence ``last_error_code / last_error_detail / next_retry_at``.
Callers name a transition from :data:`TRANSITIONS`; this module checks the
from-state and writes the to-state in one guarded ``UPDATE``. A transition whose
from-state no longer matches is refused (``False``) instead of overwriting a
state another component owns, e.g. a READY recovery may never clear a blocker
that is not MEDIA, and nothing here may move a PUBLISHED article.

Transitions are universal. Channel-specific behaviour (media policy, TTL,
recovery attempts) is decided by the caller from channel settings; the caller
then names the transition and passes the reason code.

Phase 1 covers the MEDIA blocker. See ``docs/ARTICLE_STATE_INVENTORY.md`` for
the remaining direct writers.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Mapping

from .domain import BlockedBy, Decision, Stage
from .loghub import event


class _Keep:
    def __repr__(self) -> str:
        return "KEEP"


class _Caller:
    def __repr__(self) -> str:
        return "CALLER"


KEEP: Any = _Keep()
"""The field is not written by the transition."""
CALLER: Any = _Caller()
"""The caller supplies the value (reason code, detail, retry clock)."""


@dataclass(frozen=True)
class StateGuard:
    """From-state. ``None`` means any value; ``exclude_stages`` always applies."""

    stages: frozenset[str] | None = None
    decisions: frozenset[str] | None = None
    blocked_by: frozenset[str] | None = None
    error_codes: frozenset[str] | None = None
    exclude_stages: frozenset[str] = frozenset({str(Stage.PUBLISHED)})

    def matches(self, state: Mapping[str, Any]) -> bool:
        stage = str(state.get("stage") or "")
        if stage in self.exclude_stages:
            return False
        checks = (
            (self.stages, stage),
            (self.decisions, str(state.get("decision") or "")),
            (self.blocked_by, str(state.get("blocked_by") or "")),
            (self.error_codes, str(state.get("last_error_code") or "")),
        )
        return all(allowed is None or value in allowed for allowed, value in checks)

    def sql(self) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, allowed in (
            ("stage", self.stages),
            ("decision", self.decisions),
            ("blocked_by", self.blocked_by),
            ("last_error_code", self.error_codes),
        ):
            if allowed is not None:
                values = sorted(allowed)
                clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
                params.extend(values)
        if self.exclude_stages:
            values = sorted(self.exclude_stages)
            clauses.append(f"stage NOT IN ({','.join('?' for _ in values)})")
            params.extend(values)
        return " AND ".join(clauses), tuple(params)


@dataclass(frozen=True)
class Transition:
    """One edge of the lifecycle graph.

    ``stage``/``decision``/``blocked_by`` are fixed targets or :data:`KEEP`.
    ``error_code`` is a fixed code, ``''`` (clear) or :data:`CALLER`; a caller
    code must belong to ``reason_codes``. ``detail`` and ``next_retry_at`` are
    ``''`` (clear), :data:`KEEP` or :data:`CALLER` (``None`` from the caller
    keeps the stored value). ``extra_fields`` lists the
    non-state columns a caller may write in the same statement.
    """

    name: str
    guard: StateGuard
    stage: Any = KEEP
    decision: Any = KEEP
    blocked_by: Any = KEEP
    error_code: Any = ""
    detail: Any = ""
    next_retry_at: Any = ""
    reason_codes: frozenset[str] = frozenset()
    extra_fields: frozenset[str] = frozenset()
    counts_attempt: bool = False


class IllegalTransition(ValueError):
    """The transition request itself is malformed (unknown name, code or field)."""


MEDIA_ERROR_CODES = frozenset({
    "MEDIA_REQUIRED",
    "MEDIA_INCOMPLETE",
    "MEDIA_DOWNLOAD_RETRY",
    "MEDIA_DOWNLOAD_FAILED",
    "MONITORING_VIDEO_DELIVERY_INCOMPLETE",
    "LEGACY_MEDIA_PARTIAL",
    "CAPTION_STATE_MISSING",
    "MEDIA_UPLOAD_RETRY",
    "MEDIA_PARTIAL",
    "MEDIA_UPLOAD_REJECTED",
})
"""Final-gate MEDIA backoff codes written by the publisher."""

READY_MEDIA_RECOVERABLE_CODES = frozenset({
    "MEDIA_REQUIRED",
    "MEDIA_INCOMPLETE",
    "MEDIA_DOWNLOAD_FAILED",
    "MEDIA_DOWNLOAD_RETRY",
})
"""MEDIA codes a READY article may leave when its stored bundle becomes complete."""

_READY = frozenset({str(Stage.READY)})
_PUBLISH = frozenset({str(Decision.PUBLISH)})
_MEDIA = frozenset({str(BlockedBy.MEDIA)})

MEDIA_BACKOFF = "MEDIA_BACKOFF"
MEDIA_UNBLOCK_NEW_ASSET = "MEDIA_UNBLOCK_NEW_ASSET"
MEDIA_UNBLOCK_READY_BUNDLE = "MEDIA_UNBLOCK_READY_BUNDLE"
MEDIA_ARCHIVE_PERMANENT = "MEDIA_ARCHIVE_PERMANENT"
MEDIA_RESTORE_223 = "MEDIA_RESTORE_223"

TRANSITIONS: dict[str, Transition] = {
    t.name: t
    for t in (
        # Publisher final media gate: READY stays READY, blocked until the
        # retry clock elapses ('' = wait for a source refresh).
        Transition(
            MEDIA_BACKOFF,
            StateGuard(stages=_READY, decisions=_PUBLISH),
            blocked_by=str(BlockedBy.MEDIA),
            error_code=CALLER,
            detail=CALLER,
            next_retry_at=CALLER,
            reason_codes=MEDIA_ERROR_CODES,
            counts_attempt=True,
        ),
        # A re-poll brought new media evidence for a MEDIA-blocked article at any
        # non-published stage (the caller proves the evidence is new).
        Transition(
            MEDIA_UNBLOCK_NEW_ASSET,
            StateGuard(blocked_by=_MEDIA),
            blocked_by=str(BlockedBy.NONE),
        ),
        # READY row whose stored bundle is complete and not yet tried.
        Transition(
            MEDIA_UNBLOCK_READY_BUNDLE,
            StateGuard(
                stages=_READY, decisions=_PUBLISH, blocked_by=_MEDIA,
                error_codes=READY_MEDIA_RECOVERABLE_CODES,
            ),
            blocked_by=str(BlockedBy.NONE),
            extra_fields=frozenset({"status_detail"}),
        ),
        # Bounded recovery exhausted: fail closed, no text-only fallback.
        Transition(
            MEDIA_ARCHIVE_PERMANENT,
            StateGuard(stages=_READY, decisions=_PUBLISH),
            stage=str(Stage.ARCHIVED),
            decision=str(Decision.REJECT),
            blocked_by=str(BlockedBy.MEDIA),
            error_code="MEDIA_REQUIRED_PERMANENT",
            detail=CALLER,
            extra_fields=frozenset({"reject_reason"}),
        ),
        # One-time 2.2.3 repair of items archived by the pre-2.2.3 recovery loop.
        Transition(
            MEDIA_RESTORE_223,
            StateGuard(
                stages=frozenset({str(Stage.ARCHIVED)}),
                decisions=frozenset({str(Decision.REJECT)}),
                error_codes=frozenset({"MEDIA_REQUIRED_PERMANENT"}),
            ),
            stage=str(Stage.READY),
            decision=str(Decision.PUBLISH),
            blocked_by=str(BlockedBy.MEDIA),
            error_code="MEDIA_REQUIRED",
            detail=CALLER,
            next_retry_at=CALLER,
            extra_fields=frozenset({"reject_reason", "article_layout_json"}),
        ),
    )
}


@dataclass(frozen=True)
class Plan:
    transition: Transition
    assignments: dict[str, Any] = field(default_factory=dict)
    retry_increment: int = 0


def plan(
    name: str,
    *,
    error_code: str | None = None,
    detail: str | None = None,
    next_retry_at: str | None = None,
    count_attempt: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> Plan:
    """Resolve a transition request into column assignments (pure)."""
    spec = TRANSITIONS.get(name)
    if spec is None:
        raise IllegalTransition(f"unknown transition {name!r}")
    out: dict[str, Any] = {}
    for column, target in (("stage", spec.stage), ("decision", spec.decision), ("blocked_by", spec.blocked_by)):
        if target is not KEEP:
            out[column] = target
    if spec.error_code is CALLER:
        code = str(error_code or "")
        if code not in spec.reason_codes:
            raise IllegalTransition(f"{name}: reason code {code!r} is not allowed")
        out["last_error_code"] = code[:120]
    elif spec.error_code is not KEEP:
        out["last_error_code"] = spec.error_code
    for column, target, value in (
        ("last_error_detail", spec.detail, detail),
        ("next_retry_at", spec.next_retry_at, next_retry_at),
    ):
        if target is CALLER:
            if value is not None:
                out[column] = str(value)[:2000]
        elif target is not KEEP:
            if value is not None:
                raise IllegalTransition(f"{name}: {column} is fixed by the transition")
            out[column] = target
    for column, value in dict(extra or {}).items():
        if column not in spec.extra_fields:
            raise IllegalTransition(f"{name}: field {column!r} is not writable by this transition")
        out[column] = value
    if count_attempt and not spec.counts_attempt:
        raise IllegalTransition(f"{name}: does not count attempts")
    return Plan(spec, out, 1 if count_attempt else 0)


def can_transition(state: Mapping[str, Any], name: str) -> bool:
    spec = TRANSITIONS.get(name)
    if spec is None:
        raise IllegalTransition(f"unknown transition {name!r}")
    return spec.guard.matches(state)


def transition(
    con: sqlite3.Connection,
    article_id: int,
    name: str,
    *,
    error_code: str | None = None,
    detail: str | None = None,
    next_retry_at: str | None = None,
    count_attempt: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> bool:
    """Apply ``name`` to one article on ``con``; ``False`` if the guard refused.

    Runs on the caller's connection so it joins any open transaction.
    """
    resolved = plan(
        name, error_code=error_code, detail=detail, next_retry_at=next_retry_at,
        count_attempt=count_attempt, extra=extra,
    )
    sets = [f"{column}=?" for column in resolved.assignments]
    params: list[Any] = list(resolved.assignments.values())
    if resolved.retry_increment:
        sets.append("retry_count=retry_count+?")
        params.append(resolved.retry_increment)
    where, guard_params = resolved.transition.guard.sql()
    sql = f"UPDATE articles SET {','.join(sets)} WHERE id=?" + (f" AND {where}" if where else "")
    cur = con.execute(sql, (*params, int(article_id), *guard_params))
    applied = int(cur.rowcount or 0) > 0
    if not applied:
        row = con.execute(
            "SELECT stage,decision,blocked_by,last_error_code FROM articles WHERE id=?", (int(article_id),),
        ).fetchone()
        event(
            "app", "article transition refused",
            article_id=int(article_id), transition=name,
            stage=str(row[0]) if row else "", decision=str(row[1]) if row else "",
            blocked_by=str(row[2]) if row else "", last_error_code=str(row[3]) if row else "",
            missing=row is None,
        )
    return applied
