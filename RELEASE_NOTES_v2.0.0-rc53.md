# UA FREE Telegram Autopilot v2.0.0-rc53

RC53 fixes the architectural mistake where advanced scientific dedupe behavior was embedded in the global runtime instead of being configured per output channel.

## Per-channel dedupe configuration

The channel settings now expose a dedicated **Дедуплікація** tab with:

- dedupe profile: Standard / Scientific-News;
- Scientific-name fingerprint;
- compound event fingerprint: subject + method + mechanism;
- rare-term weighting;
- published-history window for the final pre-publication duplicate check.

The runtime reads only these persisted channel settings. It does not infer behavior from the channel name.

## CTRL+UA compatibility migration

Existing Data is preserved. On first startup after upgrade, the existing CTRL+UA channel receives a one-time stored configuration:

- profile: Scientific / News;
- Scientific-name fingerprint: enabled;
- compound-event fingerprint: enabled;
- rare-term weighting: enabled;
- final PUBLISHED history: 720 hours / 30 days.

The CTRL+UA name is used only by this one-time migration to transfer existing behavior into explicit database settings. After migration, renaming the channel does not alter dedupe behavior.

Other channels remain on their own settings and do not inherit the CTRL+UA scientific rules.

## Generic engine, story-specific tests only

Concrete events are no longer production rules. Leopardus tilcayo, the Herculaneum-scroll case and the human-cortical-tissue mouse case exist only as regression fixtures.

The production engine provides generic capabilities:

- exact Latin binomial + discovery-context fingerprint;
- generic compound subject/method/mechanism fingerprint based on shared concepts, rare terms and optional numeric corroboration;
- channel-configured published-history depth.

No database reset or destructive migration is introduced.
