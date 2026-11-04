# Autopilot v2.3.11 — evidence-first local editorial and QA recovery

**04.11.2026 · verified v2.3.10 LIVE follow-up**

## What changed
- **ГРОМАДИ, post #90628:** a nationwide NABU/SAP investigation copied into a Zaporizhzhia Telegram aggregator is not automatically regional news. A narrow, source-only gate rejects national criminal investigations with no explicit regional event; a local investigation or actionable civic service remains eligible. The gate runs during selection and immediately before Telegram delivery, including old READY items.
- **Legal precision, post #90628:** verified investigation/indictment coverage must attribute unresolved criminal allegations to investigators; categorical guilt/organizer claims without source-owned court judgment are refused. This remains non-overridable by manual approval or force. Editorial writer and final-editor instructions request appropriately qualified wording.
- **ГРОМАДИ, article #90617:** the existing end-of-sentence QA incorrectly rejected an otherwise complete post ending in an exact source-owned phone/email/URL line added by contact preservation. Permit only exact verified trailing practical lines following a complete sentence. Arbitrary numeric truncation, dangling prose, wrong numbers and invented contacts remain blocked.
- Regression suite: national NABU/SAP copied post vs real local case, legal allegation vs qualified source attribution, source-owned phone vs invalid trailing text.

## What remains unchanged
- Operator `Data`, encrypted or historical publication receipts, and quarantined Telegram `UNKNOWN`; no replay or deletion.
- Channel cadence 45/30/5 min, source-day/start fencing, event dedupe and original-story photo/video provenance.
- Commercial `ПРОДАНО!` source-sufficiency gate is **not** bypassed. After 2.3.10, observed two new sources were rejected, including one fragment with fewer than two substantive sentences; no evidence yet supports lowering quality floor or forcing posts.
- No automatic LIVE changes: this change must pass all PR CI and Windows release/Defender, then be installed and accepted separately.

## Validation
Candidate, not LIVE until full CI, Windows release and new operator supervisor evidence. Historical 2.3.10 Telegram posts are not retroactively edited.
