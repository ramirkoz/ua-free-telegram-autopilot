# UA FREE Telegram Autopilot v0.1.0-rc40

RC40 fixes the zero-publication regression observed in RC39 live operation. RC39 made editorial imperfections and several false-positive guards equivalent to factual safety failures, so otherwise safe candidates rarely reached Telegram.

## Fixed
- Split **hard publication safety** from **soft editorial quality**. Facts, numbers, unsupported entities, broken Ukrainian, corruption and incomplete output remain hard blockers; readability/style score is no longer allowed to kill a factually safe post by itself.
- A safe candidate below the preferred editorial score now gets **one targeted copy-edit repair**. If repair fails or is not better, the original safe candidate is retained instead of discarded.
- RC40 blocks a candidate on deterministic editorial score only when it is genuinely unusable (`<60`), not merely imperfect (`<82`).
- RU editorial bridge length is no longer a publication gate. The bridge must still be natural Russian prose and fact-safe, but internal draft length is treated as an editorial detail.
- If every RU bridge provider is unavailable, RC40 falls back to a **SOURCE-only final author pass** instead of reducing throughput to zero.
- Final Ukrainian author keeps Codex/Gemini priority but can fall back to **Groq/NVIDIA** under the exact same hard SOURCE/Fact Guard checks.
- Publication metadata year is accepted as a valid temporal anchor because `SOURCE PUBLICATION DATE` is explicitly supplied to the writer.
- Number QA ignores only clearly formatting-only time/date fragments while preserving strict checks for factual quantities.
- Fact Guard no longer mistakes generic Latin technology nouns such as `Email`, `Web`, `App`, `Cloud`, `Browser` and `Server` for invented product/model names.
- Added article/stage-aware RC40 logging for bridge, UA author, repair and publish-ready transitions.

## Preserved
- Media-required publishing semantics.
- RC38 event dedupe and topic balance.
- RC37 newsworthiness, media relevance and source backoff.
- Evidence Pack and SOURCE Fact Guard as the final factual authority.
- Existing SQLite/Data compatibility. No schema change.

## Upgrade
Unpack RC40 into a fresh folder and copy the complete existing `Data` directory from RC39. Do not overlay runtime files onto the old build.
