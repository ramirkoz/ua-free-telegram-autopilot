from __future__ import annotations

from .loghub import event
from .media_recovery import MediaRecoveryRuntimeEngine
from .semantic_dedupe import SemanticDedupeEngine, SemanticGuardedPublisher


class GuardedRuntimeEngine(MediaRecoveryRuntimeEngine):
    """Production runtime with startup and pre-publish semantic duplicate guards."""

    def __init__(self, store):
        super().__init__(store)
        self.dedupe = SemanticDedupeEngine(store)
        self.publisher = SemanticGuardedPublisher(store, self.dedupe)

    def start(self) -> None:
        # A portable update intentionally preserves Data, including old READY rows.
        # Reconcile that inherited queue against already-published history before a
        # worker can send the next post.
        try:
            blocked = self.dedupe.reconcile_ready_against_published()
            event("publish", "startup READY semantic reconciliation complete", blocked=blocked)
        except Exception as exc:
            # Do not hide a guard failure. Publishing still has the same pre-send
            # semantic check, so startup can continue while the incident is logged.
            event("publish", "startup READY semantic reconciliation failed", level=40, detail=str(exc)[:1200])
        super().start()
