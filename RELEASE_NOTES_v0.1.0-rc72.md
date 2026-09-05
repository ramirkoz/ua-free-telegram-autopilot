# UA FREE Telegram Autopilot v0.1.0-rc72

## Restored per-channel fine controls

RC72 restores the channel-specific manual policy editor that was accidentally hidden by later UI layers.

Each channel can again configure its own:

- mission / purpose;
- audience;
- inclusion / selection rules;
- exclusion / rejection rules;
- writing structure;
- tone and style;
- positive and negative examples;
- media policy;
- target post length;
- additional channel rules;
- selector prompt additions;
- writer prompt additions.

These settings are channel-local. Channel names are never used as hidden routing or editorial rules.

## Architecture contract

Only universal mechanisms remain under the hood: collection, dedupe/clustering, Fact Guard, language/media infrastructure, scheduling, QA, the editorial/monitoring branch and the universal Editorial Value Gate for editorial channels.

Editorial channels use their saved channel policy for Channel Fit, then the universal Editorial Value Gate runs separately.

Monitoring channels do not use Editorial Value, broad-interest scoring or thematic balance. When an explicit policy has been saved for a monitoring channel, RC72 applies only that channel's inclusion/exclusion rules. Old monitoring channels without an explicitly saved fine policy retain the previous fail-open behaviour instead of inheriting a hidden legacy editorial profile.

## Compatibility

RC72 keeps RC69 media-first settings, RC70 mixed Ukrainian/Russian input support and RC71 contextual freshness / deferred media pipeline behaviour.
