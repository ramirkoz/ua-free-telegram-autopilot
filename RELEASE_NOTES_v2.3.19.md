# UA FREE Telegram Autopilot 2.3.19

Operator-priority release based on v2.3.18 LIVE telemetry and the 08.11.2026 human editorial workbook (157 completed editor labels; 100 monitoring entries remain unreviewed).

## Fixed
- **OpenRouter-only while usable**: in `ai_mode=openrouter`, all purposes use OpenRouter models first and exclusively; a rejected model answer is retried within OpenRouter, not sent to free/direct models. A verified shared endpoint outage, auth/config failure or exhausted operator budget permits conservative emergency direct-provider fallback. Preserve $3/24 h, $20/month and per-task caps, no unsafe QA bypass.
- **Cloudflare standby**: migrate active/legacy Cloudflare slot off deprecated `@cf/nvidia/nemotron-3-120b-a12b` to `@cf/google/gemma-4-26b-a4b-it`. Do not assume a healthy Cloudflare account or expose backup while OpenRouter works. Keep direct NVIDIA independent.
- **Monitoring original-source gate**: suppress social lunch greetings posing as civic initiatives and specific off-region diplomacy/military-recruitment incidents with no local source link. Preserve local public services, regionally relevant reports and approved planned civic infrastructure.
- **CTRL+UA topical false positive**: reject the verified non-technical workplace holiday-advice source (#93640) instead of upgrading it to `role=science fit=100`; no general ban on authentic technology explainers.
- **Ukrainian final-copy fixes**: narrowly repair live attested case agreement and corrupt words; block the confirmed contradictory bulb/fixture statement pending source-faithful rewrite. Keep full Fact Guard and source-fact QA.

## Editorial learning and unresolved operations
- Human workbook dated 08.11 has **69 ☑ / 31 ☐ CTRL+UA** and **36 ☑ / 21 ☐ ПРОДАНО!**; ГРОМАДИ 100 blank pending human assessment. This file is training evidence, not an automatic publishing override or automatic release-wide training injection.
- Known false negatives (46 CTRL+UA, 22 ПРОДАНО!), source starvation (The Dieline HTTP403, Rest of World HTTP403), and partial commercial media remain tracked for safe subsequent calibration/recovery; **not** claimed solved by code-only rewrite.
- Keep 45/30/5-min intervals, Data, editorial provenance, original-source media parity, protected Telegram UNKNOWN=2 (#92213), and no automatic replay.

## Acceptance gates
- Ubuntu and Windows 3.11/3.12/3.13 full test suite.
- Windows portable/Defender, integrity and official release assets.
- Operator LIVE installation preserving Data, new natural posts, source-to-final-to-Telegram comparisons and proof that healthy OpenRouter makes *no* direct AI generation calls.
