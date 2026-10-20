# Autopilot v2.2.9 — P0 live security alerts must not reach ГРОМАДИ

## Operator evidence 20 October 2026

- Installed 2.2.8 unexpectedly published article **68340** at **14:46:25 Kyiv** into ГРОМАДИ Telegram destination **3202**, from the exact public source post `https://t.me/zaborzp/154829`.
- Original source headline was a short operational drone/weapon location alert ("Ланцет на Піски"). Its Telegram message text was rewritten as a current live warning. Not a settled reported event. This is expressly excluded by monitoring policy.
- AI selector marked **PUBLISH** with `MONITORING_POLICY_PASS: [local_news]` and fit **100**, while adjacent active-alert posts were correctly rejected. Root cause: deterministic live-now and postfactum security vocabulary missed this drone type and verb-free "weapon + area" bulletins.
- The program's green `HEALTHY` label measures runtime/source health, not policy correctness. No remote cancellation and no automatic delete/replay of the already published destination message.

## Code changes

- Add a *source-text deterministic pre-AI and prepublish veto* for short active weapon + locality/direction alerts, including "Ланцет" and related FPV forms. This is independent of AI event label, fit score and an opt-in policy marker.
- Expand the opt-in `LIVE_NOW_RC96` lexicon as an additional independent fail-closed check for the same class of active alerts. Completed news with verified results remains eligible for editorial review.
- Regression exercises the exact escaped Telegram text, alternate live alert wording, a fake model that must never run, historical summaries and harmless community reports, plus channel isolation.
- Does **not** modify Telegram photos/videos, media download, source settings, OpenRouter routing or the 2.2.8 web image provenance fix.

## Release gate

GitHub PR CI and Windows Portable build required before marking release ready. Then operator manual install and **LIVE acceptance**: no short tactical alert may be delivered to ГРОМАДИ even when AI mislabels it local_news. Do not auto-republish/edit already committed Telegram items and preserve all operator Data and delivery ledgers.
