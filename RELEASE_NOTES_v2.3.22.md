# Autopilot v2.3.22: no classifieds; ПРОДАНО! consumer-first

Date: 2026-11-09. Changes based on human operator review of 2.3.21 actual posted messages and operator's explicit additional editorial orders.

## Regional monitoring: NEWS ONLY, NO ANNOUNCEMENTS

- New source-only non-AI exclusion for private classifieds, lost-and-found, private contact allegations, job ads, commercial sales offers, bare event invitations, greeting-only posts and standalone 'Оголошення' banners. No automatic sanitization of private persons' details for a news story that should not exist; reject the entire announcement instead.
- Safety check runs both during initial selection and at `hard_editorial_reject` immediately before publication (including READY items created under earlier builds). No bypass by AI or manual approval.
- Do not infer the owner of found documents is responsible for a neighboring story (2026-11-09 GR #94596 / Telegram #4689 incident). The software update cannot edit an already published Telegram message; operator should review it manually.
- National-only Defence Ministry military accounting paperwork is out of scope without a verified local event. Actual local service changes and independently verified regional civic events remain eligible.
- Do not remove legitimate local official instructions/verified service disruptions solely because they contain the word `повідомили`; they are news, not classifieds.

## ПРОДАНО! sources reoriented away from professional marketing journals

- Idempotent one-time exact-name-and-URL migration from the original commercial channel: **disable** Famous Campaigns, Campaigns of the World, Muse by Clio, Campaign Brief, Shots, Creative Review, The PR Insider, Adweek, Ads of the World, The Drum, Contagious, Ad Age, and 403-producing The Dieline / COOL HUNTING. Disable is not delete; historical article/source IDs preserved.
- Promote remaining consumer-facing creative sources: It's Nice That, Yanko Design, Creative Boom, Colossal, Creative Bloq, designboom Design, Dezeen Design, Design Milk, Design You Trust, Core77, Trend Hunter and other original sources only where exact URL identity matches.
- Add **My Modern Met** (`https://mymodernmet.com/feed/`) and **Laughing Squid** (`https://laughingsquid.com/feed/`) as new, publicly working RSS streams, initially uninitialized. Operator-network freshness, media and actual publication yield require new-version LIVE verification. A public feed listing is **not** evidence of local Windows collector success.
- All custom/user-added sources, other channels, budgets, publish schedule, media authenticity and existing queue/delivery history remain unchanged.
- Calibrated selector instruction: the audience is a normal curious human, not a marketing specialist; choose surprising creative/human-interest stories with concrete source evidence, reject staffing, B2B appointments, trade analysis, mundane product catalogs. No automatic quotas or replays.

## Quality and safety

- Source-owned unnecessary article/Telegram URLs are stripped from monitoring draft text **before** writer QA, with existing exact-source and factual validation unchanged. Prevent repeated AI attempts on already-attributed source links.
- Fix no image by genuinely sourced photos or videos from the existing strict first-party media collector. Do **not** permit site-wide OG cards or cross-story images to boost throughput.
- New synthetic in-memory regressions for announcement/personal info bypass, regional scope, duplicated source links, and exact-name+URL commercial portfolio migration.
- `Data`, existing operator credentials, protected Telegram delivery UNKNOWN (2), restart/no-replay fence, article history, 45/30/5 minutes, daily $3 / monthly $20 budgets, Fact/Media/Telegram safety stay untouched.

## Gates

Before tagging: full Ubuntu and Windows Python 3.11/3.12/3.13 CI, Windows portable package/Defender, first-run tests. Installation and editorial results are separate from build success. Following operator install, verify updated 2.3.22 boot and at least one real post/source review for each productive channel, with particular attention to ПРОДАНО! source throughput; do not claim fixed live until observed.
