# UA FREE Telegram Autopilot v0.1.0-rc65

RC65 is an editorial-pipeline release based on the RC64 live logs. Source lists are intentionally unchanged in this build; source expansion for ПРОДАНО! is deferred to the next tuning pass.

## What changed

- **Universal final editor for every channel.** Every publish-ready draft, regardless of channel, now receives one final channel-aware Ukrainian copy-edit before Telegram publication. The editor improves syntax, rhythm, paragraph logic and readability while preserving the channel's own writing/style policy.
- **Fact-safe final editing.** Final-editor output is revalidated against SOURCE evidence, allowed numbers/years, Ukrainian language blockers and Fact Guard. It may not invent or alter facts, attribution, uncertainty, names, numbers or causal relations.
- **Non-blocking editor degradation.** If the final editor/provider is unavailable or its rewrite fails validation, the already safe pre-editor draft is kept. The new editor can improve throughput quality but cannot become another publication kill switch.
- **Three independent ПРОДАНО! routes.** Marketing selection now distinguishes `creative`, `human` and `behavior/commercial-mechanism` stories instead of forcing every story through one Cannes-style creativity/shareability formula. Strong behavior/payment/pricing/platform mechanics can pass without campaign-style creative spectacle.
- **Selector-pass resume cache.** Once a candidate passes selector, a retry in the same process reuses that pass for up to six hours and resumes at writer/QA instead of spending another AI call re-selecting the same story.
- **Pipeline diagnostics.** Logs now expose RC65 selector cache hits, marketing route, final-editor START/PASS/DEGRADED and whether a thrown failure happened before selector or after an already accepted selector pass.
- **No source changes in RC65.** The existing source set remains intact so the effect of pipeline changes can be measured separately from source expansion.

## Preserved

- RC64 five-minute technical anti-double-send spacing and quiet hours 00:00–07:00.
- No daily or rolling publication-count caps during training.
- RC64 soft source/topic diversity, cross-source event dedupe and named-entity localization.
- Semantic 👍/👎 learning and 🔥 style-only learning.
- Existing SQLite `Data`, channels, sources, Telegram credentials and reaction history. No destructive migration or Data reset is required.

## Live acceptance

GitHub CI/release validation is required before distribution. Native live acceptance remains separate and must be judged from the operator's real RC65 logs and published posts after installation.
