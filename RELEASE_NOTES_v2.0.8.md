# Autopilot 2.0.8 — editorial grounding and safe AI cost routing

## Included in this build
- Borrow Content Tool's source-first editorial principle: final editor verifies SOURCE and rewrites unsupported passages from the source rather than polishing an invented draft.
- Deterministic reject of conspicuous unsupported speculative claims ("це свідчить про", invented preliminary attribution, ungrounded expert forecasts), with bilingual English/Ukrainian source-cue support.
- OpenRouter automatic writer/final_editor discovery excludes agentic multi-agent ensembles, avoiding recent high-cost Grok auto-selection while preserving strong single-agent editorial models. Manually configured models and research routes remain unaffected.
- Regression tests include unsupported claims, legitimate translated source qualifiers, cost route, source-bound media identity and existing startup/migration/media pipeline tests.
- A selected hero binary is now included in per-article gallery duplicate detection, preventing it from being uploaded twice under two different image URLs.
- When a monitoring post omits source-owned email/contact URL near the 750-character limit, the safe local repair shortens ordinary text at a sentence boundary and preserves the contact. If the contacts cannot fit, publication still fails closed.

## What does NOT change
- Import, startup, SQLite, credentials, operator Data, Telegram workers/collectors and publishing behavior, channel configuration and budgets.
- Content Tool is unchanged. Codex remains disabled in configuration and PR #153 is not incorporated.
- Existing 2.0.7 postfactum-only and prepublish guards remain enabled.

## Known problems not claimed solved
- Full human-quality equivalence to Content Tool requires live comparative post-by-post testing.
- Same-image reuse across **separate** posts and occasional incorrect web hero imagery still require source-article visual review and a separate ledger-aware feature; the fix above covers per-article hero/body exact-binary repeats, not cross-article perceptual duplicates.
- Event dedupe false positives/false negatives and queue throughput require continued operator observation.
- **Do not promote to unsupervised overnight production solely because CI is green.** Keep 2.0.7 as rollback until full live acceptance.
