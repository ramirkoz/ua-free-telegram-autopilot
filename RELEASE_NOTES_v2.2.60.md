# Autopilot 2.2.60 — safe restart source continuity

- Replaces the permanent all-before-runtime source rejection **only for an unseen, same-local-day item published since that source's last successful poll**, where the poll was less than two hours before restart.
- Snapshots each source's prior successful `last_checked_at` before updating the existing runtime marker. Stored as a JSON value in existing `meta`, no SQLite schema migration and no operator Data reset.
- Applies one consistency gate at commercial pre-enrichment, Telegram linked teaser hydration, final source ingest, pre-AI processing, and publisher preflight.
- Existing pre-start article rows are not restored: they have earlier `discovered_at`. Unknown dates, previous-day stories, future dates, old checkpoints or long downtime fail closed.
- Database source identity, canonical-URL dedupe, event dedupe, READY checks, and Telegram COMMITTED/UNKNOWN delivery ledger unchanged. No automatic replay of UNKNOWN.
- No changes to media ownership, source roster, publication cadence, AI routing, or budgets.
- Operator acceptance requires LIVE v2.2.60 with the original Data and real `restart_checkpoint_admitted` telemetry. Zero admitted is valid if no fresh articles occurred during a restart gap.
