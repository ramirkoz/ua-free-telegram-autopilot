# UA FREE Telegram Autopilot v2.0.0-rc31

RC31 fixes two defects confirmed by live RC29 telemetry on 14 September 2026.

## Fixed

- Clean update quiesce no longer queues an entire channel crawl inside `ThreadPoolExecutor`. Production collection keeps only the bounded live fetch lane outstanding and stops scheduling new sources immediately after a runtime stop/update request.
- Waiting for the global source-fetch semaphore is cancellation-aware, so a collector cannot spend the updater grace period merely waiting behind another channel.
- Source/database results are not committed after collection cancellation.
- Cross-source dedupe keeps READY/PUBLISH/PUBLISHED candidates visible even during a large ingest burst instead of letting them fall out of the newest-item scan.
- Cross-source expanded headlines with five or more distinctive shared anchors are recognized more reliably. This specifically covers the live Waymo/ghost-gun duplicate observed between The Verge and Tom's Hardware while preserving a negative same-brand/different-event guard.

## Preserved

- RC30 Supervisor Agent → Telegram bridge and ACK replay protection.
- RC29 Telegram media extraction and technical-ID entity fix.
- Data, SQLite, secrets, credentials and channel configuration are unchanged.
