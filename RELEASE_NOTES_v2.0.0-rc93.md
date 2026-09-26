# UA FREE Telegram Autopilot v2.0.0-rc93

Live credential migration repair after RC92 Windows validation.

## Fixed

- Restores missing Gemini, NVIDIA, Groq, Cloudflare and other encrypted credentials from older sibling Autopilot builds around the migration source.
- Preserves every non-empty credential already present in the current build.
- Keeps Codex/runtime startup fixes from RC92 unchanged.
- Adds a regression for the real failure chain: newer selected RC with intact database/Codex state but missing fallback-provider keys, with valid credentials still present in an older sibling build.

## Validation

- Full regression suite passes on Ubuntu and Windows Python 3.11, 3.12 and 3.13.
- Windows migration, live supported-source collection and exact-post Telegram media gates pass on Python 3.12.

This release remains pending real Windows user acceptance before canonical Drive/ProductVault synchronization.
