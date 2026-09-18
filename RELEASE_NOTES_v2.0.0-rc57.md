# UA FREE Telegram Autopilot v2.0.0-rc57

RC57 is the full canonical synchronization release. It promotes the proven live RC54–RC56 operational fixes into GitHub while removing channel-specific dedupe hardcodes.

## Canonical synchronization

- Preserves RC54 rolling per-source scheduling, cooldown repair, monitoring topic balance, practical contact preservation and PRODANO editorial gate.
- Preserves RC55 schema-validated passive telemetry and Drive LIVE mirror hardening.
- Preserves RC56 durable published-event ledger, proper-name/fact matching, nearest-event trace and video-story extraction/linking.
- Makes GitHub, release artifacts, signed update overlay, live updater and Project Vault converge on one source line.

## Per-channel dedupe settings

Advanced duplicate behavior is now stored explicitly on each channel and editable in the **Дедуплікація** tab:

- profile: Standard / Scientific-News / Commercial-Editorial;
- Scientific-name fingerprint;
- compound subject + method + mechanism fingerprint;
- rare-term weighting;
- published-history window for the final pre-publication gate.

Existing production data is migrated once without reset:

- CTRL+UA -> Scientific / News, scientific names ON, compound events ON, rare terms ON, 720-hour published history;
- ПРОДАНО! -> Commercial / Editorial, 720-hour published history;
- other existing channels keep Standard behavior while retaining the live RC56 720-hour history window.

After migration, runtime behavior never derives dedupe semantics from a channel name or numeric channel ID.

## No story-specific production rules

Concrete examples such as `Leopardus tilcayo`, the Herculaneum scroll reports and the mouse-cortex study remain regression fixtures only. Production matching uses generic binomial-name, concept, rare-term, proper-name, action, quantity and duration evidence.

No database reset is introduced. Existing articles, publication history, feedback, credentials and updater state are preserved.

## Editorial runtime profile

- Added an explicit per-channel editorial runtime profile.
- Existing ПРОДАНО receives `Commercial / Editorial` once during compatibility migration.
- Commercial value gating, marketing-aware media handling and video diagnostics read the stored channel setting.
- Runtime no longer identifies ПРОДАНО by numeric channel ID or channel name.
