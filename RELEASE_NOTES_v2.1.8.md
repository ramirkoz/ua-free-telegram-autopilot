# Autopilot 2.1.8 — Source-owned media recovery

- A missing required-media bundle at the editorial publication gate triggers one bounded rehydration of the **same original source article page**, before applying the existing MEDIA_REQUIRED backoff. The rehydration uses the shared collector and existing editorial media classifier; it never uses unrelated external image search, nor invents a preview or relaxes a channel media policy.
- Reject cross-story page identity mismatch, invalid image URLs and candidates that do not pass the regular publication media filter. Preserve original final_text, article title, source URL, Telegram delivery metadata and media recovery history while importing only source-owned media evidence.
- Each individual channel retains its configured media_policy (required/preferred/optional); the mechanism applies universally to all editorial channels, without channel IDs or names in code.
- Regression coverage checks recovery, mismatched page rejection, and optional-media behavior.
- Limitations: A page that blocks requests, exposes no usable original media or requires authenticated JavaScript rendering can still fail closed with MEDIA_REQUIRED. This release does not guarantee resolution of the specific historical Fast Company records, nor fix source collection timeouts or AI throughput. No automatic replay of already archived or permanently rejected records.
- Windows Portable manual upgrade: preserve operator Data and credentials, retain 2.1.7 rollback. Live editorial/operational acceptance requires telemetry after installation.
