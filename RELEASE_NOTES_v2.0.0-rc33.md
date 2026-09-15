# UA FREE Telegram Autopilot v2.0.0-rc33

## Fixed

- Preserve hidden Telegram message-text hyperlinks during strict `t.me/s` ingest. A source fragment such as `за <a href="https://…">посиланням</a>` now keeps the exact target URL in the source evidence instead of degrading to the bare word `посиланням`.
- Protect operational/actionable URLs during AI rewrite and final edit. Registration, application, form, ticket, booking, payment, schedule, deadline and similar reader-action links are validated as protected facts.
- A generic `Джерело` footer no longer counts as a replacement for a distinct registration/application URL. If the writer drops the practical target, QA rejects that rewrite and retries/falls back instead of publishing a post that forces the reader to hunt through the source.
- Non-actionable links remain optional so ordinary news posts do not become link dumps.

## Regression coverage

- Hidden registration `href` survives `StrictTelegramParser` and reaches `raw_text`.
- Actionable URL is accepted when preserved and rejected when removed.
- Canonical Telegram source URL cannot substitute for a different operational URL.
- Generic non-actionable links are not forced into the rewritten body.

## Preserved from rc32

- Pre-publication semantic/event dedupe and startup READY reconciliation.
- LIVE telemetry repair/rediscovery.
- Manifest/SHA-authoritative remote update transport with GitHub release fallback.
- Existing `Data`, SQLite database, credentials, channel configuration and local AI runtime remain compatible.
