# Autopilot 2.2.23 — published-incident deduplication on the real SQLite schema

22 October 2026. Production defect in channel «ЗАПОРІЖЖЯ | ГРОМАДИ».

## Operator-proven incident
On 22 Oct the same fatal strike on a private residence in Zaporizhzhia, with two deaths and no material new facts, was posted twice within eleven minutes: operator article #75211 from the Zaporizhzhia regional administration at 18:17:33 and #75338 from local publisher «ЗаБор Запоріжжя» at 18:28:38. Confirmed by Telegram screenshot, outbound LIVE events and operator SQLite.

## Root cause and repair
Version 2.2.22 introduced a final-send casualty-event duplicate guard but queried a phantom table `published_event_ledger` created by its isolated test, not by the application. In the real application the lookup therefore failed rather than identifying the previously published article.

Version 2.2.23 queries real `articles` records with `stage='PUBLISHED'` and matches a confirmed `COMMITTED` delivery in `publication_delivery_journal` or `delivery_receipt_archive`. UNKNOWN, FAILED, READY and other channels are not publication evidence.

Keep existing narrow 20-minute same-city, same-fatality, same-residential-target checks, exclude separately named streets, changed death toll, and explicit material updates. The hard check runs in `publisher.py` before Telegram send, including older READY jobs.

## Verification
`tests/test_2222_published_casualty_dedupe.py` now uses product-style `articles` and delivery receipts, not a made-up published ledger. Covers OVA/newsroom paraphrase, original pair, different facts/site, elapsed-window threshold, quarantined UNKNOWN, archived COMMITTED, and READY.

No operator data, source settings, AI providers/budgets, schedule intervals, media files, previously published Telegram messages, or delivery receipts modified. The existing UNKNOWN #66297 remains quarantined. Operator LIVE acceptance requires manual installation and fresh outbound telemetry after full CI and official Windows release verification.
