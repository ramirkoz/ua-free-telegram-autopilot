# UA FREE Telegram Autopilot v0.1.0-rc50

## Main fixes
- Fixes the false LanguageTool unavailable/retry loop on Windows by using realistic local-server health timeouts.
- Restores media throughput for marketing channels such as ПРОДАНО! without weakening the anti-banner/affiliate/sponsor protections.
- Advertising, advertisement, campaign and promo vocabulary can describe the actual editorial subject in a marketing channel and is deferred to the channel-aware media policy instead of being discarded during extraction.
- Non-marketing channels keep the strict advertising/commercial media rejection path.
- Every channel remains media-only: no photo/video means no Telegram publication, and a rejected media upload does not downgrade to text-only.
- Media audit entries now expose raw/prepared candidate counts for diagnosis.

## Compatibility
Copy the complete existing `Data` directory into the new portable folder. Existing channels, sources, tokens, history and Editorial Memory are preserved.
