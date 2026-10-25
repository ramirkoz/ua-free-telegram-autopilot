# Autopilot 2.2.32 — monitoring source question/irony factual safety

Date: 2026-10-25. The version is a candidate until PR, main CI and native Windows Release complete. GitHub release is not proof of operator installation.

## Operator evidence
- User supplied side-by-side screenshots of original from «ЗАПОРІЖЖЯ.ІНФО» and published «ЗАПОРІЖЖЯ | ГРОМАДИ» at 16:28 Kyiv. Original stated 41 municipal guard protocols per week, added sarcastic publisher criticism of claimed 16 million UAH annual expense, and asked whether guard workers moved from Космічний to the right bank because it was uncomfortable. Published copy said flatly that workers **did** move **because** it became uncomfortable. Neither factual relocation nor its motive was established by the source.
- Latest independently fetched operator LIVE file from Drive generated 16:14:02 Kyiv, before the 16:28 screenshot, version 2.2.30 RUNNING 3/3 workers and collectors; 25 posts today, 681 COMMITTED, one quarantined UNKNOWN #66297. Thus specific publication chain/model/stage are NOT individually evidenced by the stale telemetry snapshot. Screenshots establish the content distortion.
- Root cause in code: general `verify_source_polarity` covers polarity, `verify_qualified_claims` covers narrow explicit uncertainty words, `trace_output_claims` is shadow-only; none compare original *question speech act* with asserted output. `monitoring_source_voice_230` checks first-person quotations and global policy commentary, not question→claim and adopted local sarcasm. Prompts did not explicitly distinguish a Telegram publisher's rhetorical question from an event.

## Code changes
- `monitoring_editorial_stance_232.py`: compare *immutable original raw_text* interrogative source sentence with final assertive output by ≥3 overlapping substantive word stems and ≥0.65 conservative normalized overlap; do not block unrelated true information, actual questions, or explicitly attributed commentary. Independently corroborated declarative sentences from the same original are exempt from this narrow question guard.
- Refuse obvious unattributed adoption of publisher irony ("оце так робота") without conflating all opinion-bearing sources with non-news. Source facts remain eligible for a neutral rewrite, rather than blacklisting the origin.
- Writer and final editor prompts explain original publisher satire, rhetorical questions, unsupported spending figures, and fabricated causality. Deterministic validator rejects failed model text so the gateway can attempt a clean candidate.
- `hard_editorial_reject` enforces the stance at prepublish for older READY; `non_overridable_quality_issues` enforces it even under human-approval/force paths.
- `tests/test_2232_monitoring_editorial_stance.py` reproduces both supplied source/output texts and tests source-fact preservation, independent declarative corroboration, attributed question, unrelated questions, channel scoping, and non-overridable final publication boundaries.
- No changes to sources 36/18/57, published 45/30/5 minute gaps, editorial inclusion thresholds, AI/provider costs $3/day/$20/month, operator Data, Telegram receipts, archived COMMITTED, UNKNOWN #66297 replay policy, current 2.2.31 conservative event-identity dedupe, or signed update gate.

## Scope and limitations
- This is a **high-confidence lexical safeguard**, not a general proof of entailment, OCR validation of screenshots, or comprehensive satire understanding. Some paraphrases not sharing enough terms may be missed; some ambiguous language will require manual original-source checks. No arbitrary restrictions on opinions or quoting a clearly attributed source.
- The originally posted bad Telegram message is not edited or deleted automatically. The fix affects only new submissions and rechecked existing READY, after operator installs.
- Prior intended 2.2.32 *media/source-yield observability* scope is deferred to the next planned release instead of being silently represented as done.

## Install and acceptance
1. CI Ubuntu+Windows versions and native Windows Defender/GUI/migration must pass; official main/tag and ZIP checksum confirmed separately before marking RELEASED.
2. Operator manually stops older build, backs up original Data independently, installs into separate Windows folder, imports Data (never dual-runs or replays UNCERTAIN delivery).
3. Outbound Google Drive LIVE must explicitly say version 2.2.32 RUNNING 3/3; review real original→final source question and unrelated factual news, check suppression/false positives. No live editorial acceptance solely from CI.
