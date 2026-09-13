# RC19 media contract

`EDITORIAL` is a single-media product mode. Storage trims unpublished editorial rows to exactly one media item and refuses to let later pipeline stages re-expand them.

`MONITORING` may keep multiple attachments, but Telegram ownership is strict: one `data-post` widget is one publication. Adjacent message IDs and timestamps are never evidence of album ownership.

Telegram collection is fail-closed. Only known content-media wrappers are accepted. Avatars, author/profile photos, link previews, reactions, reply thumbnails, video posters and unknown wrappers are discarded.

Pre-RC19 unpublished Telegram media snapshots are quarantined and refreshed before publication.

For web/RSS sources a fresh non-empty extraction replaces the previous unpublished media snapshot instead of accumulating stale URLs across polls.
