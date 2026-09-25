from __future__ import annotations

from .event_dedupe_guard import EventFingerprintDedupeEngine, SemanticGuardedPublisher
from .loghub import event
from .media_recovery import MediaRecoveryRuntimeEngine


class GuardedRuntimeEngine(MediaRecoveryRuntimeEngine):
    """Production runtime with startup and pre-publish event duplicate guards."""

    def __init__(self, store):
        super().__init__(store)
        self.dedupe = EventFingerprintDedupeEngine(store)
        self.publisher = SemanticGuardedPublisher(store, self.dedupe)

    def start(self) -> None:
        try:
            ledger_total = self.dedupe.sync_all_published_ledger()
            event("publish", "published event ledger synchronized", entries=ledger_total)
            blocked = self.dedupe.reconcile_ready_against_published()
            event("publish", "startup READY event reconciliation complete", blocked=blocked, ledger_entries=ledger_total)
        except Exception as exc:
            event("publish", "startup READY event reconciliation failed", level=40, detail=str(exc)[:1200])
        super().start()
