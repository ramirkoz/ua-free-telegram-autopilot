# Autopilot 2.3.49 — evidence-first editorial admission (candidate)

Status: CANDIDATE / PR VALIDATION. Not an official release, not installed on the user's Windows operator. The live operator remains 2.3.48 until native Windows/Defender and LIVE acceptance are confirmed.

## Why
Live audit 23 Nov 2026 identified the same rescued woman published three times:
- 110485 / Telegram #5675 (22 Nov 18:36)
- 110490 / Telegram #5676 (22 Nov 18:42)
- 110793 / Telegram #5711 (23 Nov 07:46, already on v2.3.48).
Previous prepublish diagnostics found 0.71 concept similarity but did not establish same-event identity.

Other regression examples: 110584 published at 21:16 for service hours expiring 20:30; 110601 bureaucratic visit without new outcome; 110714 routine "5 best cabin accessories" catalog in creative channel.

## Bounded changes
1. monitoring_event_identity_2349.py: high-precision source-only rescue incident identity including rescue, injury, boat, rocky shore, shared named district/waterbody and source-time range 48h. Integrated in channel-configured pre-AI and prepublish semantic event matcher. Do not use title similarity or publish stage as independent proof. Material new fatal outcomes must not be merged; previous COMMITTED ledger remains authoritative.
2. editorial_admission_2349.py: source-only expiry for dated operational service changes, rejecting after proven final end time; never guess when dates/time are absent or schedules cover several days.
3. Same module: conservative veto for routine inspections with neither actionable service information nor confirmed result, and for brief unconfirmed fireworks signals. Do not automatically reject short verified casualties or genuine operational notices.
4. Creative profile: source-title best-N shopping accessories catalog exclusion. No blanket category / fashion / games / LEGO / gadget bans.
5. Both source admission checks wired before AI and again at hard prepublish editorial gate, including previous READY material. Existing original-source factual integrity checks remain intact.
6. Focused regression module tests/test_2349_event_and_editorial_admission.py includes positive and negative matches, distinct locations/victims/updates, expiry/legitimate schedules, creative exception.

## Preserved / out of scope
- No changes to operator Data, SQLite, Telegram ledger, Facebook, Content Tool, sources, budgets, channel cadence 30/30/5, provider routing, two protected UNKNOWN, automatic replay or remote updates.
- Existing QUALITY_RETRY_EXHAUSTED backlog (110031 transport, 110467 art) requires fresh-source verification and exact QA failure diagnosis. Not automatically cleared or delivered by this release.
- CTRL source HTTP403 / HTTP429 and Core77 network failures remain input-provider follow-up; do not bypass access restrictions.
- The additional commercial/science owner calibration from 2.3.48 remains; this candidate corrects one verifiable best-N class, not all owner-selection precision.

## Verification gates
1. All PR CI checks pass (Ubuntu and Windows matrix) with specifically reviewed 2.3.49 regressions.
2. Merged official main release and native Windows Portable/Defender/ZIP hash pass before publishing a download as verified.
3. Operator manually installs into a new folder with durable Data import (no automatic update), then validates source/final/delivery and fresh editorial examples. CI alone is not live acceptance.

Canonical audit: ProductVault/01_PRODUCT/AUTOPILOT/LIVE_EDITORIAL_AUDIT_2.3.48_2026-11-23_0834.md.
