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
        # A portable update intentionally preserves Data, including old READY rows.
        # Reconcile that inherited queue against already-published history before a
        # worker can send the next post. RC52's final gate sees at least seven days.
        try:
            blocked = self.dedupe.reconcile_ready_against_published()
            event("publish", "startup READY event reconciliation complete", blocked=blocked)
        except Exception as exc:
            # Do not hide a guard failure. Publishing still has the same pre-send
            # event check, so startup can continue while the incident is logged.
            event("publish", "startup READY event reconciliation failed", level=40, detail=str(exc)[:1200])
        super().start()
