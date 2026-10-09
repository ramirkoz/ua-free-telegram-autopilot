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
