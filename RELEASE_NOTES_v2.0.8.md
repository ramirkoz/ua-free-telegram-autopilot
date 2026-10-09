# Autopilot 2.0.8 — editorial grounding and safe AI cost routing

## Included in this build
- Borrow Content Tool's source-first editorial principle: final editor verifies SOURCE and rewrites unsupported passages from the source rather than polishing an invented draft.
- Deterministic reject of conspicuous unsupported speculative claims ("це свідчить про", invented preliminary attribution, ungrounded expert forecasts), with bilingual English/Ukrainian source-cue support.
- OpenRouter automatic writer/final_editor discovery excludes agentic multi-agent ensembles, avoiding recent high-cost Grok auto-selection while preserving strong single-agent editorial models. Manually configured models and research routes remain unaffected.
- Regression tests include unsupported claims, legitimate translated source qualifiers, cost route, and existing previous release startup/migration/media pipeline tests.

## What does NOT change
- Import, startup, SQLite, credentials, operator Data, Telegram workers/collectors and publishing behavior, channel configuration and budgets.
- Content Tool is unchanged. Codex remains disabled in configuration and PR #153 is not incorporated.
- Existing 2.0.7 postfactum-only and prepublish guards remain enabled.

## Known problems not claimed solved
- Full human-quality equivalence to Content Tool requires live comparative post-by-post testing.
- Same-image reuse across separate posts and occasional incorrect web hero imagery require source-article visual review, not just a regression pass.
- Event dedupe false positives/false negatives and queue throughput require continued operator observation.
- **Do not promote to unsupervised overnight production solely because CI is green.** Keep 2.0.7 as rollback until full live acceptance.
