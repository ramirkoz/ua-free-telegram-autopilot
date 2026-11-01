# Autopilot v2.2.63 — editorial integrity and AI route efficiency

*1 November 2026; next release after 2.2.62, not a live-operator claim.*

## Verified LIVE source basis
Operator snapshot 01.11.2026 14:55 Kyiv on **v2.2.61**: 3 workers + 3 collectors,
65 historical publications in the 2.2.61 run, 4/7 healthy AI providers,
ling reasoning-only output, Cloudflare reasoning-only output, local Ollama 120-second
timeout, repeated QUALITY retries/exhaustion. Actual published rows:
- #87658 Halloween social solicitation: the rewrite claimed "Ми є у WhatsApp,
  Instagram, TikTok і Threads" on behalf of our regional channel.
- #87615 copied the outside publisher's "Гортайте картки" and "діліться
  історіями в коментарях" as our channel's instructions.
- #87338 an anonymous consumer complaint identified a restaurant but never
  described the allegedly offensive object on the photograph, only an
  insinuation "комплімент від шефа"; no invented image facts are permitted.
- #87860 science news said "210 учасників 11–18 рік" instead of the
  grammatically valid, number-preserving "210 учасників віком від 11 до 18 років".

## Changes
1. Monitoring-only source gate rejects short pure third-party channel social
   promotions without an actual civic event; preserves ordinary reports with
   concrete events and actionable verified details.
2. Monitoring writer/final/pre-Telegram source-body gate disallows external
   publishers' self-promotion, carousel/swipe instructions and comment-farming
   CTAs presented as our channel voice. No blanket suppression of reporting,
   official addresses, phone numbers, or source footer links.
3. Source completeness fails closed for the precisely attested unverified,
   photo-dependent private-business insinuation. Do not invent image contents
   or promote anonymous hearsay into fact.
4. Narrow local Ukrainian agreement correction for *participants/children*
   whose numeric age range was generated as "11–18 рік". Original people,
   ages, all numbers, dates, names preserved. A prepublish blocker also
   catches old imported READY posts with the same defect.
5. Ephemeral per-model output-contract circuit: repeated exact reasoning-only
   failures (Ling/OpenRouter, GLM/Cloudflare) temporarily defer *only that*
   model for ten minutes; repeated local CPU timeouts defer local model for
   fifteen minutes. Other models and providers stay available; verified
   success clears the model's state. Operator routing, AI budgets,
   destination, global health counters, source media, delivery receipts,
   Telegram UNKNOWN protection and publication interval are unchanged.
   No additional AI model calls added.

## Verification
Unit regression on original bad/good LIVE examples and negative controls.
PR CI Ubuntu and Windows 3.11/3.12/3.13, native Portable/Defender.
**Do not claim LIVE accepted until operator installs v2.2.63 and telemetry
confirms zero copied calls to action, age agreement issues, and fewer
reasoning-only or local timeout retries.** v2.2.62 is being installed
independently while this release is built.
