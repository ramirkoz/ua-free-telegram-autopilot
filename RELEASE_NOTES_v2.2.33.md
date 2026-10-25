# Autopilot 2.2.33 — bounded, outbound-only telemetry repair

Date: 2026-10-25. Source branch candidate until PR merge, main CI and official Windows build complete.

## Grounded operator evidence and Drive folder investigation
- As of the last available outbound Google Drive operator snapshot generated **2026-10-25 16:14:02 Kyiv**, installed **v2.2.30**, RUNNING 3/3 workers and 3/3 collectors, **25 published** total today: CTRL+UA 9 HEALTHY, ПРОДАНО! 5 DEGRADED, ГРОМАДИ 11 DEGRADED. 681 COMMITTED / 1 FAILED / 1 UNKNOWN #66297 quarantined, $12.110989/$20 OpenRouter month. **No verified operator v2.2.31 or v2.2.32 after 16:14.**
- Searched Google Drive root, visible Autopilot folders, exact LIVE filenames, and the historical `UA FREE Telegram Autopilot — Project Vault`. The canonical [LIVE folder](https://drive.google.com/drive/folders/1tm0Xdd5V4mDHm7iZza3SnHdEXR2VMa-0) ID `1tm0Xdd5V4mDHm7iZza3SnHdEXR2VMa-0` holds status/recent_events/incident modified **14:14 UTC** (16:14 Kyiv) and old redacted SQLite at **13:18 UTC** (15:18 Kyiv). Other discovered Autopilot folder contains historical version archives latest Oct11. **No alternate current LIVE stream was confirmed**. Search indexing may not expose every binary JSON file, so this is not proof no other private/unindexed copy exists.
- **Root cause NOT proven:** operator could have stopped or switched version, OAuth/Drive sync could have failed, or old supervisor loop could have been blocked. The last 16:14 status showed outbound Drive last_ok 16:13:46, so it does not prove cause of subsequent staleness. Do not present new release as repairing a demonstrated root cause without new LIVE evidence.

## Code fix
- New `outbound_telemetry_233.py`: one daemon worker, one most-recent pending JSON payload per `status.json`, `recent_events.json`, `incident.json`, no unbounded queue, bounded per-file retry/backoff. The sender executes blocking Drive OAuth/HTTP in its own thread, not in the local supervisor heartbeat. Pending data are coalesced; stop never waits a full Drive request timeout. Serialized immutable payloads prevent filesystem mutation races.
- `drive_api_telemetry.DirectDriveTelemetry.upload_bytes` sends immutable bytes using same OAuth credential sources, canonical folder ID and Google API update semantics. Existing `upload_path` delegates to it, preserving 100MB operator snapshot export behavior (already an independent background exporter).
- Local supervisor validates JSON schema and version, reads bytes, submits to the bounded async sender without network. If Drive API fails, background thread falls back only to one canonical locally synced LIVE folder and copies newest valid local JSON; separate `transport.outbound_pump` exposes thread state, queue size, submitted/delivered seq, per-file success/mode, attempt, last error, consecutive failures.
- No remote agent/commands or new inbound communication. No telemetry JSON payload other than the three allowlisted files. No changes to source lists, editorial/2.2.31 dedupe/2.2.32 source-stance safety, publication intervals 45/30/5min, AI budget $3/day/$20/month, media, operator Data, Telegram committed receipts, UNKNOWN #66297 quarantine or signed updates.

## Known design constraints
- One sender thread can still be busy for Google Drive's documented per-request timeout; other items wait in a fixed-size three-file queue. It **does not block heartbeat/publishing**. It is not an external service and cannot report current status while the operator PC/app is off.
- Fallback local Drive Desktop folder can be stale if the Desktop client is offline; `last_mode=local_fallback` explicitly distinguishes a local-copy success from a confirmed Google Drive API upload. Operator should inspect **cloud file modifiedTime**.
- The last LIVE snapshot is pre-release, and **operator live installation/health and the exact reason for the 16:14 cutoff remain unverified**. Never update LIVE counters based on repository commit alone.

## Operator acceptance
1. CI Ubuntu+Windows and native Windows/Defender, tagged official ZIP and GitHub hash must be verified after main merge.
2. Operator independently preserves full original Data, stops old runtime before separate-folder Windows Portable installation/import. No two concurrent instances or receipt replay.
3. Confirm new cloud Drive canonical folder `status.json` timestamp moves at least twice, version `2.2.33`, 3/3 workers+collectors, `transport.outbound_pump` delivered seq advancing and mode `google_drive_api`. If local fallback, diagnose Drive account/sync separately. No claims of runtime deployment until this happens.
4. Subsequent product work 2.2.34: factual/monitoring editorial yield, after fresh evidence; then commercial source/media observability, without consuming an entire release solely for tests.
