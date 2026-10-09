# Autopilot 2.0.10 — clean queue cutover

On first launch only, existing unpublished work is retired. Draft/final texts of the retired items are cleared; prior published posts, editor feedback, channels, source definitions and credentials remain intact. Historical records are kept as tombstones to stop stale content from returning on the next feed scan.

A timestamp is stored in the database so later restarts do not repeat the reset. Newly discovered sources whose confirmed publication date precedes the cutover are not queued. Undated sources continue to follow existing channel policy.

Uncertain or already acknowledged Telegram deliveries and their delivery journal are preserved and quarantined to prevent duplicate posting. Previously approved material retired by the reset is not resurrected by the older approval-recovery logic.

Status: code under review; not operator-accepted until CI, Windows Portable build, Drive synchronization and live telemetry verification.
