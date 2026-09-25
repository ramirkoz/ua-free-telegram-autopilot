# UA FREE Telegram Autopilot v2.0.0-rc89

## Fixes

- Restores missing AI/provider credentials after RC88 migration when the current Data contains a partial secrets set.
- Recovery is local and conservative: only validated sibling encrypted secret pairs are considered, and only currently empty secret fields are filled.
- Existing non-empty current credentials are never overwritten.
- Repairs RC88 databases that carried the old 5-minute polling value despite the earlier RC85 migration marker.
- Applies one explicit 15-minute polling repair pass; later operator edits are preserved.
- Retains RC88 V2 database carry-forward, RC86 per-source text-only cleanup and cross-source duplicate protection.

## Safety

- No secrets are embedded in the release.
- No Data directory is shipped in the update overlay.
- Credential recovery records only the source Data path and provider presence flags, never secret values.
