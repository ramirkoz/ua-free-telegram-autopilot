# UA FREE Telegram Autopilot v0.1.0-rc42

RC42 fixes the multi-channel architecture problem introduced by the RC41 CTRL+UA topic mix. Editorial categories and weights are now owned by each channel and are editable by the operator.

## Changed
- Removed the global RC41 technology/security/AI topic percentages from production behavior.
- Added a per-channel **Editorial profile** editor. The operator can describe that channel's audience, topics, exclusions and style independently.
- Added a per-channel **Editorial weights** editor. The operator creates category names manually and assigns each a weight from 0 to 100.
- Weights are relative and are normalized automatically; they do not need to sum to 100.
- Weight `0` disables automatic publication for that category in that channel.
- A channel with an empty weight list has no topic-balance gate at all.
- Added automatic semantic classification into the operator-defined category names. Exact category-name matches are resolved locally first; ambiguous items use a small AI classification call. If classification is unavailable, publication is not blocked merely because the classifier is offline.
- Category history is persisted per article in the existing SQLite database and rolling balance uses only that channel's own published categories.
- Added a small rolling tolerance so weights behave as editorial targets rather than brittle hard quotas.

## Multi-channel isolation
- CTRL+UA weights no longer affect a future Marketing channel or any other channel.
- A Marketing channel can define categories such as `SEO`, `Social media`, `Advertising`, `Analytics`, `MarTech` with its own weights.
- A new channel starts with a neutral profile and no topic weights until the operator configures them.
- RC41's global `cyber=2`, `AI=4`, etc. balance is neutralized in RC42.
- Domain-specific marketing/news filters from older tech-only policy are reduced to a small universal junk filter (buying/affiliate roundups and sponsored/affiliate source material).

## Data compatibility
- Existing `Data` folders remain compatible.
- RC42 adds only two SQLite columns lazily: `channels.editorial_weights_json` and `articles.editorial_category`.
- No destructive migration and no data reset.

## Preserved
- RC40 SOURCE → optional RU editorial bridge → fresh Ukrainian author pipeline.
- Evidence Pack, Fact Guard, number/year checks, Ukrainian hard gate and media-required publishing.
- Event dedupe, source health/backoff, AI Router and Telegram publication safety.

## Upgrade
Unpack RC42 into a fresh folder and copy the complete existing `Data` directory from RC41. Do not overlay runtime files onto the old build.
