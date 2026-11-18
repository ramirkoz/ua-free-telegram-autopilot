# Autopilot 2.3.39: owner-rejected LIVE posts and committed cross-source events

18.11.2026. **WINDOWS PORTABLE QA CANDIDATE. NOT INSTALLED. NO PRODUCTION GO.**
Stacked on 2.3.38 draft PR #316; operator remains v2.3.37 Windows LIVE.
No changes to operator SQLite, installed Data, Telegram, media/source settings,
publication cadence (30/30/5), OpenRouter limits, or UNKNOWN delivery safety.

## Verified operator evidence (READ-ONLY, 18.11 08:57 Kyiv)

- ПРОДАНО! #1196 / article #104290: ordinary Flatbush rescue of cat Isaac,
  from Laughing Squid, passed commercial editorial selection without a
  meaningful creative/commercial mechanism. Explicit operator negative.
- ЗАПОРІЖЖЯ | ГРОМАДИ #5183/#5191, source article IDs #104329/#104380:
  city council and another channel repeated the same story about traffic lights,
  backup batteries, replacing drained units and generators 37 minutes apart.
  Existing title/URL/incident dedupe missed source paraphrases.
- #5189 / article #104337: request addressed to облeнерго to publish outage
  information, not a verified official service update. Rewriter introduced a
  dangling "тут:" service URL ending. The latter remains subject to separate QA.

## Change

1. Creative source-only gate: reject routine lost/rescued pet reports with no
   verified original artistic, engineering or creative mechanism. Preserve novel
   devices, original creative campaigns and truly interesting animal research
   as eligible to pass normal editorial checks.
2. Civic source-only gate: a direct plea/complaint with no official new fact
   cannot be converted into a news item merely because two source sentences
   are present. Do not suppress real restoration/service updates.
3. Conservative source-fact same-event checker: cross-source text stems must
   have >=6 shared content anchors, >=60% containment of the shorter source,
   >=2 headline anchors, and no new confirmed outcome, quantitative fact,
   conflicting service status or distinct named street. Only checks a 6-hour
   window of prior Telegram COMMITTED publications, in the same channel.
   It cannot treat READY, UNKNOWN, FAILED, source discovery, or AI drafts as
   proof of publication.
4. Check #3 before paying for AI (DedupeEngine) and again immediately before
   Telegram (Publisher), including previously prepared READY items. No new AI
   requests and no source/model-specific hardcoding.
5. Added targeted regression tests for 3 owner RED examples plus real creative
   engineering, official utility update, substantial status/number/location
   changes, committed-only delivery and channel isolation.

## Safety / incomplete gates

- Tests authored and source branch inspected; **full pytest / independent CI /
  native Windows and Defender are not verified**. The archived operator SQLite
  was read-only; do not claim 2.3.39 LIVE improvement or production acceptance.
- Before GO: run targeted test file and complete suite; replay relevant
  owner-positive controls; build signed/verifiable Windows Portable from
  stacked branch; install only after operator acceptance; monitor 24-48h posts.
- Current source-only controls do not reclassify past published Telegram posts
  or delete previously published duplicates.
\n## QA result (18.11.2026)\n- 177 focused/related pytest cases PASS on Linux Python 3.13.\n- Source file GitHub blobs checked before assembly; source and Windows QA ZIP CRC verified.\n- One inherited v2.3.35 broad roundup rule rejected two genuine original art cases in v2.3.37 tests; narrow source-backed art exception added and both controls PASS.\n- Full pytest is INCOMPLETE (timed out about 61%, no failure shown before timeout); no native Windows launch/Defender, no independent CI and no post-install acceptance.\n- Portable QA assembled from v2.3.36 Windows baseline, with exact 2.3.39 source files overlaid. No operator Data/credentials, no signed updater GO.\n\n- Read-only operator SQLite replay exact IDs 104290/104337/104329/104380/104373: pet and appeal rejected, duplicate traffic-light story matched, distinct utility restoration not matched.\n