# Autopilot 2.0.7 — postfactum monitoring safety

- Monitoring security alerts (air raid alarms, blast reports, smoke, moving threats) are rejected **before AI** unless the source states a confirmed retrospective event; past timing alone is insufficient.
- Confirmed daily summaries of attacks are allowed without inventing damage/casualties.
- Short-source monitoring grounding catches unsupported new claims of attack causality, hostile drone origin and synthetic 'preliminary information' at the writing/editing/publishing gates.
- Live-observed Ukrainian calque «низькокачесні» blocked at language gate.
- Added deterministic regression tests derived from actual operator publications and confirmed recaps.
- Import, Data migration, credentials, channel settings, Content Tool and disabled Codex are unchanged.

**Scope disclaimer:** This is a safety-focused editorial release, not evidence that all long-form quality or duplicate clustering issues are resolved. Live operator review is required before unattended overnight use.

## Same-version 2.0.7 first-run hotfix

- Fix unwanted Codex runtime installation on normal first startup. Codex remains optional and operator-disabled by default. Explicit `UA_FREE_CODEX_BOOTSTRAP=1` opt-in is required to launch installer; no network download or startup delay without opt-in.
- Source Data, migrations, database, editorial filters, budgets and channel configuration unchanged.
- Same 2.0.7 version is republished with new portable SHA-256; old ZIP is superseded. Live acceptance still pending.
