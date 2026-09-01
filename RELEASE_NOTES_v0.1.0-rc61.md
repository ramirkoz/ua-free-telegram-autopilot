# UA FREE Telegram Autopilot v0.1.0-rc61

RC61 is a production-blocker fix based on the working RC60 baseline and the 2026-09-01 production Data snapshot where CTRL+UA was publishing but ПРОДАНО! had zero successful posts.

## What changed

- **Freshness no longer starves the channel.** Old dated rows are rejected in the pending-queue prefilter before AI/media work and do not consume the per-cycle processing budget.
- **Recent freshness rejects get one bounded recovery pass.** Up to three recent article-like page items per source are re-opened once so the stronger extractor can recover dates from the real article page without resurrecting people/agency/company directory noise.
- **Page-source discovery is article-aware.** Internal links are ranked; real `/news/...`, `/news/view/...`, `/campaigns/...`, `/article/...`, `/story/...` links outrank profile/directory pages. `/people`, `/agencies`, `/brands`, `/companies`, jobs/login/etc. are excluded.
- **Published-date extraction is stronger without becoming permissive.** RC53 metadata/JSON-LD/URL rules remain first; RC61 additionally handles common creative-industry bylines such as `by … on 1st September 2026` and broader JSON-LD quoting. If no defensible date is found after article re-fetch, publication still fails closed.
- **Telegram photo uploads normalize modern CDN formats.** AVIF/WebP/GIF and other non-JPEG/PNG image responses are converted locally to bounded JPEG before `sendPhoto`, preventing a valid ПРОДАНО! story from dying at the final Telegram media call because an Imgix-style CDN honored `auto=format`.
- **Missing page dates are re-fetched once before strict rejection** and persisted into the existing article row.

## Data / schema

- Existing RC60 Data remains compatible.
- No destructive migration.
- Existing source priorities, channel policies, reaction learning, article history and Telegram sessions are preserved.
- One app-state marker per channel prevents freshness-recovery loops.

## Verification

- `python -m compileall`: PASS.
- Full local pytest suite including new RC61 regressions: PASS.
- New regressions cover page-link ranking, human byline date extraction, JSON-LD date extraction, WebP→JPEG Telegram normalization and stale high-priority prefilter behavior.
- RC60 production Data dry-run: fresh Muse by Clio items remain first for ПРОДАНО!, stale low-priority backlog no longer consumes returned queue slots, and only bounded recent article-like freshness rejects are recovered.
