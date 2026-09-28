# UA FREE Telegram Autopilot 2.0.0-rc99

Focused hardening candidate based on RC98 and independent code review.

## Fixes
- Distinguishes pre-send Telegram network failures from outcome-unknown failures so DNS/connect outages retry instead of parking posts forever.
- Prevents false HEALTHY worker state by separating worker freshness from collector heartbeat; watchdog recovers stale leases during runtime.
- Moves update discovery off Tk and raises polling/backoff intervals; RC99 disables automatic update application until cryptographically authenticated manifests are deployed.
- Fixes Tk exception callbacks that captured deleted `exc` variables.
- Preserves video attribution URLs in Telegram entities and fixes body-link stripping around punctuation.
- Defers unexpected publish exceptions instead of permanently parking articles.
- Treats provider-busy as short non-outage contention.
- Tightens monitoring policy: bare warnings such as “Новомиколаївка, уважно” are rejected for insufficient context before AI; settled aftermath remains eligible; sports/non-war “attacks” do not trigger the war gate.

## Safety
Stable media-delivery state machine, bounded Telegram stitching, storage claim semantics, dedupe-before-AI and provider error taxonomy remain intact.
