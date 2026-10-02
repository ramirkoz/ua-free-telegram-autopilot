# Legacy V1/RC contract tests

RC101 classifies the following historical tests as **legacy-only** because they import top-level `telegram_autopilot.rc*` modules that are absent from the shipped V2 runtime. They are excluded from the active pytest collection instead of being counted as product regressions.

The contracts must be ported to V2 tests when the behavior is still relevant; the old files remain in the repository as historical evidence.

| Test | Missing historical modules |
|---|---|
| `test_rc33_policy.py` | `rc33_policy` |
| `test_rc35_source_compat.py` | `rc35_source_compat` |
| `test_rc36_media_human.py` | `rc33_policy, rc35_source_compat, rc36_policy` |
| `test_rc37_editorial.py` | `rc37_policy, rc37_style` |
| `test_rc38_editorial.py` | `rc38_policy` |
| `test_rc39_editorial_bridge.py` | `rc39_policy` |
| `test_rc40_pipeline.py` | `rc37_policy, rc38_policy, rc40_policy` |
| `test_rc41_editorial_mix.py` | `rc41_policy` |
| `test_rc42_channel_editorial_weights.py` | `rc42_policy` |
| `test_rc43_ui_layout.py` | `rc43_ui` |
| `test_rc44_direct_feed_transport.py` | `rc44_source_transport` |
| `test_rc45_cross_language_fact_guard.py` | `rc45_fact_guard, rc45_policy` |
| `test_rc45_editorial_direction.py` | `rc42_policy, rc45_policy` |
| `test_rc45_editorial_fit.py` | `rc45_editorial_fit, rc45_policy` |
| `test_rc46_editorial_throughput.py` | `rc42_policy, rc45_policy, rc46_policy, rc46_transport` |
| `test_rc47_editorial_quality.py` | `rc45_policy, rc47_policy` |
| `test_rc48_editorial_learning.py` | `rc48_learning` |
| `test_rc49_policy.py` | `rc48_learning, rc49_policy` |
| `test_rc49_router.py` | `rc49_router` |
| `test_rc51_reaction_feedback.py` | `rc51_feedback` |
| `test_rc52_dual_reaction_learning.py` | `rc51_feedback, rc52_feedback` |
| `test_rc53_production_hardening.py` | `rc53_hardening` |
| `test_rc54_mtproto_hotfix.py` | `rc48_learning, rc51_feedback, rc53_ui, rc54_mtproto` |
| `test_rc55_repeat_refresh.py` | `rc48_ui, rc51_ui, rc55_refresh` |
| `test_rc56_reaction_runtime.py` | `rc48_learning, rc48_ui, rc51_feedback, rc51_ui, rc54_mtproto, rc56_reaction_runtime` |
| `test_rc57_admin_audience_feedback.py` | `rc51_feedback, rc52_feedback, rc57_feedback_db, rc57_scoring, rc57_telegram_feedback, rc57_ui` |
| `test_rc58_editorial_rebuild.py` | `rc52_feedback, rc58_editorial_rebuild` |
| `test_rc59_universal_policy.py` | `rc52_feedback, rc59_universal_policy` |
| `test_rc60_editorial_quality.py` | `rc60_editorial_quality` |
| `test_rc61_runtime_fix.py` | `rc33_policy, rc53_hardening, rc61_runtime_fix` |
| `test_rc62_editorial_control.py` | `rc33_policy, rc53_hardening, rc61_runtime_fix, rc62_editorial_control` |
| `test_rc63_training_mode.py` | `rc62_editorial_control, rc63_training_mode` |
| `test_rc64_live_tuning.py` | `rc62_editorial_control, rc64_live_tuning` |
| `test_rc65_universal_final_editor.py` | `rc62_editorial_control, rc65_universal_final_editor` |
| `test_rc66_editorial_queue.py` | `rc66_editorial_queue, rc66_tags` |
| `test_rc67_nonblocking_runtime.py` | `rc67_nonblocking_runtime` |
| `test_rc68_editorial_value.py` | `rc59_universal_policy, rc68_editorial_value` |
| `test_rc69_media_language.py` | `rc45_policy, rc68_editorial_value, rc69_media_language` |
| `test_rc70_mixed_language.py` | `rc45_policy, rc69_media_language, rc70_mixed_language` |
| `test_rc71_editorial_pipeline.py` | `rc66_editorial_queue, rc68_editorial_value, rc71_editorial_pipeline` |
| `test_rc72_channel_policy.py` | `rc51_feedback, rc59_universal_policy, rc72_channel_policy_ui, rc72_monitoring_policy` |
| `test_rc73_channel_weights.py` | `rc73_channel_weights_ui` |
| `test_rc74_universal_runtime.py` | `rc45_policy, rc74_universal_runtime` |
| `test_rc75_channel_settings_ui.py` | `rc59_universal_policy, rc75_channel_settings_ui` |
| `test_rc76_editorial_weights_persistence.py` | `rc42_policy, rc45_policy, rc46_policy, rc51_feedback` |
| `test_rc79_runtime.py` | `rc59_universal_policy, rc79_runtime` |
| `test_rc80_dedupe_guard.py` | `rc80_runtime` |
| `test_rc81_resilience.py` | `rc81_runtime` |
| `test_rc82_stable_night.py` | `rc82_stable_runtime` |
