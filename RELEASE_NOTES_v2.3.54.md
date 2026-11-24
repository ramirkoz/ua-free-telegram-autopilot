# UA FREE Telegram Autopilot v2.3.54 — editorial source fit and film/media parity

Status: owner-requested Windows Portable candidate. Built from the 2.3.53 source package. No claims of operator installation, GitHub release or LIVE editorial acceptance.

## Owner-review corpus, 23–24 Nov 2026

Owner expressly accepted 21 of 25 published 2.3.53 posts. **All 21 must remain eligible**. Four exceptions:
- ПРОДАНО! #1416 KFC India *Drip Happens*: narrative **campaign film** published with an image instead of an actual video. A YouTube link or poster is NOT attached video. Source-only hard gate blocks this specific format when playable source-owned video is not present; an authentic uploadable source-video asset allows normal selection/media/Telegram checks.
- ПРОДАНО! #1418 Toshiba: routine $130 price reduction / shopping offer, not a novel designed product report.
- ПРОДАНО! #1414 Costco: ordinary ready-made food sides returned to retail inventory; not an original design or campaign.
- CTRL+UA #2186 Chris Dickman: obituary / tribute without a newly reported result. Genuine scientific discoveries about that scientist remain eligible.

## Implementation
- `v2/editorial_owner_2354.py`: deterministic, narrowly conditioned **original-source** owner-veto; requires explicit discount+shopping evidence, ordinary side-dish retail return+shopping evidence, or obituary headline+body. No country, brand, publication or category blacklist.
- A narrative-ad-film requirement for **real source-owned `video|https://...` media item**. Website `video_links`, embedded player pointers and still images do not satisfy that condition. Non-film brand stunts, product/packaging design and creative physical ideas remain eligible with existing source-owned image policy.
- Called through the existing `editorial_source_topic_reason_2319` hook before AI and again in existing `hard_editorial_reject`/READY publication checks. No extra AI models, no database schema changes, no external video scraping or copyright bypass.
- `editorial_blueprint_250.py` + `editorial_voice_2337.py`: first verified surprising fact, one material mechanism, no shot-by-shot narration of video, fewer secondary catalog details, preserve scientific uncertainty and exact attribution. AI stylistic output still needs a LIVE check.
- Added `tests/test_2354_owner_21_green_4_red.py` plus actual-operator-SQLite **read-only** cohort verification for 25 items. User operator DB is never packaged.

## Immutable safety fences
- All accepted 21 samples remain eligible; no blanket bans on creative weirdness, cats, films, food, KFC, designs, brands, beauty or pop culture.
- ГРОМАДИ: original and final meaningful text >=500 characters; keep existing dedupe and source-provenance guards. CTRL+UA and ПРОДАНО! have no imported 500-char limit.
- 30/30/5-minute publication intervals, operator `Data/`, credentials, SQLite, existing published messages, Telegram receipt ledger, protected UNKNOWN and source-owned media integrity are untouched.
- Drive disconnected credentials were an external access/session issue, **not** a code defect or editorial regression; do not patch Drive OAuth or claim production backup repair.
- Do not replay rejected, queued or historical published material; installation means a fresh folder and no automatic migration of operator `Data`.

## Release process
- Source syntax/pytest and 25-post owner-cohort checks. Windows portable uses the pre-tested Python runtime/launcher from 2.3.53 with updated Python sources and release metadata.
- Runtime/GUI compatibility on actual Windows and LIVE Telegram editorial behavior remain unverified until operator runs the candidate. Do not label CI or Defender as PASS without evidence.
