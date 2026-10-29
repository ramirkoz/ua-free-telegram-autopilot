# Autopilot 2.2.51: deterministic final-edit regression guard

Based on 29 October three-post analysis of source, draft, final, and Autopilot 2.2.50 blueprint.

Changes:
- Adds source/draft/final explicit AI editorial contract: distinguish uncertainty from observed findings, qualified scientific claims, journalism vs brand positions, contributor vs film author, and unsupported detail.
- Adds bounded CPU-local DRAFT-to-FINAL comparison on aligned Ukrainian statements and named works, rejects high-confidence loss of 'може/могли/припускають/ймовірно' and promotion of 'працював над' to film author in trusted final editor.
- Adds independent high-precision hard Ukrainian case check for the real 'нашої власної планетні системи' pattern at writer and Telegram prepublish without changing facts automatically.
- No additional AI call or model substitution, no media/Telegram receipt modifications, no source priority/roster changes, no budgets/cadence/SQLite state changes. Same delivery ledger with 1 protected UNKNOWN remains fully preserved.
- Limit: lexical overlap across Ukrainian DRAFT→FINAL is NOT full semantic NLI, does not verify English source translations; this release cannot guarantee all roles, causality or nuances are caught. A/B editorial evaluation after operator installs, independently. Negative controls avoid cross-sentence or unrelated phrase false blocks.
