# Autopilot 2.2.14 — Source-owned monitoring relevance guard

**Operator incident:** [#210](https://github.com/ramirkoz/ua-free-telegram-autopilot/issues/210). The v2.2.13 sanitized operator SQLite confirmed two `READY/PUBLISH` candidates in an opted-in monitoring feed that were not local news: #70403 (temporary Telegram invite-only bait) and #71020 (speculative TikTok/AI historical-figure meme). The model marked both `MONITORING_POLICY_PASS [local_news]`; media failure, not editorial quality, was the only gate withholding them.

**What changed:**
- A deliberately **narrow, high-confidence, original-source** check rejects a vanishing private group invite without any source-owned public/civic service or event, and speculative social-media memes without an original source-owned local event. It never infers locality from the feed's brand/name or rewrites.
- Relevance check runs before the AI monitoring selector **and** through `hard_editorial_reject` on READY/PUBLISH before Telegram calls. Old queued candidates receive the same gate; no existing published article is edited, deleted or resent.
- Genuine local municipality Q&A #71506, local emergency summaries, public meetings and local arts/AI exhibitions remain eligible. Another editor/channel isn't affected unless its own existing `[LIVE_NOW_RC96]` rejection policy opts into monitoring safeguards; never hardcode channel ID/name or disable `zaborzp` source.
- Scoped regression tests include the actual negative source texts, the same-source positive report, community event/assistance invitation, an AI cultural exhibition, absence of opt-in, and a separate editorial channel.

**Preserved, unchanged:** 2.2.13 SQLite recovery on restart, independent immutable delivery receipt archive, confidential hourly operator SQLite backup/Google Drive telemetry, 3-channel worker/collector scheduling, original Telegram media parity, delivery UNKNOWN quarantine (#66297), configured source priorities, operator intervals, models/budget and existing source lists. No historical message replays, no operator Data migration required.

**Release gates:** GitHub PR CI + independent native Windows Portable build on `main`, verify official release asset integrity, preserve separate operator LIVE acceptance after installation. Do not present a PR candidate as the final official build.
