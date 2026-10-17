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
