# UA FREE Telegram Autopilot 2.3.50 — Windows Portable timezone incident hotfix

Status: hotfix candidate; operator LIVE acceptance pending. Supersedes v2.3.49 ZIP when verified and officially published from main. The owner must install manually; no remote command/update is executed.

## Confirmed LIVE P0: 23 November 2026

At 12:27 Europe/Kyiv the installed Windows operator v2.3.49 was RUNNING with 3/3 workers/collectors and healthy Drive mirror, but production output was STARVED:
- ПРОДАНО!: 0 new posts after v2.3.49 start at 09:45:46; last delivered #1400 at 09:32:12 (v2.3.48). 15 errors/deferred; 0 READY. New valid candidates existed (GTA 6, design, Ferrari, culture).
- ГРОМАДИ: 0 new posts after start; similarly deferred by the same fatal exception, in addition to normal dedupe.
- CTRL+UA continued publishing because the failing source-admission path was not used for its science profile.
- Both affected worker event streams repeatedly reported 'No time zone found with key Europe/Kyiv', retry 180s. Latest read-only SQLite mirror last updated 11:58:28; source status.json generated 12:27:14.
- Unrelated Telegram integrity: 2382 COMMITTED, 4 FAILED, 2 historic protected UNKNOWN, with no auto replay.

## Root cause, verified source

v2.3.49 source requirements listed tzdata>=2025.2; release.yml instead constructs a separate portable Lib/site-packages with a hard-coded pip package list that did not include tzdata. New editorial_admission_2349.py eagerly called ZoneInfo('Europe/Kyiv') at import time, so both the commercial catalog check and monitoring source check raised on isolated Windows rather than yielding editorial results. Existing GUI/Defender smoke did not assert zoneinfo availability.

## Small fix, no behavior retuning

1. Include tzdata>=2025.2 in the release portable-target pip install, not only source/test requirements.
2. Move ZoneInfo('Europe/Kyiv') into cached lazy service-freshness function. Ordinary commercial news and non-schedule monitoring must not require timezone data to import their rules; genuinely time-sensitive service messages still use the proper IANA zone and DST.
3. Native isolated _runtime_console.exe -I smoke MUST import tzdata, load Europe/Kyiv and check winter UTC+2 / summer UTC+3. Fail release before the EXE/ZIP is published if missing. Static + unit regressions added for anti-recurrence.
4. Version 2.3.50 in all 6 metadata markers/package entrypoints.

## Non-changes / safety

- No new publishing quota; retain the 30/30/5 min cadence and channel working hours. Do not turn off owner selector, numeric/fact guard, anti-slop, source dedupe, media requirements, or source freshness fences.
- No import of transient queues, reset of operator Data, deletion or recreation of SQLite or Telegram journal, no auto replay of 2 protected UNKNOWN, no automatic recovery of old stale or delivered messages.
- Preserve v2.3.49 incident/source editorial fixes when packaged correctly.
- Never treat CI PASS or released ZIP as confirmation of LIVE operator publishing. After manual install, verify new publication from ПРОДАНО! and ГРОМАДИ, channel funnel, delivery receipts, AI usage and post text.

## Release gates
- PR CI full Ubuntu/Windows Python 3.11/3.12/3.13.
- Native Windows release from main: packaged IANA zoneinfo smoke, GUI startup, Defender scan, ZIP and SHA256, official GitHub tag.
- Separate manual operator telemetry after installation. The v2.3.49 operator can remain unchanged until the download and install; do not start two instances using the same Data.
