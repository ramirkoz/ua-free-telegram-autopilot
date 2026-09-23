# UA FREE Telegram Autopilot v2.0.0-rc72 — MANUAL TEST

Channel-policy / operational tuning only. Core stitch, Telegram ownership and web-media extraction from RC71 are unchanged.

- Existing channels explicitly using `commercial_editorial` receive a new visible `[BROAD_AUDIENCE_RC72]` policy seed. Broad-audience stories are easier to pass; routine professional case-study lanes are stricter.
- The target mix is written into the channel's normal selection/rejection/selector/writer settings: roughly 70–80% broad-interest stories, professional cases as a minority format.
- `media_policy=required` remains enforced for the commercial-editorial profile. No return to text-only publishing.
- Broad/editorial thresholds are ordinary visible `editorial_thresholds_json` values and stay editable in Channel Settings.
- `TELEGRAM_VIDEO_PENDING` no longer wakes the same processing job every five minutes. The universal retry is at least 30 minutes or six configured poll intervals, whichever is longer.
- A later source refresh that recovers the real video still requeues the job immediately, so the longer backoff does not delay successful recovery.
- No channel name or ID is hard-coded. CTRL+UA policy is untouched.
- MANUAL TEST: no auto-update promotion.
