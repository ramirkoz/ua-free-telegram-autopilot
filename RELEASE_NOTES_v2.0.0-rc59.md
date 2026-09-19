# UA FREE Telegram Autopilot v2.0.0-rc59

RC59 repairs channel throughput without putting channel-specific behavior into the runtime engine.

- Scientific-name dedupe now requires nearby taxonomic context and no longer promotes ordinary title-case English phrases into fake species identifiers.
- Editorial thresholds are explicit per-channel JSON settings. Runtime code provides universal lanes only; channels own their thresholds.
- Existing Commercial / Editorial channels receive a one-time profile-derived balanced threshold seed stored in channel settings. No channel name or ID is used at runtime.
- Adds per-channel output-starvation settings: enabled, window hours, minimum processed jobs and minimum publications.
- Supervisor emits CHANNEL_OUTPUT_STARVATION_<id> when a channel is actively processing enough material during its configured publishing window but produces too little output.
- Publishing-window awareness prevents starvation alerts while a channel is outside its allowed schedule.
- RC58 UA Anti-Slop and BOM-safe signed updater are preserved.
