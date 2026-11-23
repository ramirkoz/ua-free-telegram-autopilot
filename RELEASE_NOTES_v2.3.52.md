# Autopilot v2.3.52 — owner hard editorial rule: short regional posts are REJECTED

Status: candidate pending CI and native Windows Portable; not operator LIVE until install and telemetry.

## Incident

23.11.2026, operator v2.3.51, ЗАПОРІЖЖЯ | ГРОМАДИ article 111230 → Telegram #5715 at 14:40. Source ЗаБор Запоріжжя /160771 mixed a brief unconfirmed report of a body by the road with a note that traffic on Mariia Prymachenko Boulevard resumed. The published message contained only about **155 characters**. Owner explicitly prohibits short, low-information reports, rewriting an incomplete source, and inventing facts to lengthen it. Current channel policy target_min_chars=500 was silently weakened in `_monitoring_limits` as low as 20/85 characters for short source material.

## Remediation

- New `monitoring_short_material_2352.py`: for regional channel ID 3 / monitoring only, original source **minimum 500 meaningful text characters**, excluding links; **before AI** and **before actual Telegram send**. Retains stricter configured minimum if greater.
- Final generated text must independently contain **at least 500 meaningful characters**; otherwise `MONITORING_SHORT_FINAL_DROP_2352`; do **not** instruct model to artificially pad or invent to fill 500.
- Existing hard rejection for stale, rumor, lack of incident context, unsupported facts remains. The short-source ban is an additional fail-closed admission layer.
- Existing 2.3.51 specific blocks for #5712 orphan casualty, #5714 pinned-donor schedule remain.
- Regression tests include the REAL #5715 mixed-source example, old READY/prepublish, URL inflation, final 155-character rejection, independent channels, configurable longer minimum and lower UI-min cannot bypass hard owner minimum.
- No operator Data, publisher settings, Telegram receipts, 2 UNKNOWN, $3/day/$20/month budgets, or 30/30/5 changes.

## Explicit limitations

Minimum text length is a **necessary**, not sufficient, condition for factual source completeness. Long spam and weak evidence still depend on existing source-integrity/editorial QA. Event-centric dedupe winner/source claim provenance from 111135/111031 and false civic dedupe 111184/111035 remain open, **not** claimed fixed by this change.

Install via new official GitHub Windows Portable release only after main CI/Windows Defender pass; user must manually update. No automatic replay or duplicate Telegram sends.
