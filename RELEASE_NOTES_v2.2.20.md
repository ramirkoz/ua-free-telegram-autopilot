# Autopilot v2.2.20 — targeted LIVE editorial quality repair

2026-10-22, branch candidate. Operator actual v2.2.19 remains installed until separate installation.

- CTRL+UA #74292 / Telegram #1469, published 15:32:41 Kyiv. Correct first draft contained "прогнозувати зриви"; trusted AI final-editor changed this to nonsensical "передзвіри зриви". Source: Scientific American article on plasma control at https://www.scientificamerican.com/article/new-superconducting-chip-aims-to-help-tame-fusion-plasma/. Add fail-closed high-confidence hard Ukrainian QA at writer stage **and** final READY prepublish gate; no unsafe automatic substitution.
- ГРОМАДИ #74332 / Telegram #3490, published 15:24:14 Kyiv. Original https://t.me/mih_gromada/4653 only defines "кібергігієна"; selector labelled [local_news] 100/100. Monitoring-only (explicit LIVE_NOW opt-in) source-owned glossary-card veto at selection and before Telegram send. Genuine municipal events, useful instructions, URLs, contacts and dated information survive.
- Exact operator examples and positive/negative regression cases: tests/test_2220_operator_editorial_quality.py. This is scoped to observed defects, not a universal hallucination detector.
- No changes to Data, channel/source settings, 5/30/45 minute publication cadence, photo collection, receipts (including protected UNKNOWN #66297), providers or OpenRouter limits.
- Candidate requires CI + native Windows build, official release, and later operator LIVE evidence before acceptance.
