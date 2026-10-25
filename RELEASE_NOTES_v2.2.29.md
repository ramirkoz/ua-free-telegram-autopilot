# Autopilot 2.2.29 — ПРОДАНО! commercial source reset

Date: 2026-10-25. **Source candidate; operator LIVE validation is NOT complete.**

## Scope

**Commercial-editorial sources, not a new editorial/AI model experiment.** Based on the 25 October operator read-only Data and LIVE telemetry, the 26 enabled sources produced zero posts for ПРОДАНО! today. Many existing feeds supplied low-value platform marketing reports, agency appointments, industry PR and B2B items. Factual/creative/editorial thresholds must not be lowered to fill a quota.

- One-time `commercial_sources_229` migration runs only after the first-run Data import, before the collectors start.
- Target identification uses `editorial_runtime_profile=commercial_editorial` and at least four **exact** known shipped source identities; **no channel IDs or names hardcoded**.
- Adds five potential high-yield source inputs: Campaigns of the World (page), Yanko Design (RSS), Creative Bloq (RSS), Design Milk (RSS), The PR Insider (page).
- The previously ineffective Famous Campaigns RSS input is switched **within its original source ID** to the active official homepage for page-first, public RSS-fallback collection. Preserves historical articles, priority becomes 10. If the homepage already exists as a custom source, original is untouched.
- Promotes the existing Muse by Clio, It's Nice That, Creative Boom, Creative Review, Fast Company, Adweek and Ads of the World to earlier scan priorities.
- **Disables, never deletes**, exactly recognized low-yield/blocked streams: Springwise (known HTTP403); Snapchat for Business; YouTube Blog; Meta News; LinkedIn Marketing Blog; Social Media Today; Marketing Dive; Digiday; Reddit for Business; Pinterest Business Blog; Think with Google; Brand New / UnderConsideration; Social Samosa. They remain visible/re-enableable and their article history stays intact. Unknown/custom source names or altered URLs are never disabled.
- Adds each new source only when the domain is not already represented, never automatically revives a previously user-disabled matching domain.
- Saves `meta` migration receipt scoped per channel, source-level introduction note and Famous Campaigns original URL/kind; second startup is a no-op.

## Important guardrails

- Current 45/30/5-minute posting gaps and all channel scheduling preserved; no provider, AI cost, editorial thresholds, source ownership, media requirements, credentials, history, UNKNOWN receipts or Data deletion touched.
- `CTRL+UA` and `ЗАПОРІЖЖЯ | ГРОМАДИ` entirely outside scope.
- **Not claimed:** zero source fetching failures, guaranteed 3–6 posts/day, restoration of source media #77342, fixes for monitoring source voice/meta text/deduplication (planned 2.2.30–2.2.31), nor publication of anything without existing editorial QA.
- Public website/RSS visibility is NOT proof that the Windows operator's collector can fetch/enrich that source. After install, evaluate real collected/article-added counts and media for each source; if new endpoints have poor yield, disable via the operator source UI, not blind retries or bypass.

## Verification / acceptance gates

- CI: Python 3.12 + native Windows 3.11/3.12/3.13 regression suite, source compilation, first-run migration and signed/native Windows packaging; `tests/test_2229_commercial_sources_reset.py` proves channel scope, custom setting preservation, existing publication/source IDs, idempotence and no duplicate domain.
- Separate-folder operator installation preserving original full `Data`, independent backup, all COMMITTED journal/archive receipts and UNKNOWN #66297 quarantine. No unattended auto-replay.
- Inspect actual installed `version=2.2.29`, operator LIVE log `2.2.29 commercial source refresh`, effective source list (expected around 18 active sources if the known 26-source sample is unchanged), 3/3 workers and 3/3 collectors.
- **Editorial acceptance:** review several genuinely new original-source article captures from new sources, factual text/media integrity and sustainable commercial output for 1–3 days. Do not call source code merge or CI success operator acceptance.

## Next product work, deliberately deferred

- **2.2.30:** stop unsourced speaker/quote and `Текст поста:` leaks; monitoring local relevance.
- **2.2.31:** reliable same-event identity and consolidated Zaporizhzhia daily strike updates.
- **2.2.32:** bounded real-media repair and quality/source-yield telemetry.

Source priority is a scan ordering preference only. No commitments to produce manufactured content.
