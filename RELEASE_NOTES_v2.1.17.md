# Autopilot v2.1.17: Telegram photo ownership repair

- Fix strict Telegram media parser: preserve genuine source photo when nested in photo/grouped-media wrapper below a persistent Telegram user/avatar wrapper, and when real photo wrapper is two or more elements above the media element.
- Keep actual channel avatars, reply/reaction icons and link-preview chrome excluded.
- Preserve consecutive separate text + photo album stitching; no changes to the existing adjacent-post policy.
- Adds regression tests inspired by LIVE Data(7).zip: article 56221 (osypenko_stg/4739), raw_candidates=8/discarded_non_content=8/media=0, with structural direct-photo and separated-media examples.
- The backup has no original Telegram HTML: this repair addresses demonstrable parser failure classes, not a claim of verified recovery of the exact historical post.
- Install to a separate Windows Portable folder, migrate Data from v2.1.16 with backup, retain rollback. LIVE acceptance required.
