# UA FREE Telegram Autopilot 2.0.0-rc104

Roadmap release focused on the ПРОДАНО! commercial-editorial profile audit, while carrying forward the live fixes discovered during RC103 acceptance.

## ПРОДАНО! audit/profile

- Adds a non-mutating audit for every channel using `commercial_editorial`.
- Checks media-first capability, the RC98 120-character reference threshold, broad-audience editorial threshold keys, visible broad-audience selection/rejection markers, and media-policy validity.
- Audit results are added to supervisor telemetry and local editorial logs.
- Startup does not silently rewrite operator channel policy or custom source configuration.

## Editorial queue fix

- Human-approved READY material now has publication priority over automatically prepared READY rows.
- Among human-approved items, the oldest approval is handled first.
- Existing hard blockers still remain authoritative: for example `MEDIA_REQUIRED` is not bypassed by approval.

## Telemetry repairs carried from RC103 live debugging

- Canonical Google Drive live folder is pinned by ID instead of ambiguous name-only lookup.
- A revoked/stale Autopilot OAuth refresh token can fail over to valid Content Tool credentials and persist the verified replacement.
- Legacy local Drive fallback migrates from `SUPERVISOR FEED — Autopilot V2` to `UA_FREE_AUTOPILOT_LIVE_CURRENT`.

## Startup/database fixes preserved

- Runtime/UI readiness is not gated by database housekeeping.
- Seven-day retention stays deferred by 300 seconds and runs in bounded FK-safe batches.
- Live maintenance does not run VACUUM/ANALYZE/index creation/checkpoint operations.

## Roadmap note

Cluster same-event dedupe shadow mode is not part of RC104 in the current ProductVault roadmap. It remains planned for RC106, with validated activation in RC107.
