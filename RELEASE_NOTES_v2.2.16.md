# Autopilot 2.2.16 — capacity-aware freshness and high-precision entity QA

**Operator evidence (2.2.15 LIVE, 21 October, 19:49 Kyiv):** 3 workers/3 collectors healthy, 63 posts today (cumulative, last send before 2.2.15 startup), 475 COMMITTED including 11 archival receipts, UNKNOWN #66297 quarantined. CTRL+UA had 136 due articles near 24-hour TTL and only 16 publication slots within a 24-hour window under the operator's **45-minute spacing**. `FRESHNESS_FIRST` was shown in telemetry but SQL still sorted `j.priority` ahead of source freshness. Recent provider QA errors also misclassified ordinary title-cased English words `Semantic` and technical acronyms `ACL`, `III` as invented model names.

**Changes:**
- On *verified overload only*, lease work from newer six-hour freshness tiers before stale tiers. Preserve source priority *inside* the tier. Source publication timestamp parsing supports ISO offsets, falling back to discovery time for unparseable legacy timestamps. The existing RESCUE_NEAR_TTL lane remains priority-first when not overloaded.
- This changes **which pending source job is processed first**, not publishing frequency, output volume, TTL, source configuration, readiness/quality/media requirements, or source enablement. It cannot publish 136 posts into 16 allowed slots; it reduces wasted AI work on aging articles. No automatic queue deletion or backlog replay.
- FactGuard ignores a short allowlist of context-independent ordinary words `Semantic`, `Overview`, `Review`, `Report`, `Summary`, `Research` and `Analysis`, plus well-known `ACL` and Roman numerals; names/models with digits such as `Gen5` remain guarded. **No global bypass of protected-entity QA.**
- Regression tests for overloaded priority inversions, priority consistency within age tier, existing non-overloaded behavior, unchanged 45m setting, ordinary words/acronyms and still-rejected invented model names.

**Kept unchanged:** all v2.2.15 AI refusal leakage guards and opted-in regional original-source relevance; Windows SQLite startup journal recovery, durable delivery receipts, sanitized hourly Google Drive data snapshot, media parity/UNKNOWN quarantine, per-channel intervals (45/30/5), source lists, AI budgets and routing, Telegram no-replay guarantee.

**Gates:** PR CI (Ubuntu, Windows Python 3.11/3.12/3.13), native Windows Portable Release, squash merge, independent main CI+Release, verified ZIP SHA, and only then operator install. Real-world LIVE acceptance remains separate.
