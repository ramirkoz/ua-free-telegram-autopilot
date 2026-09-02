# UA FREE Telegram Autopilot v0.1.0-rc62

RC62 is an editorial-control release based on the first real RC61 production run on 2026-09-01/02.

## Why this release exists

RC61 fixed the blocked ПРОДАНО! pipeline, but the live run exposed the next production-level failures: CTRL+UA could publish in bursts, two distinct articles about the same product/news cycle could both go out, one source/topic could dominate the feed, the stronger semantic 👍/👎 layer had been shadowed by RC59, ПРОДАНО! still admitted industry-interest stories with weak general-reader value, and visibly broken Ukrainian phrases could escape the writer QA.

## What changed

- **Semantic reaction learning restored after RC59.** 👍/👎 now influence both close textual matches and broader semantic/facet similarity again. 👎 remains twice as strong as 👍; 🔥 remains style-only.
- **ПРОДАНО! gets an enforced human-interest gate.** The selector must return explicit human-interest, creative-surprise, mechanic and friend-share scores. A campaign is no longer publishable merely because it is professionally good or festival-worthy. Behavioural/selling stories can still pass when the everyday consequence is strong.
- **Publication pacing.** Quiet hours are 00:00–07:00 local time. Effective minimum spacing is at least 60 minutes for general science/tech profiles and 90 minutes for marketing profiles. Daily caps are 12 and 8 respectively, and a four-hour burst guard prevents feed floods.
- **Source/topic saturation hold.** Pending stories from an overrepresented source or recent topic are deferred, not rejected. CTRL+UA can no longer become a five-post BleepingComputer block simply because that source produced many fresh candidates.
- **Stronger same-news-cycle dedupe.** Versioned products/technologies such as `DLSS 5` are treated as one subject within the dedupe window when named anchors and content overlap confirm the collision, even if one article is a launch story and the second is an explainer.
- **Final Ukrainian proofreader.** Every publish candidate gets a narrow final QA pass for broken morphology, machine-translation corruption and distorted units/technical terms. Repair is fact-preserving and revalidated against the source. A temporary proofreader-provider outage does not stop publication when deterministic gates are clean.
- **Known corruption signatures are blocked deterministically.** Includes the live-run failures such as `запік селені`, `сліду вальник`, `у вузькому смузі`, split `мод дери`, and `непісн...`.
- **Clickable source footer works with video posts.** `Джерело` is linked even when a `🎬 Відео:` line follows it.

## Data / schema

- Existing RC61/RC60 Data is compatible.
- No destructive migration.
- Existing channels, source priorities, policies, reactions, history and sessions are preserved.

## Intended production behaviour

- Quality beats quota. RC62 does not force ПРОДАНО! to match CTRL+UA by count.
- Weak Cannes-Lions-style trade-interest stories are rejected rather than used to fill the feed.
- CTRL+UA remains broad science/tech, but source and topic concentration is held back automatically.
