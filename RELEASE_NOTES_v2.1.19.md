# Autopilot v2.1.19 — LIVE regression stabilization

Based on operator Data(9).zip and six Telegram screenshots. v2.1.18 did not pass operator LIVE acceptance.

- Source-grounded last-mile monitoring hard stop for bare current aircraft/munitions destination bulletins (#58894): no AI rewrite can override. Preserve confirmed retrospectively reported consequences.
- Publication hard gate rejects invented claims explicitly attributed to local witnesses when no such statement exists in source; other factual consistency checks remain unchanged.
- Added narrow final pre-Telegram check for short local injury/strike summaries appearing within 20 minutes of already committed incident reporting in the same operator monitoring channel. Intended to suppress #58853/#58855 after #58682; meaningful independently reported updates remain an edge case for LIVE validation.
- Improved final-stage visual duplicate detection for re-encoded or slightly color-shifted near-identical photo files (#54858), retaining distinct media and videos; checked against two regressions.
- Regression tests: `test_2119_operator_live_content_gates.py`, `test_2119_prepublish_incident_collision.py`, `test_2119_media_delivery_duplicates.py`.
- Does not reverse 2.1.18 newsroom policy: independent original reporting and official communities both eligible; unverified subscriber and anonymous eyewitness reports remain disallowed.
- Windows Portable installation: back up operator Data, install into a NEW folder, migrate Data only, keep old 2.1.18 rollback. Final operator acceptance requires LIVE verification of all screenshots' failure classes and unrelated legitimate reporting.
