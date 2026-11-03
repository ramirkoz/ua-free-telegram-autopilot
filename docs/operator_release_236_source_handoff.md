# 2026-11-03 — Operator Autopilot 2.3.6 source handoff (DO NOT RELEASE FROM main)

**WARNING:** This GitHub repository's `main` source is still **2.2.64**. The operator's installed Windows build was 2.3.5, with unpublished source changes. PR #269 was closed because its 2.2.64 base is not the complete operator code.

On 2026-11-03 the operator provided the actual **2.3.5 Windows Portable ZIP** (full Python sources and portable EXE). A complete 2.3.6 Windows Portable and a full **2.3.6 source ZIP** were built **locally from that uploaded 2.3.5 source**, not from GitHub main, and validated. The authoritative canonical release record is [ProductVault RELEASE_2.3.6.md](https://github.com/ramirkoz/ProductVault/blob/main/01_PRODUCT/AUTOPILOT/RELEASE_2.3.6.md).

## Persistent artifact inventory

All three files are stored in the user's persistent ChatGPT Library at `/Autopilot/Releases/2.3.6/`, with the following exact filenames and checksums:

| File | Bytes | SHA256 |
|---|---:|---|
| `UA_FREE_Telegram_Autopilot_v2.3.6_Windows_Portable.zip` | 29,444,571 | `8ab47dd33eb6c3da19c7c69d10b98674a14cb1e83fc5c0c22884d321faab3f01` |
| `UA_FREE_Telegram_Autopilot_v2.3.6_Source.zip` | 749,308 | `6d60e5dc42ef7ba5a38ff213c9bbfae1bb453c2b0256b7a1ad110022c743d829` |
| `UA_FREE_Telegram_Autopilot_v2.3.6_SHA256SUMS.txt` | 232 | Plain SHA256 checksums |

The **Source ZIP** contains all Python files from the operator-supplied 2.3.5, updated 2.3.6 source and non-Python package resources, sitecustomize, pyproject, requirements, release notes, and eight focused regression tests. Windows EXE bytes are carried forward unchanged, not recompiled.

## Release contents

- Operator-calibrated science and creative selections based on the 200 article labels (CTRL 47 positive, ПРОДАНО 31 positive), new role-specific transactionally-backed-up policy migration.
- Monitoring news source-only guards for nonlocal US polemics, unsupported Borshchahivka speculation, unverified «reactive sound»; source timetable time-window fidelity; sports duplicate identity #88747/#88765.
- Fixed exact 2.3.5 Trend Hunter vs Design Milk FeedBurner collision, retaining source IDs, RSS roster and Telegram delivery history.
- Active 2.3.5 selector calibrated; old score and catalog vetoes no longer stack after channel-fit approval. Source/factual/dedupe/media/delivery safety retained.
- No Data, credentials, or user SQLite bundled. 8/8 local Python tests, compileall, ZIP CRC and SHA256 passed. Windows-native runner/Defender and actual Telegram LIVE acceptance are not yet verified.

## Required source sync, do NOT fake it

**P0:** Import the complete Source ZIP into this GitHub repository using a fully authenticated Git transport (retain history, include all original 2.3.0–2.3.5 source changes). Review file deltas, rebuild Python and Windows Portable in CI, and check version 2.3.6, source parity and SHA. Only then mark GitHub main as synchronized. Never merge the obsolete PR #269 as a shortcut, or call a build from 2.2.64 an equivalent release.

Maintain canonical ProductVault, operator's existing 45/30/5 cadence, built-in first-run Data importer and protected historical Telegram UNKNOWN. The installed operator's 2.3.5 remains source of Data to import through UI; do not manually copy it.
