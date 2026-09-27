# UA FREE Telegram Autopilot V2 2.0.0-rc95

Windows validation build after the RC90-RC94 recovery failures.

## Runtime
- Keeps the 15-minute channel polling baseline.
- Preserves channel/source settings, editor queue, media stitching, dedupe, anti-slop, learning and publishing logic.
- Keeps per-source text-only cleanup and channel-configured source attribution.

## Credentials
- Removes automatic Desktop/Downloads/OneDrive/sibling-build credential discovery from normal startup.
- Imports one exact validated encrypted credential pair from the Data folder selected by the operator.
- Never combines secrets from several historical portable builds.

## AI
- Keeps provider-aware routing and fallback across configured providers.
- The manual AI test now reports how many routes were actually tested, healthy, failed or skipped instead of a generic completion message.

## Updates
- Auto-update can discover approved release manifests directly from GitHub Releases.
- Drive mirror remains a fallback/cache and is no longer required for release discovery.
- Existing SHA-aware detached update, backup, health check and rollback path remains in place.

This prerelease is for live Windows validation. Google Drive CURRENT and ProductVault canonical state are not advanced until live acceptance.
