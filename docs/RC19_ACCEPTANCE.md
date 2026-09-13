# RC19 acceptance

RC19 is accepted only if GitHub CI passes the full V2 regression suite on Ubuntu and Windows and the release workflow builds the portable Windows package.

Required behavior:

1. Editorial channels publish at most one media item.
2. Monitoring channels keep galleries only from the same Telegram post widget.
3. Avatars, author photos, link previews, reactions, video thumbnails and unknown Telegram wrappers are excluded.
4. Old pre-v3 Telegram media snapshots are not published without refresh.
5. Fresh web media replaces stale unpublished media snapshots.
6. Update requests accept only a target version and SHA-256; arbitrary shell commands and arbitrary URLs are ignored/rejected.
7. Update shutdown is graceful; SQLite is checkpointed and backed up before file replacement.
8. Startup health is required after update; failure triggers rollback.
