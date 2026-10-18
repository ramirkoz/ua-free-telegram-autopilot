# Autopilot 2.2.0 Evidence-First release contract

**Status:** development only. This branch is not production-ready; do not tag or package it as 2.2.0 yet.

## Editorial invariants

1. A public Telegram message is an immutable source unit identified by `channel/message_id`. Never merge adjacent messages based only on numeric proximity or timestamp.
2. Media belongs only to the exact source widget, a trusted album identity, or an explicit same-channel reply relation. Unknown ownership is **unresolved**, never guessed.
3. If the source or final post promises essential video but it has no downloadable source-owned video, publication is blocked, including `preferred` media text fallback.
4. Multiple unrelated incidents inside one raw post cannot become a single article. Split using verified event boundaries or reject for manual review.
5. Unverified active-threat notices are not transformed into retrospective completed incidents. Do not invent negative claims from absence of data.
6. AI final copy is not a source of truth. Claims require a source-grounded evidence record; unknown facts stay unknown.
7. Record both editorial quality outcomes and transport outcomes; `HEALTHY` workers are not proof of accurate posts.

## First implemented slice (draft PR #193)

- `evidence_first.py`: source-integrity and media dependency decisions.
- `editorial.py`: pre-AI deterministic source gate and publication-boundary media QA.
- `publisher.py`: monitoring video-dependency blocks preferred-media text fallback.
- `strict_ingest.py` / `ingest.py`: source-message snapshots and explicit same-channel reply links for media-only messages.
- `tests/test_220_*.py`: operator-inspired damaged story/strike/video tests and explicit reply-ownership tests.

## Blockers before 2.2.0 release

- Verify album/grouped_id and cross-post video ownership on actual original Telegram samples, including records for VB_is_Ukraine/14790 and vasgromada/10013. Explicit reply links alone are not sufficient.
- Event-level segmentation that generalizes beyond the currently known lost-animal/lost-documents case.
- Claim-level citation/evidence ledger and independent final verifier; existing deterministic negatives are only partial safeguards.
- A full replay corpus from private operator examples without publishing secrets or personal data.
- Review ambiguous reply ownership and refuse multiple claims to a single media item.
- All Ubuntu/Windows CI, native Portable release, 24-hour shadow monitoring and operator acceptance.

## Release gate

No merge/tag/release while any blocker remains. `main` stays on 2.1.23.

## Phase 1b: ownership / video invariant

- Media-only replies are attached only when an explicit same-channel reply relation exists and has exactly one editorial owner; conflicting claims remain unbound.
- Telegram video-dependent posts require a real `video|URL` media entry. A still image or video poster cannot stand in for the source video.
- Regression cases cover conflicting reply claims, missing video and photo-only placeholders.
- These checks prevent false attachment or text-only publication but do not yet reconstruct videos from Telegram albums without explicit public provenance. Full 2.2.0 release is still blocked.

## Phase 1d: qualification preservation

- `claim_verifier.py` compares output assertions against exactly sourced, explicitly uncertain sentence evidence and blocks a high-confidence omission of its uncertainty qualifier.
- Wired into monitoring `prepublish_quality_issues()`; source evidence and original uncertainty remain authoritative, AI must not silently promote an unverified statement into a confirmed one.
- Unit tests cover qualifier removal, qualifier preservation, unrelated facts, and actual prepublish wiring.
- This is not general semantic verification. Full claim-level entailment and operator replay remain release blockers.

## Phase 1f: shadow statement provenance

- `claim_trace.py` traces individual output statements to exact source spans, recording EXACT, ALIGNED or UNRESOLVED with score and source quote.
- Monitoring prepublish QA emits `monitoring claims unresolved in source trace` with counts. Shadow only, no automatic blocking on lexical mismatch.
- Regression tests cover exact spans, a fabricated absence-of-aftermath sentence, legitimate reordered paraphrase and unrelated topic.
- Promote UNRESOLVED to a publish blocker only after measured operator-corpus precision/recall and semantic verification. The existing hard guards still block narrow proven violations.

## Phase 1g: explicit Telegram album identity

- `TelegramEntry.grouped_id` is read only from explicit `data-grouped-id`, `data-media-group-id`, or `data-album-id` on the exact Telegram message widget.
- Strict stitching joins a media-only message to a text story when an unambiguous same-source album/group ID or reply edge proves its owner. A group with multiple independent text owners remains unbound rather than duplicating the media.
- Source provenance records include grouped_id; tests cover exact group ownership, conflicting ownership and parser extraction.
- Public Telegram HTML often omits these attributes: actual operator-post reconstruction still needs calibrated source-level retrieval and replay and is NOT complete.

## Phase 1h: unresolved public-Telegram media observations

- Exact-post ingestor stores nearby media-only public Telegram widgets in `telegram.unresolved_nearby_media_v1` when an actual ownership relation is unavailable. Entries include source post, bounded time distance, media count, video presence and explicit unresolved reason; they **never** add the media to the news article.
- Media explicitly linked by a verified album ID or reply relation is excluded from unresolved candidates.
- No proximity-based stitching. A missing linkage must be resolved by authoritative source access or operator inspection; this stage improves observability, not automatic video recovery.
- Regression tests cover adjacent unowned video, explicitly linked video and cross-channel/time-boundary isolation.
