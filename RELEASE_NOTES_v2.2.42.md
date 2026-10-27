# Autopilot 2.2.42 — final safety and general-audience editorial release

## Two operator P0 corrections

### 1. No historical reposts on any channel
- Incident: `ЗАПОРІЖЖЯ | ГРОМАДИ` published October 13 source content on October 27. The old collector saved historical candidate rows without source-date cutoff, and publication checks were inconsistent across channels.
- All three channels now require a verifiable ORIGINAL SOURCE publication timestamp within the operator's **current local calendar day** **and not earlier than the current Autopilot start/restart**. A missing, corrupt, naive or future timestamp fails closed; discovery, processing and AI rewrite times do not make old material fresh.
- Three independent barriers: source collection BEFORE database/AI, queued processing BEFORE AI, and the final READY delivery gate BEFORE any Telegram call. Existing old READY rows are not grandfathered in after restart.
- Hard policy applies equally to CTRL+UA, ПРОДАНО! and ГРОМАДИ. No source credentials, topic approvals or publication-rate settings are changed.

### 2. CTRL+UA is science and technology for regular curious readers
- Previous niche RC103 mix unintentionally favored small AI/hardware engineering updates (hardware 10%, Science/Space 7%, Medicine/Biology 3%).
- Updated visible persisted role-scoped focus: **Science/Space 30%, Medicine/Biology 17%, AI 18%, Robotics 12%, Energy/Climate 10%, Defense/Ukraine tech 5%, Cybersecurity 5%, Hardware 3%**. These are editorial hints, not hard publication quotas.
- Reject marginal controller, voltage, frequency, chip benchmark, firmware and DIY tweaks unless the ORIGINAL SOURCE demonstrates a meaningful public/scientific effect. Preserve major fundamental discoveries even without a near-term commercial application.
- Broad-reader relevance required during selection and independent AI editorial value checks; keep source-grounding and all final factual/quality gates. Other channels are unaffected.

## Clean 7-day operating memory
- Active queues, editor review and operator recent history have a seven-day window. Old nonpublished material is archived and its job removed.
- Heavy published/archived article payload retention is **7 days**, not 30.
- Dashboard/supervisor `published_total` and `last_publish` only refer to the most recent **seven days**. These are now *operational 7-day* counts, not lifetime totals. `published_today` remains current local date.
- **Do not erase** delivery receipts, COMMITTED/UNKNOWN handling, permanent duplicate-protection identity or credentials. Historical UNKNOWN #66297 must never be automatically replayed.

## Installation and validation
- Windows Portable clean unzip into a NEW folder, copy **entire existing Data** unchanged after stopping previous process, start exactly ONE new instance, retain old folder for rollback. Never overwrite Data with old archive contents.
- Verify LIVE program reports **2.2.42**, workers/collectors 3/3 each, correctly aligned source dates, CTRL+UA broad-audience topic samples, unchanged original 45/30/5 minute publication intervals and budgets. The two policy fixes cannot undo an already-published wrong Telegram post; that post requires separate manual correction.
- Release gates: pull request full CI (Ubuntu 3.12, Windows 3.11/3.12/3.13), official native Windows Portable package, packaged GUI smoke, mandatory Microsoft Defender signatures and file scan, SHA256 manifest. Only the **tagged official GitHub asset** is intended for operator download.
