from __future__ import annotations

from pathlib import Path

from telegram_autopilot.v2.ai_gateway import PRODUCTION_SLOTS, _rc109_route_slots
from telegram_autopilot.v2.provider_discovery import provider_discovery_snapshot
from telegram_autopilot.v2.storage import V2Store


def _models(purpose: str) -> list[str]:
    return [slot.model for slot in _rc109_route_slots(PRODUCTION_SLOTS, purpose)]


def test_rc109_writer_prefers_super_before_ultra() -> None:
    models=_models("writer")
    assert models.index("nvidia/nemotron-3-super-120b-a12b") < models.index("nvidia/nemotron-3-ultra-550b-a55b")
    assert models.index("gemini-3.5-flash") < models.index("nvidia/nemotron-3-ultra-550b-a55b")


def test_rc109_short_json_keeps_ultra_as_late_reserve() -> None:
    models=_models("editorial_selector")
    assert models[0] == "gemini-3.5-flash"
    assert models.index("qwen/qwen3.8-27b") < models.index("nvidia/nemotron-3-ultra-550b-a55b")
    assert models.index("nvidia/nemotron-3-super-120b-a12b") < models.index("nvidia/nemotron-3-ultra-550b-a55b")


def test_rc109_complex_task_can_escalate_to_ultra_after_super() -> None:
    models=_models("final_editor")
    assert models.index("nvidia/nemotron-3-super-120b-a12b") < models.index("nvidia/nemotron-3-ultra-550b-a55b")
    assert models.index("nvidia/nemotron-3-ultra-550b-a55b") < models.index("openai/gpt-oss-120b")


def test_rc109_provider_discovery_is_advisory_only() -> None:
    snap=provider_discovery_snapshot()
    assert snap["auto_enable"] is False
    assert snap["mode"] == "advisory_only"
    assert any(item["model"] == "Beam" for item in snap["candidates"])
    assert all(item["auto_enable"] is False for item in snap["candidates"])


def test_rc109_usage_summary_breaks_down_purpose(tmp_path: Path) -> None:
    store=V2Store(tmp_path/"usage.sqlite3")
    store.record_ai_usage(provider="nvidia",model="nvidia/nemotron-3-super-120b-a12b",purpose="writer",input_tokens=1000,output_tokens=100,total_tokens=1100,estimated_openrouter_usd=0.000125)
    store.record_ai_usage(provider="nvidia",model="nvidia/nemotron-3-ultra-550b-a55b",purpose="final_editor",input_tokens=1000,output_tokens=100,total_tokens=1100,estimated_openrouter_usd=0.00072)
    out=store.ai_usage_summary(24)
    assert out["calls"] == 2
    assert {x["purpose"] for x in out["by_purpose"]} == {"writer","final_editor"}
    assert out["ultra_reference_usd"] > 0
    assert out["ultra_reference_share"] > 0
    assert out["pricing_snapshot"].startswith("rc109-")
