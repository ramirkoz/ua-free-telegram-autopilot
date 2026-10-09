# UA FREE Telegram Autopilot 2.0.6 — editorial language safety

## Scope
- Local LanguageTool no longer auto-applies word or named-entity substitutions, including MORFOLOGIK misspelling guesses. Punctuation-only corrections remain available.
- Writer and final-editor reject leaked formatting/control instructions using the existing validation/retry path.
- Fact Guard treats Latin FPV and Cyrillic ФПВ as equivalent in source evidence.
- Cyrillic uppercase entity mismatch tracking starts in shadow mode and does not block publication.
- Added regression tests for Ukrainian named entities, LanguageTool suggestions, prompt echo and FPV transliteration.

## Explicitly unchanged
- Source collection, media extraction, channel policy, publication routing, operator credentials and OpenRouter budgets.
- Codex operator-disabled setting; Content Tool.

## Acceptance status
Windows CI and portable build are engineering gates, not proof of editorial quality. Final acceptance requires live operator review against the 59-post RCA corpus.

## Same-version 2.0.6 emergency import hotfix (2026-10-09)

- Restores import of previous V2 Data when a read-only source SQLite database has WAL/shared-memory write restrictions: use a private writable SQLite+WAL snapshot for the retry, never modify the old Data.
- Displays explicit NOT READY status and opens Migration when no enabled channels are loaded instead of misleading operator with Ready / 0 workers.
- Keeps version 2.0.6 and preserves channel settings, database backup/rollback, credentials, operator-disabled Codex and Content Tool.
- Adds readonly-WAL and negative regression tests. The packaged update is not live-accepted until the operator confirms channel counts and publication runtime.
