# UA FREE Telegram Autopilot 2.0.0-rc108

Roadmap release: ПРОДАНО! editorial throughput tuning + global non-blocking media policy.

## Product media rule
- Media is now opportunistic across the whole product: if valid source media exists, publish it; if not, publish text.
- Missing media can no longer block publication.
- Runtime normalizes every legacy media policy to `optional`.
- Existing channel-policy rows are migrated to `optional`.
- Existing READY/PUBLISH rows blocked only by MEDIA are released automatically.
- Existing media extraction, validation, normalization and multi-media Telegram publishing remain intact when media is available.
- Media diagnostics remain visible, but `MEDIA_REQUIRED` is no longer a publication gate.

## ПРОДАНО! throughput tuning
- Uses the existing `commercial_editorial` profile; there is no literal channel-name branch.
- RC108 slightly lowers broad-audience/creative lane thresholds based on RC106/RC107 reject telemetry.
- Routine B2B/PR, HR/personnel, dry partnerships and ordinary trade updates remain reject candidates.
- The selector is instructed not to categorically reject a story with a plausible broad human/consumer/culture/visual/surprise/retellable hook; such candidates proceed to the deterministic commercial value gate.
- Commercial profile thresholds remain ordinary persisted/editable channel configuration.

## Preserved RC107 contracts
- manual approvals remain operator-owned until PUBLISHED or explicit human reject;
- validated high-confidence cluster dedupe activation remains conservative;
- delivery journal remains crash-safe;
- signed updater safety contract remains unchanged.

## Live acceptance focus
1. telemetry reports `version=2.0.0-rc108`;
2. READY MEDIA blockers fall to zero after startup reconciliation;
3. previously approved MEDIA-blocked items are allowed to publish text-only;
4. media-bearing items still publish with their media normally;
5. ПРОДАНО! produces a materially healthier publish/processed ratio without obvious trade-noise regression;
6. delivery journal stays unresolved=0;
7. no regression in human-approved lifecycle or dedupe behavior.
