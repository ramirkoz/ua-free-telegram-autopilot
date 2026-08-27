# UA FREE Telegram Autopilot v0.1.0-rc45

RC45 is an editorial-quality and multilingual-channel release. It keeps the RC44 source transport and adds per-channel content direction plus a native English rewrite path for Ukrainian/Russian sources.

## Channel language direction
- Every channel now has its own **Content direction** setting.
- Existing channels migrate safely to `English → Ukrainian`, preserving current behavior.
- New reverse mode: `Ukrainian / Russian → English`.
- Reverse mode uses a dedicated native-English newsroom rewrite, not literal translation.
- Source input language is validated per channel.
- English-output posts use an English `Source` footer and `Video` label while preserving the same Telegram/media safety path.
- Channel direction is included in the post format marker so cached Ukrainian text cannot be reused after switching a channel to English output, or vice versa.

## Editorial quality
- Added a pre-rewrite event-level duplicate gate that compares source titles, entities and source facts before two outlets can become stylistically different rewrites of the same event.
- The Gemini 3.5 Transcribe cross-outlet duplicate is covered as a regression case.
- Final-body semantic dedupe remains as a second independent barrier immediately before Telegram publication.
- Category classification no longer silently disables editorial balance when AI classification is unavailable. Provider outages now retry instead of `balance skipped`.
- Classifier output parsing accepts normal provider wrappers/JSON and uses `__OTHER__` for material that is outside the configured channel profile/categories.
- `__OTHER__` is an editorial rejection when channel weights are configured, rather than an implicit pass.
- Classification prompt now treats category labels semantically across English/Ukrainian/Russian sources and checks fit against the channel profile.

## More human writing
- Ukrainian rewrite instructions now emphasize one dominant idea, 2-3 short paragraphs, fewer secondary details and no obligatory clever hook/kicker.
- Repetitive AI-newsroom scaffolding such as «найцікавіше тут», «але є нюанс», «іронія в тому» and similar constructions is explicitly discouraged as a recurring template.
- English reverse rewrites follow the same human-editor principle: strong fact first, concise selection, no manufactured angle and no paragraph-by-paragraph translation.

## Multilingual factual safety
- Evidence Pack scoring now recognizes Ukrainian and Russian attribution/risk language, so late source sentences carrying uncertainty or attribution remain eligible for the evidence pack.
- Reverse English output keeps number/year checks and Fact Guard.
- RC45 adds cross-language guards against inventing stronger English claims such as `first`, `largest`, `fastest`, `record` or turning an agreement/plan into a purchase.

## Compatibility
- SQLite migration is additive: `channels.content_direction TEXT NOT NULL DEFAULT 'en_to_uk'`.
- Existing `Data` folders, channel weights, sources, publication history and Telegram credentials remain compatible.
- RC44 direct-feed transport, RC43 screen-aware channel editor and RC42 per-channel editorial weights are preserved.

## Upgrade
Unpack RC45 into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
