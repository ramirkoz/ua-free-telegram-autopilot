# UA FREE Telegram Autopilot v2.0.0-rc28

## Telegram media recovery / monitoring hotfix

- Fixes the RC27 `ЗАПОРІЖЖЯ | ГРОМАДИ` media starvation where valid Telegram post photos could be discarded because current public `t.me/s` direct-media wrappers appeared under `link_preview` / `webpage` ancestors.
- Direct Telegram photo/video/grouped-media wrappers now override only the soft preview rejection. Avatars, reactions, replies, logos, promo chrome and video thumbnails remain rejected.
- Required-media monitoring items now receive a 10-minute source-refresh grace window instead of being permanently archived seconds after the first incomplete media snapshot.
- If an exact Telegram post was previously archived as `MEDIA_REQUIRED_SKIPPED` and a later source poll discovers valid source media, the same article/job is revived and re-queued automatically. No duplicate article is created.
- Supervisor now exposes `MEDIA_STARVATION_<channel>` and marks the operational channel DEGRADED when Telegram candidates are being seen but `content_media=0` and publications remain at zero.
- Required-media policy stays enabled. RC28 fixes extraction/recovery; it does not permit text-only monitoring posts.

## Regression coverage

- Direct media inside current-style soft preview/webpage wrappers is preserved while preview/avatar chrome remains rejected.
- Archived media misses revive when a later exact-post refresh gets valid media.
- Required-media sweeper respects the refresh grace window.
- Supervisor detects the RC27-style 835-candidates / 0-content-media starvation pattern.
