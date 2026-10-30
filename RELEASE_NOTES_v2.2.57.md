# Autopilot 2.2.57 — ПРОДАНО!: distribution of genuine stories, not a design catalog

## Origin (operator LIVE evidence)
- Current installed 2.2.56 at 2026-10-30 13:01 Kyiv is RUNNING 3/3+3/3, 937 COMMITTED / one protected UNKNOWN; no newly authored 2.2.56 posts at that snapshot. Editorial acceptance for 2.2.56 remains unproven.
- Source cohort 24h: Yanko Design **6/8 published (75%)**, Creative Bloq 1, Campaign Brief 1; 6/18 commercial sources in cooldown. Previous observed 23–27 Oct Yanko 20/35 (57%) and 28–30 Oct 14/18 (78%). Operator requires wide-audience surprising, viral, funny, culturally significant brand/human interest; not a product design catalog.
- The previous 'published-source fast-first' order gave Yanko additional first-place advantage because it already published most posts. This is a self-reinforcing schedule bias, though not the only cause: editorial and source freshness also matter.
- Official live listings on Famous Campaigns include current entertaining brand stunts and visual stories, but prior collector produced `EMPTY`. Root cause candidate found in common HTML anchor parser: every void-tag `<img>`, `<br>`, `<source>` changed depth without an end-tag, so `</a>` around image-heavy article cards was ignored.

## Changes
1. **Read-only 7-day post-source concentration signal**, actual `published_at`, not picked/rejected/intake counts; used solely to **order** enabled `commercial_editorial` collection. If >=12 real published posts from >=2 sources, penalty applies to any source with >30% share. Max 25 ranking points. Existing base priority, cooldowns, enabled source list, access policy, selector/QA and publication rules unchanged. No source blocked, disabled, hard publication cap or forced low-quality stories; never penalizes without meaningful sample.
2. **LIVE collector integration** through `bounded_ingest.py`, alongside existing 24h yield and cost-aware fetch depths. One inexpensive aggregate SQLite read; emits `commercial source diversity advisory 7d` with source concentration / shortlist; no schema migration, extra AI calls, or network probing.
3. **Image-rich homepage link parsing fix** in `collector._LinkParser`: HTML void tags no longer alter nesting depth, including self-closed tags. Re-enables full link extraction for verified public campaign pages, including the existing *Famous Campaigns* home page. The actual operator network should confirm collector yields; a web page or a synthetic fixture alone is **not** operator success. An existing source with HTTP403 remains blocked; nothing circumvents it.
4. Regression for source share accurate counting / other channels, soft ordering, sample gates, void/nested tags and page collector output. No new source records added on mere URL visibility.

## Unchanged invariants
- Three existing channels, 36/18/57 enabled-source roster configuration, channel intervals 45/30/5 minutes, source cooldowns, operator priority settings and custom URLs, Data/SQLite schema, Telegram at-most-once/UNKNOWN quarantine, media provenance, existing Fact Guard 2.2.55 and broad-audience reader 2.2.56.
- OpenRouter $3/day and $20/month caps, other AI provider configuration, no extra requests. Public website visibility is not proof that a source can be scraped from operator's network.
- **Known issues not solved:** strict runtime freshness fence after restarts (cannot remove without replay risk), HTTP403 Design Milk / Rest of World, slow Shots/Ad Age and AI QUALITY failure rate. These remain explicit P1 backlog. Human/source post QA needed.

## Release gate
PR Ubuntu + Windows (Python 3.11/3.12/3.13) full test matrix, Windows Portable & Defender, merge to main, official release asset, then separate operator telemetry validation. User's request was a **new installable version**: do not report a draft PR as released.
