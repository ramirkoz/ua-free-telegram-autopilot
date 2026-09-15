# UA FREE Telegram Autopilot v2.0.0-rc32

RC32 hardens three defects confirmed on the live RC31 portable on 15 September 2026.

## Fixed

- Final semantic dedupe now runs again immediately before Telegram publication, so inherited READY rows cannot bypass a newer published story merely because they were prepared by an older build.
- Startup reconciles the preserved READY queue against published history before workers can publish. The new phrase/event fingerprint catches cross-source reports about the same study, court case, regulatory action or syndicated event while retaining conservative same-source and same-product guards.
- Supervisor telemetry now re-discovers the canonical Google Drive LIVE feed at startup and after mirror failures, retries a failed mirror write once after repair, logs mirror failures/recovery instead of failing silently, and exposes telemetry repair state in snapshots.
- Remote auto-update accepts a validated approved release manifest even when the large update ZIP has not yet synced through Google Drive. The updater falls back to the fixed GitHub release URL and still requires the manifest-pinned SHA-256.
- Drive update ZIP selection is SHA-aware: a partial or stale mirrored ZIP is ignored and the updater downloads the exact GitHub release asset instead.

## Preserved

- Data, SQLite, secrets, credentials and channel configuration remain untouched by the update overlay.
- RC31 bounded/cancellation-aware collection quiesce remains active.
- RC30 Supervisor Agent to Telegram bridge and ACK replay protection remain active.
- RC29 Telegram media extraction and technical-ID entity handling remain active.
