# UA FREE Telegram Autopilot v0.1.0-rc52

## Two independent reaction-learning tracks
- 👍 now means **the topic/story is interesting**. It raises affinity for semantically similar future material, but it does not teach writing style.
- 👎 keeps the RC51 dynamic topic suppression behavior: very similar fresh stories are temporarily lowered or skipped, with decay across the seven-day window. It does not mark the text as badly written.
- 🔥 now means **the published Telegram text is well written**. It is completely topic-neutral and only supplies style examples to the Ukrainian writer.
- Two reactions on one post are intentionally supported as independent labels: 👍+🔥 means both topic and writing are good; 👎+🔥 means suppress similar topics while still learning from the writing style.
- No reaction remains neutral.

## Style learning
- Only published posts with 🔥 enter style memory. 👍-only and 👎-only posts never become prose examples.
- Style memory uses the actual published Telegram teaser/caption, not the source article or an intermediate draft.
- The writer may learn rhythm, density, paragraph length, opening strategy and detail selection, but reaction memory remains non-factual; current facts still come only from SOURCE Evidence Pack.
- Style examples decay within the same rolling seven-day learning window.

## Topic learning
- Topic ranking uses 👍 and 👎 only. 🔥 cannot raise a similar story in the queue and cannot rescue a disliked topic.
- Existing RC51 semantic similarity, time decay and close-story dislike gate are preserved.
- Manual editorial topic percentages remain retired from publication decisions.

## UI and compatibility
- Editorial Memory now displays separate **Topic** and **Style** signals so the operator can see what each reaction is teaching.
- Telegram Analytics still reads exactly 👍 / 👎 / 🔥 and continues to use the existing MTProto session.
- Existing RC51 Data is compatible; no destructive migration is introduced.
- RC50 media-required behavior, LanguageTool fix and all factual safety gates are preserved.

## Upgrade
Unpack RC52 into a fresh folder and copy the complete existing `Data` directory from RC51. Do not overlay runtime files.
