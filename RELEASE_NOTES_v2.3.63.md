# 2.3.63 — editorial phase reserve and conservative quality stabilization

Base: exact 2.3.62 candidate (main merge 8a1031218614d711b8f50782d4cbf4411718ee8e).

- Reserve total/editorial attempts by purpose: selector cannot consume last three total attempts; writer leaves two, final editor leaves one for reader. Five editorial/eight total attempt maxima and observed $0.010 article admission threshold remain unchanged. Existing spend and counters are not reset. Reserved attempts are not a reservation of dollars and cannot override the actual-spend gate. No new permission to publish without verified reader receipt.
- Validated selector response cache is runtime-local, bounded to 256 entries/15 minutes, scoped to exact prompt hash, channel/article, purpose and route list. Revalidate on reuse; all local source, policy, freshness and saturation checks still run. No cache of final publication decisions.
- An explicit final-editor reader veto ends the call cycle immediately, instead of trying a more permissive model. Existing final QA and receipt/delivery protections remain.
- Writer gets explicit length and sentence/paragraph guidance. ПРОДАНО! prompts ask for plain Ukrainian without strengthening scientific causality. Conservative paragraph split only for a paragraph-only QA error and only after unchanged full validator accepts; no automatic sentence rewriting.
- Count prompt sections and separately report provider tokens, add rejected-article recorded cost in the runtime window and ready-time classification for delivered bodies. Ready-time classification is not proof of new generation.
- Skip manual probes only for explicitly retired HTTP 410/EOL models; retain operator config and other model health diagnostics. No direct-free production routing change.

Not included: hard context truncation/target token reduction, automatic sentence rewriting, deterministic outage schedule rendering, broad regional policy changes, new provider parameters for Cloudflare Gemma/reasoning-only replies, authenticated free-model qualification. Those require separate source-grounded evidence/testing. Existing global limits, 30/30/5 cadence, sources, operator data and credentials, delivery/UNKNOWN safety, and Content Tool unchanged. Windows LIVE/native build and actual cost/throughput gains remain unverified. Locally assembled candidate, not official GitHub workflow release.
