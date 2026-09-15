# UA FREE Telegram Autopilot v2.0.0-rc35

## Explicit per-channel source attribution

RC35 removes the RC34 runtime heuristic that inferred community behavior from an output channel name.

### What changed

- Added a visible per-channel setting: `Формат посилання на джерело`.
- `Стандартне — Джерело` keeps the existing generic `Джерело` / `Джерело N` footer.
- `Іменоване — Читати у «назва джерела»` uses the configured donor/source name and links it to the exact primary original post.
- Named-source mode also makes the configured source name mandatory rewrite context, so context is preserved outside the donor channel.
- Runtime behavior no longer checks whether a channel name contains `громад` or any other keyword.
- Future monitoring channels default to `standard`; they do not inherit community semantics.
- Existing RC34 databases receive a one-time compatibility migration: monitoring channels that previously matched the RC34 `громад` heuristic are stored as `named_source`. The compatibility match is Unicode-safe and runs only during migration. After that migration, the database setting is authoritative and editable in the channel UI.
- Actionable registration/form/payment/schedule URLs remain protected independently and stay in the post body.

### Compatibility

- No destructive database migration.
- Existing articles, sources, publication history, feedback and credentials are preserved.
- RC34 imports remain import-safe through a compatibility shim, but no name-based runtime detection remains.

### Operator check after update

Open the existing communities channel once and verify `Формат посилання на джерело = Іменоване`. New monitoring channels start with the standard source footer unless this setting is changed explicitly.
