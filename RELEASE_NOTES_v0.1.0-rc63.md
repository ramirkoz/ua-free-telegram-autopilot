# UA FREE Telegram Autopilot v0.1.0-rc63

RC63 is a focused training-mode hotfix for the first RC62 live run on 2026-09-02.

## Why this release exists

RC62 added channel-wide daily and rolling burst caps to stop the CTRL+UA flood. On the existing production Data, the earlier RC61 morning burst had already exhausted the new calendar-day cap before RC62 started, so CTRL+UA could be held for the rest of the day even though fresh candidates existed. That is counterproductive while the editorial model is still being trained from operator reactions.

## What changed

- **No publication-count caps while training.** RC63 removes the RC62 daily post cap and four-hour N-post burst cap from the channel-level publication gate.
- **No calendar-day lockout after an earlier burst.** Posts published by a previous version earlier the same day cannot freeze the channel until midnight.
- **Minimum spacing remains.** CTRL+UA keeps at least 60 minutes between successful publications; marketing profiles keep at least 90 minutes. A larger operator-configured minimum still wins.
- **Quiet hours remain 00:00–07:00 local time.** This is a time-of-day hold, not a publication quota.
- **Editorial diversity remains.** Source/topic saturation still defers repetitive candidates; it does not impose a total number of posts per day.
- **Learning remains active.** RC62 semantic 👍/👎 learning, 🔥 style memory, ПРОДАНО! human-interest gate, same-news-cycle dedupe, final Ukrainian QA and video/source footer fixes are preserved.
- **Diagnostics are explicit.** RC63 logs installation and rate-limited HOLD reasons (`quiet_hours` or `spacing`) with the next allowed time. The log explicitly states that publication-count caps are disabled.

## Data / schema

- Existing RC62/RC61/RC60 Data is compatible.
- No destructive migration.
- Existing reactions, publication history, channels, sources, priorities, Telegram sessions and editorial policies are preserved.

## Intended training behaviour

During the learning phase, publication volume is determined by the flow of candidates that pass editorial selection, dedupe, QA, source/topic diversity and the time-spacing gate. There is no fixed daily or rolling publication quota. Count caps can be reintroduced later if live data shows they are useful.
