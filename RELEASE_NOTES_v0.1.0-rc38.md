# UA FREE Telegram Autopilot v0.1.0-rc38

Editorial stabilization release based on RC37 live output from 24–25 August 2026.

## Fixed
- Stronger cross-source event dedupe. Reports with different wording are blocked when the same event action, named entities, geography and supporting facts line up. This specifically covers the duplicated Taiwan/Nvidia/China export case that escaped RC37.
- Much lighter Telegram copy. The mandatory human editor now targets 55–80 words, never more than 90, 2–3 short paragraphs and 3–5 sentences. One core fact plus only the few details needed to understand it.
- Hard compactness gate rejects dense four-paragraph summaries, overlong first sentences and posts that still read like compressed articles.
- Rolling topic balance. Ordinary stories are skipped when one broad topic already dominates the recent feed. Strong security, safety and major regulatory events remain exempt.
- Space is capped more aggressively than other categories because the live feed was visibly overrepresented.
- Cache marker bumped to `telegram-post-v23`, so pending RC37 drafts are regenerated under the RC38 editorial contract.

## Compatibility
- No SQLite schema change.
- Copy the complete existing `Data` directory into a fresh RC38 portable folder.
- RC37 media-required, Fact Guard, trusted Codex/Gemini editor and source backoff behavior are retained.
