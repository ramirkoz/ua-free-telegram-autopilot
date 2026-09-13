# RC19 implementation lock

This release restores the product contracts agreed for UA FREE Telegram Autopilot V2:

- EDITORIAL: exactly one media attachment per post.
- MONITORING: only media owned by the same Telegram `data-post` widget; no neighbour stitching.
- Telegram media parser: fail-closed positive ancestry filter, media filter version 3.
- Pending pre-RC19 Telegram media is quarantined and refreshed before publication.
- Fresh non-empty web media replaces the previous unpublished snapshot rather than accumulating stale assets.
- Autonomous update protocol is deterministic: version + SHA-256 request, graceful quiesce, SQLite backup/checkpoint, external helper, startup health gate, automatic rollback.
- Agent-provided shell commands, arbitrary URLs, and arbitrary filesystem targets are not executed.

Do not relax these contracts without an explicit product decision.
