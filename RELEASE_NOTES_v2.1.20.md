# Autopilot v2.1.20 — Commercial media starvation terminal fix

- LIVE 2.1.19 telemetry confirmed channel «ПРОДАНО!» stuck with 6 READY rows and no new publications. TrendHunter article 57655 reached more than 160 attempts to recover `MEDIA_REQUIRED`, other similar blocked articles dozens of attempts. RSS re-ingest advertised raw gallery media but the final publication media policy rejected all candidates, leading to repeated wake/publish/reblock cycles.
- Publication now permanently archives failed `MEDIA_REQUIRED` / `MEDIA_INCOMPLETE` stories after the existing bounded recovery attempts, instead of leaving them READY and repeatedly reactivating on raw media candidates.
- Startup one-time migration archives legacy READY entries whose `article_layout_json.media_recovery` already declares `permanent` (or attempts above four), without changing valid READY entries.
- **No text-only fallback** is introduced for channels with `media_policy=required`. Unrelated valid READY stories remain eligible and can pass.
- Regression tests cover terminal skip, absence from READY, same-source reingest without reactivation, and migrated legacy data.
- This is an anti-starvation/anti-loop correction, **not** a claim to recover the original story photograph when the source offers no verifiable media. Media selection quality, slow source polling and CTRL+UA feedback category learning remain open.
- Install in a separate Windows Portable folder, migrate the backed-up Data folder from 2.1.19 and retain 2.1.19 for rollback. Confirm LIVE after installation.
