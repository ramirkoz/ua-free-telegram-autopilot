# Autopilot 2.1.10 — Cross-source incident dedupe

- Add a conservative, universal exception to strict same-headline matching: independent reports of the same incident may use different geographical scopes and headlines, but a duplicate requires at least two substantive shared named actors, an identical nontrivial numeric fact, a shared action category, and substantial matching source-body detail.
- Works through existing channel dedupe windows and enabled profile; no source, brand, event or channel names hardcoded. It does not turn shadow-only clusters into broad blocking.
- Regression scenarios include refrigeration sabotage described under different geographical scopes, unrelated business projects involving the same actors and numbers, and separate attacks with the same company names.
- Existing published Telegram posts are not deleted or replaced, and no old decisions are mass reprocessed. Media recovery and 2.1.9 actor/object checks stay unchanged.
- Technical CI/Windows release validation and live editorial QA are distinct. Keep 2.1.9 Portable available as rollback and preserve Data/credentials when updating manually.
