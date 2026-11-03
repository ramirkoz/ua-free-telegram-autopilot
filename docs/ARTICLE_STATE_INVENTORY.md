# Article state inventory (v2 runtime)

Scope: every place in `telegram_autopilot/v2/` that **writes** one of the article
state fields `stage`, `decision`, `blocked_by`, `last_error_code`, `next_retry_at`
(and the companions written with them: `last_error_detail`, `reject_reason`,
`status_detail`, `retry_count`, `ready_at`). Readers (UI, supervisor, agent feed,
`ready_articles`, `publication_guard`) are not listed. The legacy v1 runtime
(`telegram_autopilot/rc*.py`, `database.py`, `service.py`) is out of scope.

Notation: `S/D/B` = stage / decision / blocked_by, `code` = last_error_code,
`retry` = next_retry_at, `*` = any value, `—` = unchanged, `∅` = cleared to `''`.

Phase 1 (this change) routes the rows marked **[SM]** through
`telegram_autopilot/v2/article_state.py`. Everything else still writes the fields
directly and is the backlog for later phases.

## 1. Media blocker (MEDIA)

| # | Writer | From | To | Notes |
|---|---|---|---|---|
| M1 **[SM]** | `publisher.Publisher.publish_one` → `storage.publication_backoff(blocked_by=MEDIA)` (codes `MEDIA_REQUIRED`, `MEDIA_INCOMPLETE`, `MEDIA_DOWNLOAD_RETRY`, `MEDIA_DOWNLOAD_FAILED`, `MONITORING_VIDEO_DELIVERY_INCOMPLETE`, `LEGACY_MEDIA_PARTIAL`, `CAPTION_STATE_MISSING`, `MEDIA_*` from the media send loop) | READY/PUBLISH/* | READY/PUBLISH/MEDIA, code=reason, retry=now+N or ∅ (wait for source) | Transition `MEDIA_BACKOFF`. `retry_count` +1 when `count_attempt`. Recovery plan (`attempts`, `tried_assets`) lives in `article_layout_json.media_recovery`, written by `_media_recovery_plan`. |
| M2 **[SM]** | `storage.archive_permanent_missing_media` (called by publisher when `_media_recovery_plan` says `permanent`) | READY/PUBLISH/* | ARCHIVED/REJECT/MEDIA, code=`MEDIA_REQUIRED_PERMANENT`, retry ∅ | Transition `MEDIA_ARCHIVE_PERMANENT`. |
| M3 **[SM]** | `storage._ensure_v2120_archive_stale_permanent_media` (one-time init migration) | READY/PUBLISH/MEDIA, code ∈ {MEDIA_REQUIRED, MEDIA_INCOMPLETE}, layout says permanent or attempts>4 | ARCHIVED/REJECT/MEDIA, code=`MEDIA_REQUIRED_PERMANENT`, retry ∅ | Same transition as M2; keeps `last_error_detail`. |
| M4 **[SM]** | `storage.insert_collected` (re-poll of an existing non-PUBLISHED row) — SQL `CASE WHEN blocked_by='MEDIA' AND clear=1` | */*/MEDIA, stage≠PUBLISHED; `clear` when prior code is `TELEGRAM_MEDIA_REFRESH_REQUIRED` + clean snapshot, `TELEGRAM_VIDEO_PENDING` + recovered video, or `MEDIA_REQUIRED`/`MEDIA_MISSING_AFTER_INGEST`/`MEDIA_DOWNLOAD_FAILED`/`VIDEO_SOURCE_UNAVAILABLE` + genuinely new asset | —/—/NONE, code ∅, detail ∅, retry ∅ | Transition `MEDIA_UNBLOCK_NEW_ASSET`. Also requeues the WAITING job (job state is not part of this phase). |
| M5 **[SM]** | `ready_backlog.ReadyBacklogStore._recover_ready_media_blocker` (after `insert_collected` with fresh media, and from `runtime_hardening._resolve_ready_media_deadlocks`) | READY/PUBLISH/MEDIA, code ∈ {MEDIA_REQUIRED, MEDIA_INCOMPLETE, MEDIA_DOWNLOAD_FAILED, MEDIA_DOWNLOAD_RETRY}, complete bundle, offered assets ⊄ tried assets | READY/PUBLISH/NONE, code ∅, detail ∅, retry ∅, status_detail ∅ | Transition `MEDIA_UNBLOCK_READY_BUNDLE`. This is the writer that, before 2.2.3, reset M1's backoff (the 2.2.2 loop). |
| M6 **[SM]** | `ready_backlog._restore_223_media_permanent_once` (one-time startup repair) | ARCHIVED/REJECT/*, code=`MEDIA_REQUIRED_PERMANENT`, final_text≠'', ready_at within 48 h | READY/PUBLISH/MEDIA, code=`MEDIA_REQUIRED`, retry=now, reject_reason ∅ | Transition `MEDIA_RESTORE_223`. Resets `media_recovery` in layout. |
| M7 | `ready_backlog._recover_nonrequired_media_backlog` (startup, channels whose `media_policy`≠required) | READY/PUBLISH/MEDIA; PENDING/MEDIA; ARCHIVED/REJECT with media codes | →NONE (READY rows); →NONE + job requeued (PENDING); →READY/PUBLISH or COLLECTED/PENDING (archived) | Policy-driven release; three transitions in one function. Phase 2. |
| M8 | `media_recovery.MediaRecoveryStore.insert_collected` | */*/*, code=`MEDIA_REQUIRED_SKIPPED`, fresh bundle | READY/PUBLISH/NONE (has rewrite) or COLLECTED/PENDING/NONE | Revives monitoring skips. Phase 2. |
| M9 | `production_runtime._resolve_confirmed_media_misses` and `media_recovery.MediaRecoveryRuntimeEngine._resolve_confirmed_media_misses` (10-min grace variant overrides the first) | */PENDING/MEDIA, WAITING job, monitoring + required media, empty bundle | ARCHIVED/REJECT/NONE, code=`MEDIA_REQUIRED_SKIPPED` | Phase 2. |
| M10 | `runtime_hardening.HardenedRuntimeEngine._resolve_ready_media_deadlocks` | READY/PUBLISH/MEDIA, media codes, retry elapsed, ready_at older than 30 min | ARCHIVED/REJECT/NONE, code=`MEDIA_REQUIRED_EXPIRED` | Phase 2. Calls M5 first when the bundle is complete. |
| M11 | `runtime.RuntimeEngine._process_one` → `storage.defer_job(blocked_by=MEDIA)` (processing media gate, monitoring) | */PENDING/* | —/—/MEDIA, code=gate reason, retry=job available_at | Shares `defer_job` with AI/SOURCE/QUALITY deferrals. Phase 2. |
| M12 | `hardened_storage._sanitize_pre_rc19_telegram_media` (one-time) | non-published Telegram rows with old media filter | READY/PUBLISH or COLLECTED/PENDING, B=MEDIA, code=`TELEGRAM_MEDIA_REFRESH_REQUIRED` | Historical migration. |
| M13 | `storage._ensure_rc108_global_media_and_commercial_tuning`, `_ensure_rc109_clear_all_media_blockers`, `_recover_rc17_hotlink_failures` (one-time) | READY/PUBLISH/MEDIA (rc109: any non-published MEDIA) | →NONE, codes/retry cleared | Historical migrations. |

## 2. Publication / delivery blockers (TELEGRAM, CONFIG)

| # | Writer | From | To |
|---|---|---|---|
| P1 | `publisher` → `publication_backoff(TELEGRAM, …)`: `DELIVERY_OUTCOME_UNKNOWN`, `TELEGRAM_OUTCOME_UNKNOWN`, Telegram API failure codes, `PUBLISH_EXCEPTION` | READY/PUBLISH/* (`PUBLISH_EXCEPTION` is written after any exception in `publish_one`, without a stage check) | —/—/TELEGRAM, code, retry |
| P2 | `publisher` → `publication_backoff(CONFIG, "TELEGRAM_CONFIG")` | READY/PUBLISH/* | —/—/CONFIG, retry +300 s |
| P3 | `storage.mark_published` | READY/PUBLISH/* | PUBLISHED/PUBLISH/NONE, codes/retry cleared |
| P4 | `storage._reconcile_published_url_duplicates` (one-time), `publisher` → `mark_duplicate` | non-published | DEDUPED/DUPLICATE/NONE |

## 3. Processing pipeline (pre-READY)

| # | Writer | From | To |
|---|---|---|---|
| E1 | `storage.insert_collected` 2.0.10 cutover | new row | ARCHIVED/REJECT/NONE, code=`QUEUE_RESET_2010` |
| E2 | `runtime._process_one` → `update_article(stage=EXTRACTED)` | COLLECTED | EXTRACTED |
| E3 | `dedupe` / `semantic_dedupe` → `update_article(stage=DEDUPED)` or `_mark_duplicate`/`mark_duplicate` | EXTRACTED | DEDUPED/PENDING or DEDUPED/DUPLICATE |
| E4 | `editorial.EditorialPipeline` → `update_article(stage=SELECTED)`, `decision=REJECT`, `stage=QA_PASSED` then `mark_ready` | DEDUPED → SELECTED → QA_PASSED | READY/PUBLISH/NONE via `storage.mark_ready` (or `B=SOURCE`, `SOURCE_MISSING`) |
| E5 | `storage.defer_job` (AI/SOURCE/QUALITY/MEDIA), `storage.wake_blocked` (AI) | */PENDING/* | —/—/blocker, code, retry; wake → NONE |
| E6 | `storage.block_article` (publisher SOURCE/QUALITY guards) | READY/PUBLISH | QA_PASSED/PENDING/blocker, retry ∅ |
| E7 | `storage.requeue_quality_rewrite` (Telegram oversize) | READY/PUBLISH | QA_PASSED/PENDING/QUALITY, `retry_count`+1 |
| E8 | `storage.exhaust_quality_job` | */PENDING | READY/PUBLISH/QUALITY or ARCHIVED/REJECT/NONE |
| E9 | `storage.expire_stale_jobs` | */PENDING | ARCHIVED/REJECT, code=`STALE_MAX_AGE` |
| E10 | `storage.reject_editorial_article` | any | ARCHIVED/REJECT/QUALITY, code=`EDITORIAL_HARD_REJECT` |

## 4. READY backlog and retention

| # | Writer | From | To |
|---|---|---|---|
| R1 | `ready_backlog.expire_stale_ready` (startup + runtime cadence) | READY/PUBLISH, not human-approved, older than channel `max_age_hours` | ARCHIVED/REJECT/NONE, code=`STALE_READY_MAX_AGE` |
| R2 | `ready_backlog._reset_2010_queue_once` (one-time) | non-published without delivery evidence | ARCHIVED/REJECT/NONE, code=`QUEUE_RESET_2010` |
| R3 | `operational_retention._compact_operational_database` (installed onto the store by `install_operational_contracts`) | non-published older than 7 days | ARCHIVED/—/NONE, code=`RETENTION_7D` (keeps `TELEGRAM_OUTCOME_UNKNOWN`) |

## 5. Human editorial actions

| # | Writer | From | To |
|---|---|---|---|
| H1 | `editorial_review.EditorialReviewService.edit` / `approve` | any non-published, not UNKNOWN delivery | READY/PUBLISH/NONE, codes/retry cleared |
| H2 | `editorial_review.EditorialReviewService.reject` | any | ARCHIVED/REJECT/NONE |
| H3 | `storage.reconcile_human_approved_unpublished` | ARCHIVED or REJECT with latest action approve/edit | READY/PUBLISH, blocker kept if MEDIA/QUALITY/TELEGRAM/SOURCE/CONFIG |
| H4 | `runtime_contracts._enforce_terminal_human_rejects` | latest action reject | ARCHIVED/REJECT/NONE |

## 6. Import / migration

| # | Writer | From | To |
|---|---|---|---|
| I1 | `first_run_import._normalize_imported_active_state` | imported rows | ARCHIVED/REJECT, READY/PUBLISH, WRITTEN/PENDING or COLLECTED/PENDING, all NONE |
| I2 | `migration` (v1 → v2 copy) | legacy row | copied verbatim |

## Observations

- `storage.update_article` accepts any of the state fields, so every caller can
  perform any transition; there is no from-state check. Most of the writers above
  are compare-free `UPDATE … WHERE id=?`.
- The same logical transition has several writers with slightly different side
  effects: "unblock MEDIA" (M4, M5, M7, M13), "archive for missing media" (M2, M3,
  M9, M10), "back to READY" (M6, M8, H1, H3, I1).
- The 2.2.2 bug came from M5 clearing the `retry` written by M1 without checking
  that the offered assets were new. In 2.2.3 the asset check lives in M5 and M4;
  phase 1 additionally makes both go through one guarded transition so the
  blocker can only be cleared from `B=MEDIA` and never on a PUBLISHED row.
- `publisher._recover_missing_source_media` and `_media_recovery_plan` write only
  `media_json` / `article_layout_json` (media evidence and the recovery budget),
  not state fields; the resulting state change is M1 or M2.
- Phase 1 behaviour difference: the old MEDIA backoff `UPDATE` had no from-state
  check. `MEDIA_BACKOFF` requires READY/PUBLISH, so it can no longer mark a
  PUBLISHED article as MEDIA-blocked. The publisher only writes it after
  `publication_guard` has confirmed READY/PUBLISH, so live behaviour is the same.
  A refused transition is logged as `article transition refused` (app stream).
- `operational_retention`, `startup_background_hotfix` and the `*_contract`
  installers still assign methods onto classes at import time. They are not
  touched in phase 1.
