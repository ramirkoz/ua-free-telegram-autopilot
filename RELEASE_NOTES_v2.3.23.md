# Autopilot v2.3.23: editorial repair after the 2.3.22 LIVE failure

Date: 2026-11-11. Status: Windows Portable TEST release. **Not LIVE-accepted.**

2.3.22 ran from 10.11 09:20 Kyiv. By 15:31 it had published 2 of 119 processed stories in CTRL+UA, 0 of 14 in ПРОДАНО! and 17 of 344 in ГРОМАДИ, including four forbidden announcements. This release fixes the measured causes. Evidence: the operator SQLite snapshot of 10.11 (12 986 articles) and 1 472 unique operator labels from four returned XLSX files (no label conflicts between files).

## What was wrong and what changed

### CTRL+UA / ПРОДАНО!: the second opinion vetoed stories the selector had accepted
- The selector's JSON template showed `"fit_score":0`. Models echoed it (10–19), and every score under 40 was sent to a second review.
- The review template showed `"decision":"reject","reason":"конкретне пояснення"`. In 36 of 74 recorded review rejections the "reason" is that placeholder, verbatim.
- A rate cap of 8 reviews per 15 minutes rejected the rest (`REVIEW_CAP_REJECT`). An AI failure in the review was also recorded as a rejection (`REVIEW_UNVERIFIED_REJECT`).
- On labels, this stage rejected 83 wanted stories against 38 unwanted ones. After the 2.3.22 boot it killed 40 of 65 CTRL+UA and 7 of 18 ПРОДАНО! stories.

**Now:**
- Templates contain no ready-made answer. A copied placeholder is an invalid answer and the next model decides.
- The score no longer triggers a review. Only the concrete risk patterns are still reviewed: an agency appointment, an auction or second-hand listing.
- A cap or an AI failure defers the job. It is never an editorial verdict.

### ГРОМАДИ: announcements passed, facts were lost
- **New source-only veto for calls to action** (`monitoring_call_to_action.py`): survey or questionnaire invitations, ticket giveaways, application or registration calls, playbills of future events, and reader complaints relayed without official confirmation. It runs at selection and again right before a Telegram send for older READY rows. A finished event, a decision, a service change and social aid are never vetoed by it.
- **Outage schedules are news.** A forwarded power, water, gas or heat schedule is no longer rejected as a repost. A schedule written as a time table passes the two-sentence source floor. Other forwards stay vetoed.
- **Aftermath is not a threat signal.** A report with an outcome (a person wounded, a house on fire, a target hit) is no longer rejected as a "direction of threat" alert. "Ланцет на Оріхів" still is.
- **Long narratives are not alerts.** The post-factum alert rule applies to short signals only. A long story that merely mentions drones is judged by the selector.
- **Frontline summaries** attributed to the General Staff are not rejected as tactical chatter. Number and fact checks are unchanged.

### Writing and QA: correct drafts were rejected, and a working provider was "not configured"
- **Number check** (`numeric_grounding.py`): source `10.00` or `10-00` supports `10:00` in the draft. Numbers glued to a word in Telegram text (`20.11.2026Про`, `+380672738096Не`) are recognised. An invented number, a changed count or a malformed time is still reported.
- **"No AI provider configured" at the final editor.** The trusted-editor whitelist predates the "OpenRouter serves every purpose" contract and excluded OpenRouter, so no route was left. Under that contract a caller's whitelist no longer excludes OpenRouter.
- **Unreliable models go last per task.** A model that keeps breaking a task's output contract (no JSON, empty answer, reasoning only) is tried last for that task instead of burning the first attempt of every article. In memory only; operator configuration is untouched.

### Dedupe: shared footers were "the same event"
- 164 of 165 recorded cluster duplicates were pairs from the same publisher, and 134 shared no headline word. They were different posts joined by a channel footer ("Ми в WhatsApp / Instagram / TikTok") or a series intro. A cluster duplicate now needs a shared headline term or an exact scientific-name anchor. 147 of the 165 are released; exact and same-event duplicates are unchanged.

### Learning: one dislike suppressed unrelated stories
- A hard veto fired at similarity 0.18–0.32 (a water bottle, an animator and a type designer at 0.19–0.21 to one disliked post). It now needs a near-identical story (≥ 0.60 and 8 shared terms). Weaker likeness remains a soft adjustment.

### ПРОДАНО! sources
- One-time, idempotent, exact name+URL migration; rows are disabled, never deleted:
  - **Disabled:** My Modern Met (HTTP 403 on every fetch), Trend Hunter (feed returns 0 items), Fast Company (no item has a verifiable date, so all fail the source-date fence).
  - **Added:** designboom — Art and The Awesomer. Both passed the project's own collector on the operator machine on 11.11 (dated items, 4 and 9 in 24 h, text and source media).
- The runtime-start and source-day fences are **not** changed. The "226 stale" figure in telemetry is old feed items already seen in earlier runs, not lost input: 18 new ПРОДАНО! stories did arrive after the boot.

## Measured effect (same corpus, before / after)

Thematic selection, "selected" = reaches writing. Later fact, media, freshness, duplicate and QA gates are not assumed to pass.

| Channel | Version | TP | FP | FN | TN | Precision | Recall |
|---|---|---:|---:|---:|---:|---:|---:|
| CTRL+UA (n=484) | 2.3.22 | 42 | 5 | 293 | 144 | 89% | 13% |
| | 2.3.23 | 107 | 28 | 228 | 121 | 79% | 32% |
| ПРОДАНО! (n=273) | 2.3.22 | 29 | 9 | 102 | 133 | 76% | 22% |
| | 2.3.23 | 47 | 24 | 84 | 118 | 66% | 36% |
| ГРОМАДИ, deterministic gates (n=672) | 2.3.22 | 169 | 19 | 163 | 321 | 90% | 51% |
| | 2.3.23 | 193 | 27 | 139 | 313 | 88% | 58% |

- CTRL+UA and ПРОДАНО! rows use the recorded live selector verdicts; the AI selector itself cannot be replayed offline.
- ГРОМАДИ rows are a real replay of both code versions with one channel config and no AI calls.
- In ГРОМАДИ, 22 rows the operator marked as wanted are now blocked by the no-announcement rule (surveys, application calls, playbills). The hard policy outranks the topical mark.

Named cases: Telegram #4727, #4736, #4740, #4742 and playbill #4728 are blocked before writing. Controls #4737, #4750, #4751, #4724, #4741, #4755 and the finished-event posts #4738, #4743 pass.

## Not changed
Operator `Data` and history, the two protected Telegram UNKNOWN states, no automatic resend of FAILED, intervals 45/30/5, budgets $3/day and $20/month, Fact Guard, Media Guard, source ownership of media, runtime-start and source-day fences, Telegram dedupe.

## Known limits
- The effect of the new prompt contract on live model answers is not measured: no AI calls were made in testing. The offline numbers above come from recorded verdicts and deterministic gates.
- ПРОДАНО! precision on the corpus falls from 76% to 66% because the removed review also stopped some unwanted stories. Watch the first day of output.
- The channel policy text used for the ГРОМАДИ replay is the operator's 19.10 version; the sanitized snapshot does not carry policies.
- Remaining losses not addressed here: source-day freshness rejections (43 wanted CTRL+UA rows on the corpus), short RSS excerpts of some publishers, true same-event duplicates.

## Installation
Stop Autopilot. Back up the complete `Data` folder. Unpack 2.3.23 into a new empty folder, move `Data` into it, keep the 2.3.22 folder for rollback. Never upload `Data/secrets.*`.

## LIVE acceptance (operator)
Count only posts published after the 2.3.23 start. ГРОМАДИ: no surveys, giveaways, application calls, playbills or relayed complaints; outage schedules and aftermath reports present. CTRL+UA: no `EDITOR_2321_*` rejections in telemetry except risk-title reviews. ПРОДАНО!: non-zero output when new stories arrive; the two new sources show items after their first cycle.
