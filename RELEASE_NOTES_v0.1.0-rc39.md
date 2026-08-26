# UA FREE Telegram Autopilot v0.1.0-rc39

Editorial architecture change based on the RC38 live corpus from 25–26 August 2026.

## Changed
- Replaced the direct Ukrainian writer + mandatory self-editor chain with a cross-lingual editorial bridge: SOURCE facts → Russian editorial draft → fresh Ukrainian rewrite → SOURCE Fact Guard.
- The Russian draft is an internal story-finding layer, not publication content and not a factual authority. It is independently checked for source-supported numbers and years.
- The final Ukrainian model receives both the original SOURCE EVIDENCE PACK and the Russian editorial draft, but is explicitly forbidden from sentence-by-sentence translation. SOURCE always wins on facts.
- Removed the RC38 55–80 word, 3–5 sentence and 2–3 paragraph contract. There is no fixed sentence/paragraph count in RC39.
- Media-caption posts now normally target roughly 650–890 characters when the source supports that much useful context, with the existing 900-character hard publication budget retained.
- Added an anti-slop gate for stacked canned transitions and unnaturally symmetric paragraph blocks without imposing a new universal template.
- The bridge first prefers configured non-Codex/free providers or local AI; Codex is a bridge fallback. The final Ukrainian author remains Codex/Gemini and is fully revalidated from SOURCE.
- Local LanguageTool stays a non-blocking grammar proofreader only; it is not the editorial author.
- Cache marker bumped to `telegram-post-v24` so pending RC38 drafts are regenerated through the new bridge.

## Preserved
- RC38 event dedupe and rolling topic balance.
- RC37 newsworthiness, strict media-required behavior, semantic media evidence and adaptive source backoff.
- Evidence Pack, number/year checks, Ukrainian hard gates and Fact Guard.
- No SQLite schema change. Existing RC38 `Data` is compatible; copy the complete `Data` directory into a fresh RC39 portable folder.
