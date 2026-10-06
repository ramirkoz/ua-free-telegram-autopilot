# UA FREE Telegram Autopilot 2.0.0-rc107

Roadmap release: validated cluster dedupe activation plus updater/security cleanup.

## Human-approved lifecycle repair
- Manual approve/edit/publish-attempt is now treated as an operator-owned unpublished state until the article is actually PUBLISHED or the editor explicitly rejects it.
- READY expiry now protects the latest `publish_attempt` action in addition to approve/edit.
- READY publication priority is derived from durable `editorial_actions`, not fragile status text.
- Startup/media-recovery reconciliation restores manually approved rows that were automatically archived/rejected before publication.
- Unknown Telegram delivery remains blocked and is never blindly resurrected.
- Supervisor exposes: total unpublished human approvals, READY, MEDIA blocked, QUALITY blocked, unknown delivery and other blocked counts.

## Validated cluster dedupe activation
- RC106 shadow telemetry remains available.
- RC107 activates only the strongest cross-source cluster matches.
- Activation requires high shadow score plus substantial salient overlap and an independent strong anchor such as shared named entities + action, named entity + normalized fact, or scientific identity.
- Commercial profile uses the stricter threshold.
- Medium/low shadow candidates remain observation-only.
- Existing generic same-event mechanisms remain authoritative and concrete incidents are not hard-coded.

## Updater / security
- Auto-update manifests now support Ed25519 signatures over canonical manifest JSON.
- Unsigned or invalidly signed manifests are rejected before an update request is accepted.
- Auto-update starts only when a trusted update public key is configured.
- Without a trusted key the runtime stays safely update-disabled.
- Release overlay workflow now requires the `UPDATE_SIGNING_PRIVATE_KEY_PEM` GitHub secret and emits a signed manifest.
- SHA-256 artifact verification remains in addition to the manifest signature.

## Acceptance focus
1. manually approved historical rows are reconciled and remain visible until PUBLISHED or explicit human reject;
2. no approved row silently disappears after MEDIA_REQUIRED / publish_attempt;
3. only validated high-confidence cluster candidates hard-block as duplicate;
4. medium/low shadow candidates remain non-blocking;
5. unsigned manifests are rejected;
6. signed updater remains dormant when no trusted public key is configured.
