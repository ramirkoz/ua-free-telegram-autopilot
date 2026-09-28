# UA FREE Telegram Autopilot 2.0.0-rc100

RC100 promotes the editorial-review invariant requested during live review of the monitoring workflow and preserves all RC99 runtime hardening.

## Editorial review queue

- Every material that already has a non-empty final rewrite and has not actually been published remains visible in the editorial review queue.
- This applies to both editorial and monitoring channels.
- Automatic `REJECT`, `DUPLICATE`, `QUALITY`, `MEDIA`, `CONFIG` and `TELEGRAM` outcomes no longer hide an existing rewrite from the editor.
- The previous 72-hour visibility cutoff and stage/blocker whitelist are removed for rewritten, non-published material.
- An explicit manual editor rejection remains terminal so the queue can be intentionally cleared.
- Published material and items with no completed rewrite are excluded.

## Runtime baseline

RC100 includes the complete RC99 hardening line: safer Telegram delivery retry semantics, worker/watchdog freshness repair, background update discovery, updater safety gate, Tk callback fixes, provider contention handling, punctuation-safe body-link cleanup and the monitoring insufficient-context guard.

## Compatibility

- Existing V2 Data and channel settings are preserved.
- No channel name or channel ID is used as a hidden production rule.
- Existing dedupe, anti-slop, media, learning and publisher contracts remain in place unless explicitly described above.
