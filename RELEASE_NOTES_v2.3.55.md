# UA FREE Telegram Autopilot v2.3.55 — Windows Portable

Release candidate prepared 2026-11-24 from v2.3.54 source / PR #334.

## Owner-requested scope

### P0: restore quality output in ЗАПОРІЖЖЯ | ГРОМАДИ
- **One enforced regional writing floor.** Actual monitoring channel id=3 with configured 500+ meaningful source/final requirement: when an admitted original has >=500 source characters, writer and final editor now use a consistent 500-to-750 body target (bounded by actual channel policy and Telegram caption room). No earlier 220/350 fallback or schedule override can silently lower the final writer goal. Historical short-format test profiles remain unchanged.
- **No padding and no automatic post quota.** Sources below 500 meaningful characters continue to be rejected *before* paid AI and before dedupe. Sources with many promotional words but insufficient reportable facts may still fail factual QA; no synthetic context, quotes or fabricated contacts.
- **No accidental draft starvation.** The *actual* regional owner floor is checked while validating writer and final-editor candidates. A final editor cannot shrink an independently QA-verified 525-character draft to 402 and pass. If all final-editor attempts fail, the existing source-verified-draft fallback is retained only after all independent hard gates pass.
- **Bounded truncated-tail repair.** A detachable trailing colon heading after complete source-supported sentences may be removed if the remaining body still satisfies the required minimum. No arbitrary truncation, contact deletion, hallucinated ending, or incomplete fragment reaches Telegram. A missing substantive tail is still blocked.
- **Correct exhausted QA codes.** `TRUNCATED_TERMINAL_*` is `PREPUBLISH_TERMINAL_BLOCKED_2355`, not falsely `TELEGRAM_OVERSIZE_BLOCKED`. Real oversize, unsupported source facts and general prepublish QA receive their own codes.
- **Source name can be a local actor.** If a municipal donor-channel name literally appears in its own source as an institution participating in the event, it may occur as the real participant in the finished story, without granting permission for the generic phrase `за даними джерела` or unsupported publisher attribution.
- **Optional LanguageTool is harmless.** A grammar-polish proposal that fails any quality/source/floor check is ignored while keeping the already validated complete version.

### P1: reader-first newsroom writing for CTRL+UA and ПРОДАНО!
- New `story_brief_2355.py`: builds a deterministic, source-quoted 2–3-fragment newsroom brief for the existing author and editor. It identifies what a general reader needs, forces the source-bounded leading fact, keeps uncertainty, prioritizes one interesting twist and a small number of important explanatory details.
- Writer no longer receives the conflicting instruction to lead mechanically with participants before deciding on the main result. The editor checks the strongest sourced fact and preserves attribution/qualifiers.
- **No extra paid LLM call.** The already enabled AI writer/editor uses the new brief; it is not a separate generation pass, a frozen template or an excuse to fabricate an attention-grabbing angle.
- Video and visual source-policy checks from 2.3.54 remain unchanged. A filmed narrative ad needs an actual playable source-owned video, not a poster or bare link.

### Fixed invariants
- Telegram **900 total caption characters including any publisher footer**; normal body source-dependent margin enforced through `source_body_hard_limit`.
- Owner-accepted 21 historical stories remain eligible; four rejected formats continue to be vetoed. No new topic/category blanket bans and no minimum 500 for CTRL+UA / ПРОДАНО!.
- Minimum send intervals 30/30/5 min. Existing OpenRouter budgets $3 rolling 24h / $20 month. Existing dedupe, freshness, media provenance and delivery guarantees unchanged.
- No customer Data, credentials, operator SQLite, Telegram receipts, two protected UNKNOWN or replay in this package. Content Tool is separate.

## QA and release truth
- Local regression: full existing test suite + new 2.3.55 tests executed in isolated source environment with **no Telegram sends**; see run record separately.
- Authentic regional failure classes examined read-only from the operator's 24 November 2026 15:44 SQLite snapshot. No claim of successful new regional LIVE publication until owner runs 2.3.55.
- Portable uses the existing embedded Windows Python 3.12 runtime and launcher from 2.3.54; native Windows execution, malware scan and post-install publishing cannot be certified from this Linux build environment. Package ZIP integrity and code parity verified separately.

## Safe install
1. Close and wait for the previous Autopilot runtime to stop completely; do not run two versions.
2. Make an offline backup copy of the prior folder `Data/` (contains secrets and delivery ledger).
3. Extract 2.3.55 Windows Portable into a NEW folder. Copy the entire prior `Data/` folder into the new application directory while all instances are stopped.
4. Run `UA_FREE_Telegram_Autopilot.exe`. Confirm version 2.3.55, three workers/collectors, regional outcomes, the fresh backup snapshot and Telegram receipts.
5. If an operator issue arises, stop 2.3.55, restore 2.3.54 executable with the backed-up consistent Data state. Never replay UNKNOWN receipts automatically.

## Verification caveat
The software candidate, source code, native OS acceptance, GitHub merged release and actual operator LIVE installation are DISTINCT statuses. Publishing the ZIP alone does not make the operator run the new version.
