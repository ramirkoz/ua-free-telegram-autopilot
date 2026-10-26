# Autopilot 2.2.37 — commercial source yield and fast-first collection

Candidate release. Deploy **only** the Windows Portable GitHub release after successful PR CI 4/4, Windows native launch, Windows Defender scan and main release publication. Source-only ZIP is not a Windows app.

## Shipping in 2.2.37
1. Commercial editorial collection now executes the **same enabled source set** in a useful order. The first slots favor recently productive low-latency sources and leave slow 30–60-second known-only sites later. Uses small bounded adjustments to **operator-defined source priorities**. Existing cooldown, page/feed choice, per-source 70-second timeout, schedule, source preservation, and 18-source roster are unchanged. No source is dropped or permanently demoted.
2. New supervisor and Drive LIVE `commercial_source_funnel_24h`: per-source counts of 24-hour **discovered cohort**, rejected, duplicate, ready, published, and media-blocked articles; last fetch duration/outcome and cooldown. Counts are read-only, recomputed at most every 90 seconds and never mutate SQLite. Publication-by-cohort is intentionally **not** the same as total posts sent today: yesterday's queued articles do not count as newly discovered.
3. Regression tests cover actual collection ordering with unknown sources preserved, unchanged configured priority, no skipped low-yield sources, 24h cross-channel isolation, rejected/media-blocked/published cohort counting and read-only safety.

## Known external limits (not falsely labeled fixed)
- Source sites that return HTTP 403, including Design Milk and Rest of World, require lawful official feeds, authorization or operator source replacement. This release does not bypass anti-bot protections or disable sites silently.
- Monitoring media-only neighbor posts with no independent reply/group/source URL binding cannot be safely attached; v2.2.36 exact-post proof still applies.
- Existing editorial quality thresholds stay fixed. A policy-rejected candidate is not newly eligible because its source moved earlier in collection order.

## Operator Windows installation
- Stop current v2.2.36, back up the **entire** Data directory and extract v2.2.37 Windows Portable into a **new folder**, carry over the unchanged Data, keep previous ZIP/folder for rollback.
- Check 3/3 workers and 3/3 collectors, independent `autopilot-oauth` Google Drive, original channel sources 36 / 18 / 57, publication gaps 45/30/5 minutes, $3/day and $20/month OpenRouter limits and delivery ledger. Do not replay historic UNKNOWN #66297.
- In LIVE after first commercial cycle, verify new `commercial_source_funnel_24h` data for «ПРОДАНО!», actual source-to-publish yield and news quality.
