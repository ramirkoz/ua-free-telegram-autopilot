# UA FREE Telegram Autopilot 2.3.27 — Editorial Rebuild candidate

**Release status:** Windows Portable candidate; operator LIVE verification is **not** yet complete. Based on the actual v2.3.26 portable, preserving its binary runtime and all existing operator policies. Do not merge code before inspecting LIVE output.

## Operator-approved scope, implemented in this candidate

- **All 31 RSS channel assignments in one idempotent migration** (15 CTRL+UA and 16 ПРОДАНО!, 29 distinct feed URLs). Existing canonical matching feeds are activated, original custom source rows and foreign-key IDs are preserved. New ones are inserted with initialized=0; old Telegram receipts never replay. Each RSS independently reports actual collector health, including 403 and empty responses.
- **Six Telegram channels registered as topic-only discovery references**, deliberately outside the publishable `sources` table. This is a safe reference registry, **not yet an automatic TG-to-primary-source discovery engine**; no unverified fan post, forwarded photo or rumor can be published because of this registry.
- CTRL+UA/ПРОДАНО! get updated topic preferences and reader-first hook → substance → source-grounded finish. **350–600 chars is a soft editorial target**, not a new hard failure. GR policy untouched. Existing positive examples and 1,472 operator labels remain authoritative.
- **Actual OpenRouter cost accounting:** new usage rows include scoped channel/article IDs; older records explicitly remain unattributed. Supervisor telemetry includes 24h real charged USD, 24h COMMITTED deliveries and unit USD/post, breakdown by channel/purpose/model, three completed Kyiv calendar dates, at-risk writer spending and alerts. Keeps $3/day and $20/month budgets. OpenRouter website's 30-day account spend cannot be inferred as Autopilot November expense.
- Writer + final_editor accounted for 84.4% of prior rolling-24h expense. **Skip a second paid full-length final AI edit when a draft already scored >=95 and passed existing language/grammar/style/factual QA; retain all independent final/source/Telegram checks.** In all other cases trusted final edit remains.
- On source-media-required editorial posts, **preflight existing source-owned media after editorial selection but before paid writer**; when none can be verified using the publisher's existing exact-source recovery, defer as MEDIA_PREWRITE (without AI cost), never use a foreign stock image or downgrade the media rule. Existing 45/30/5 cadence and 08:58 fixed post untouched.
- Supervision shows 31 RSS registration results and first live collector health. Provider Gemini/Cloudflare schema issues are explicitly **not** declared solved without real provider response data; all known working AI routes preserved.

## Immutable safeguards

No Data or Telegram-delivery journal wipe, no UNKNOWN/FAILED replay, no changes to tokens/credentials, source URL identity, human labels, 45/30/5 minute minimum intervals, publisher factual/media constraints, regional no-announcement policy, or existing daily/monthly AI budgets.

## Acceptance gates

1. Windows executable starts, standard four operator checks (Drive/OpenRouter/Codex/Test All AI) work; no UI regression.
2. Exactly 31 canonical RSS channel assignments and 6 distinct topic hint registrations; no historical re-posts, no ad/trash from hints. Actual per-feed 200/403/dating evidence after collection.
3. New science/commercial material reaches Telegram with correct original media; community news remains fact-only, announcement-free.
4. At least one full publication interval for each channel passes, with reviewer checking original source, Ukrainian copy and media.
5. Actual cost per COMMITTED publication, waste on blocked media, split by channel and editorial task, monitored over matched windows; three previous completed calendar dates separate from rolling 24h.
6. 1,472 workbook labels must be replayed before acceptance. Candidate tests are **not** that full replay.

**Not claimed:** proven Windows LIVE publishing, RSS 31/31 HTTP successful, six active TG discovery pipelines, or full external API repairs.
