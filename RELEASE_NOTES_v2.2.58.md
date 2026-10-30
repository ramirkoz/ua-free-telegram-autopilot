# Autopilot 2.2.58 — editorial theme balance for ПРОДАНО!

## Why
Observed before 2.2.57: source Yanko Design supplied 20/35 posts (23–27 Oct)
and 14/18 posts (28–30 Oct); often a succession of ordinary tiny homes,
gadgets and furniture. 2.2.57 addresses collection order, not the actual
topic mix in the published feed. Operator 2.2.57 was confirmed running
13:45 Kyiv 30 Oct, but its editorial result still requires natural posts.

## Changes
1. New read-only seven-day published-feed theme diagnostics:
   conservative headline-keyword categories, counts, last-six theme sequence,
   consecutive topic run and similar-headline *advisory* pairs. Exact 7-day
   original-source shares are reported alongside theme samples. Explicit
   sample cap (160 posts), unknown categories remain "other"; never call
   a lexical match a proven same event.
2. Existing *single-call* RC102 commercial selector receives a short,
   factual feed-fatigue hint only when the same lexical theme is present at
   least twice in the previous six published posts or a similar headline
   occurs. This asks for a genuinely new source-grounded reader hook,
   **not** an automatic block, quota, lower threshold or duplicate judgment.
   Non-commercial selection stays unchanged. Legacy selector gets the same hint.
3. LIVE supervisor exposes \`commercial_topic_mix_7d\` by channel for
   post-release, read-only evidence. Includes theme counts, current thematic
   streak, similar headline pair count and top original-source shares.
4. Regression tests cover theme runs, actual published-only scope,
   seven-day source shares, advice-only semantics, unrelated topics and
   read-only database invariant.

## Not changed
Source lists/priority/cooldowns, operator Data, any database schema, Telegram
receipts, UNKNOWN quarantine, channel intervals 45/30/5 minutes, AI model
routing or call count, OpenRouter caps ($3/day, $20/month), Fact Guard, media
ownership and 2.2.56 reader-first selection. Broad-audience weak stories
do not get published merely to fill an under-represented topic.

## Acceptance still pending
CI + signed portable Windows + Defender are release gates; actual
2.2.58 theme mix and quality require new real operator posts. Existing
HTTP403 feeds, startup freshness fence, AI QUALITY retries and media gaps
remain on the ProductVault P1 roadmap.
