from __future__ import annotations

import json
from pathlib import Path

from telegram_autopilot.v2.domain import ChannelConfig, EditorialRuntimeProfile
from telegram_autopilot.v2.editorial import EditorialEngine, _editorial_thresholds
from telegram_autopilot.v2.event_dedupe_guard import _scientific_names
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.supervisor import SupervisorConfig, SupervisorService


def test_scientific_name_detector_requires_local_taxonomy_context() -> None:
    noisy = (
        "Researchers published a broad study about consumer behavior. "
        "The campaign called American Hope used a new format. "
        "Later Astra Model appeared in the product lineup."
    )
    assert "american hope" not in _scientific_names(noisy)
    assert "astra model" not in _scientific_names(noisy)

    real = "Researchers described a new species Varanus komodoensis in a taxonomic study."
    assert "varanus komodoensis" in _scientific_names(real)


def test_commercial_thresholds_are_channel_configuration() -> None:
    cfg = ChannelConfig(
        id=7, name="Any commercial channel", telegram_chat_id="@x",
        editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
        editorial_thresholds_json=json.dumps({
            "commercial_case_fit": 55,
            "commercial_case_score": 45,
            "commercial_transferability": 38,
            "commercial_anchor": 50,
        }),
    )
    thresholds = _editorial_thresholds(cfg)
    data = {
        "commercial_mechanism": 58, "consumer_behavior": 52, "creative_execution": 45,
        "measurable_result": 54, "strategic_transferability": 42, "why_now": 35,
    }
    allowed, lane, score = EditorialEngine._sold_value_allowed(data, 58, thresholds)
    assert allowed is True
    assert lane == "commercial_case"
    assert score >= 45


def test_rc59_storage_persists_channel_specific_runtime_controls(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "autopilot.sqlite3")
    with store.transaction() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,editorial_runtime_profile,created_at,updated_at)
               VALUES(1,'Generic','@generic',1,'editorial','commercial_editorial','x','x')"""
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,'x')")
        con.execute("DELETE FROM meta WHERE key='rc59_explicit_editorial_starvation_settings_v1'")
        con.commit()
    # Re-run schema compatibility exactly as first RC59 startup on an existing RC58 DB.
    store.initialize()
    cfg = store.get_channel(1)
    assert cfg is not None
    assert cfg.output_starvation_enabled is True
    assert cfg.output_starvation_window_hours == 4
    assert cfg.output_starvation_min_processed == 20
    thresholds = json.loads(cfg.editorial_thresholds_json)
    assert thresholds["commercial_case_score"] == 46
    assert "продано" not in cfg.editorial_thresholds_json.casefold()


def test_supervisor_output_starvation_is_config_driven(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "autopilot.sqlite3")
    service = SupervisorService(store, runtime=object(), logs_dir=tmp_path / "logs")
    snapshot = {
        "expected_running": True,
        "runtime_running": True,
        "runtime_started_at": "2026-09-19T06:00:00+00:00",
        "enabled_channels": {"7": "Generic"},
        "channels": {"7": {"alive": True, "collector_alive": True, "heartbeat_at": "2026-09-19T11:00:00+00:00"}},
        "queue": {"active": 0, "due": 0, "blockers": {}},
        "ai": {"healthy": 1, "total": 1},
        "database": {"ok": True},
        "disk": {"free_mb": 100000},
        "providers": [],
        "channel_stats": {
            "7": {
                "name": "Generic", "due_jobs": 0, "max_age_hours": 24, "ready": 0,
                "sources_total": 10, "recent_source_errors_15m": 0, "sources_cooling_down": 0, "slow_sources": [],
                "jobs_done_30m": 5, "published_30m": 0, "published_60m": 0,
                "output_starvation_enabled": True, "output_starvation_window_hours": 4,
                "output_starvation_min_processed": 20, "output_starvation_min_published": 1,
                "jobs_done_starvation_window": 30, "published_starvation_window": 0,
                "rejected_starvation_window": 18, "duplicates_starvation_window": 12,
                "publish_24h": True, "publish_start": "07:00", "publish_end": "00:00",
            }
        },
        "operational_states": {"7": {"state": "DEGRADED", "reasons": ["output starvation"], "output_starved": True}},
    }
    incidents = service.evaluate(snapshot, SupervisorConfig())
    assert any(x.code == "CHANNEL_OUTPUT_STARVATION_7" for x in incidents)


def test_runtime_has_no_channel_name_special_cases() -> None:
    for path in (
        Path("telegram_autopilot/v2/editorial.py"),
        Path("telegram_autopilot/v2/event_dedupe_guard.py"),
        Path("telegram_autopilot/v2/supervisor.py"),
    ):
        text = path.read_text(encoding="utf-8").casefold()
        assert "ctrl+ua" not in text
        assert "продано" not in text
