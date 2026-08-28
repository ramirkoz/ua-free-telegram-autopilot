# UA FREE Telegram Autopilot v0.1.0-rc49

RC49 is a newsroom-quality correction built from live CTRL+UA output. It keeps RC48 Editorial Learning Loop and the factual safeguards, but removes the extra generative polishing layer that made technically correct posts harder for people to read.

## Human newsroom pipeline
- The editorial chain is simplified to: **story editor → one Ukrainian author → factual/language validation → publish**.
- The Russian stage is now a short internal story plan, not prose intended to be translated or polished repeatedly.
- The Ukrainian author writes the post **from scratch** from SOURCE evidence and the story plan.
- The author is explicitly optimized for read-aloud clarity: one main idea per sentence, varied rhythm, no specification catalogues, no forced hooks and no recap ending.
- RC47's second generative final-newsroom rewrite is removed. The final stage is validation-only and cannot rewrite an already accepted post.
- RC40's legacy generative style-score repair is disabled in RC49. If a candidate fails hard validation, the system requests a fresh candidate instead of passing the same copy through another AI polish.
- Severe read-aloud blockers are checked deterministically: extreme sentence length, sustained overlong sentence rhythm, overloaded comma trains and repeated spec/report-style numeric sentences.

## Trusted production routing
- The RC49 story editor and final Ukrainian author use **Codex/Gemini only**.
- Local Ollama and the historically unreliable Groq/NVIDIA/Cloudflare writing fallbacks are not used for these two quality-critical writing stages.
- Diagnostics/LAB provider integrations remain unchanged.

## CTRL+UA editorial breadth
- Adds a confirmed breadth gate for narrow enthusiast/hobby retro-computing items that do not have a broader technological, security, scientific or market consequence.
- The live examples that motivated the rule were Amiga/AROS/Amiberry-style revival stories and boot-to-BASIC/Thoreau BASIC experiments.
- This is not a generic ban on Raspberry Pi, programming languages or older hardware; broader-impact stories continue through normal editorial selection.

## Editorial weights are targets, not quotas
- Positive per-channel editorial weights no longer reject a strong story merely because its category is temporarily over target in the rolling history.
- Positive weights remain visible as distribution targets and are available to editorial learning/selection logic.
- A category with weight **0** remains an explicit hard ban.
- `__UNCLASSIFIED__` remains fail-closed; off-profile `__OTHER__` remains rejected.

## Channel-specific media policy
- CTRL+UA keeps its media-required publication contract.
- Other configured channels, including marketing/news channels, may publish a compact text-only post when no validated image/video is available.
- This prevents the old CTRL+UA media rule from globally discarding otherwise valid stories in channels whose publishers use difficult lazy-load/CDN/JS media markup.

## Telegram observability
- Telegram send failures are now written to the normal application log with action type and chat target.
- Bot tokens are never written to the log.

## Editorial Learning Loop compatibility
- RC48 per-channel metrics, TOP-30 memory, MTProto analytics and encrypted Telegram session storage are preserved.
- When Editorial Learning is activated, successful examples are supplied to the **single final Ukrainian author**, rather than being diluted across several serial rewriting stages.
- Channel profile, current SOURCE evidence and Fact Guard remain authoritative.

## Cache and compatibility
- Rewrite format marker advances to `telegram-post-v31` so RC48/RC47 cached copy is not reused as an RC49 newsroom result.
- Existing Data, channels, sources, Bot Tokens, editorial profiles, weights, publication history and RC48 metrics remain compatible.

## Upgrade
Unpack RC49 into a fresh folder and copy the complete existing `Data` directory from RC48. Do not overlay program/runtime files. Telegram Analytics authorization from RC48 remains optional; RC49 works without it and begins using performance memory only after analytics is configured and enough comparable posts exist.
