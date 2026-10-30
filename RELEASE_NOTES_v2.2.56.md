# Autopilot 2.2.56 — ПРОДАНО! / reader-first commercial selection

## Problem / evidence
- LIVE editorial review 28–30 October: **18 of 18** published commercial items were dominated by **Yanko Design 14/18 (78%)**; product-design and mini-house descriptions displace broadly shareable culture, human behavior, brand stunts and surprising tech. Previous 23–27 October: Yanko Design **20/35 (57%)**. Published posts ≠ broad audience interest.
- ProductVault `01_PRODUCT/AUTOPILOT/CHANNELS/PRODANO.md` already defines the channel as a **lively visual/shareable digest for normal curious people**, with operator positive references (IKEA manul, Adidas Pokémon, AI lost cats, MSCHF/Lexus, Aston Martin viral shadow, Apple stop-motion, mega-yacht, robot goose, résumé cake, book raves, Cup Noodles Halloween, Snapchat Harry Potter AR), **not** generic design catalog or B2B marketing. These are examples, never brand whitelist.
- Real LIVE selection uses `v2/runtime_contracts.py::_install_ai_efficiency_contract` RC102 combined one-call selector; edits limited to `editorial.py` would have had **no effect** on installed operator.

## Changes
1. New `telegram_autopilot/v2/commercial_reader_256.py`: shared, profile-based operator-reference prompt with explicit question: why would an ordinary person who will not purchase this item show/retell its story? Product aesthetics/compactness/portability alone do not qualify. Independent real surprise, culture, unexpected use, memes, human behavior and brand stunts do qualify.
2. **LIVE** RC102 combined selector receives the new prompt and optional model fields `story_class`, `product_only`, `shareable_to_friend`, `share_hook_quote`. Existing 11 quantitative fit/value ratings and threshold configuration remain. If the model positively classifies a source as routine product/trade article **without an independently supported shareable story**, the profile-specific `SOLD_CATALOG_ONLY_256` veto rejects it even when its numeric score is high. If the model provides an explicit strong counterexample, a verbatim phrase must appear in the actual SOURCE. There is no source/domain/brand ban; striking design stories remain eligible. Existing model outputs without new fields remain compatible.
3. Same guidance added to the standalone selector/fallback for future safety, even though LIVE is RC102.
4. Positive, negative, invented-hook, safety, live RC102, legacy data and non-commercial-channel regression tests.
5. No new AI calls, provider, budget, telemetry mirror, source enablement/priority, channel schedule, media policy, Telegram delivery path, schema, Data migration or historical replay.

## Acceptance
- GitHub PR CI Ubuntu + Windows 3.11–3.13, signed/Defender Windows Portable release.
- 7-day **LIVE** reader-level manual audit is separate; targets (NOT claimed outcomes): **>=70%** truly broadly interesting stories, **<=30%** simple object/catalog posts, **<=30%** content from any single source; no fabricated facts in accepted sample. Source diversity and source validation are deliberately **2.2.57**, chronological mix is **2.2.58**, voice **2.2.59** and multi-channel 2.3.0. Do not hard cap authors or force publish weak stories in 2.2.56.
