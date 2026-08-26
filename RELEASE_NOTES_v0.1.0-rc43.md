# UA FREE Telegram Autopilot v0.1.0-rc43

RC43 is a focused UI correction for the per-channel editorial editor introduced in RC42.

## Fixed
- The channel editor now opens at a screen-aware size instead of assuming the old fixed 900x760 dialog is enough.
- On vertically constrained or scaled displays, the large editorial profile and weights list are reduced first so the bottom action row remains reachable.
- `Ctrl+S` now invokes the channel editor's **Зберегти** action as an explicit keyboard fallback.
- Saved editorial weights continue to persist through SQLite and reload when the channel editor is opened again.

## Preserved
- Per-channel editorial profiles and operator-defined category names/weights.
- No global CTRL+UA topic percentages.
- Empty weights mean no topic-balance gate.
- Existing RC42 Data remains compatible; no schema change.

## Upgrade
Unpack RC43 into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
