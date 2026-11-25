# UA FREE Telegram Autopilot v2.3.53 — eligible regional dedupe anchors

Status: release candidate in PR; no operator installation or LIVE acceptance implied.

## Actual observed failure
On operator 2.3.52, monitoring articles 111301 and 111303 carried
686 meaningful source characters each, but both were DEDUPED to 111304
(303 chars), which was then correctly rejected by SHORT_SOURCE_DROP_2352.
The 686-char source never reached editorial selection. This does not prove
that its final output would have passed editorial QA.

## Changes
- Apply existing owner's regional 500-character source veto **before**
  semantic/event-dedupe evaluation in the processing worker. Reject and
  finish the already-claimed job without invoking paid AI or publishing.
- Unpublished cluster anchors must remain source-eligible: reject and
  ARCHIVED candidates, short sources, source-only hard rejects and
  one-sentence fragments cannot silence a substantive report.
- When both inputs are eligible but an incoming source is materially
  richer, let the richer source proceed. Published Telegram receipts and
  the prepublish dedupe gate remain authoritative; no historical replay.
- Require a concrete attack/fire or injury+rescue for the broad
  breaking-incident shortcut. Administrative compensation and unrelated
  civic-service guides no longer become a breaking incident because
  they share words such as "damage", "medical" or "residential".
- New targeted safety regressions for 111301/111303/111304, 111184/111035
  and true attack coverage. Tests use fixture text, not production IDs.

## Explicit non-changes and still-open work
- Never weaken original/final 500-character regional rule or fabricate
  additional facts. AI QA on numbers/email and weak final copy requires
  separate source→final evidence; this release does **not** bypass QA.
- No changes to CTRL+UA/ПРОДАНО! channel policies, source rosters,
  operator Data, SQLite schemas, existing Telegram messages, protected
  UNKNOWN receipts, 30/30/5 cadence or OpenRouter $3/$20 limits.
- Editorial novelty/attribution issues from recent Atari example remain
  for a separately evidence-based editorial change, not a broad product ban.
- Merge, main Windows/Defender build and owner LIVE acceptance are distinct
  gates. Install only a verified official portable, in a new directory.
