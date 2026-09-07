# UA FREE Telegram Autopilot v0.1.0-rc80

RC80 fixes the false mass clustering observed in the live ПРОДАНО! queue after RC79.

## Dedupe / event clustering

- `DUPLICATE` and `UPDATE` decisions from AI, cache, or fallback no longer merge articles by themselves.
- Every proposed merge must also pass a deterministic local same-event confirmation.
- Different rows from the same source are treated as separate stories unless the high-precision local duplicate detector confirms one concrete event or the normalized URL is identical.
- Existing child rows with status `clustered` are no longer used as bridge candidates that can drag unrelated stories into an existing cluster.
- Minor-topic overlap alone is no longer enough even to enter the event merge comparison path.
- Shared technology/brand/topic with conflicting version/product/event codes is downgraded to `RELATED`, not merged.
- If local evidence cannot prove one concrete event, a proposed AI `DUPLICATE`/`UPDATE` is downgraded to `RELATED`.

## RC79 recovery

- On first RC80 start, recent `clustered` children from the previous 72 hours are requeued once for strict re-evaluation.
- Their old event-cluster links are cleared before reprocessing.
- Correct duplicates can cluster again under the stricter rules; unrelated stories return to the normal selector/writer pipeline.
- Older history is left untouched.

## Diagnostics

- New audit stages `rc80_dedupe` and `rc80_cluster` record the original relation, guarded relation, candidate, overlap and decision path.

## Compatibility

- No destructive database reset.
- Existing channels, sources, tokens, channel settings, reactions and publication history remain compatible.
- RC79 monitoring/media/contact/source-link fixes remain active.
