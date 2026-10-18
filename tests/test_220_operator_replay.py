"""Operator-derived editorial replay contracts, not a LIVE source acceptance."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.editorial import prepublish_quality_issues
from telegram_autopilot.v2.evidence_first import assess_monitoring_media, assess_monitoring_source


DATA = json.loads((Path(__file__).parent / "fixtures" / "monitoring_operator_replay_220.json").read_text(encoding="utf-8"))
CASES = DATA["cases"]


@pytest.mark.parametrize("case", CASES, ids=[x["id"] for x in CASES])
def test_operator_problem_is_still_blocked_at_real_prepublish_boundary(case):
    channel = ChannelConfig(
        id=3, name="ГРОМАДИ", telegram_chat_id="@test",
        mode=ChannelMode.MONITORING,
        policy=ChannelPolicy(monitoring_source_policy="connected_original"),
    )
    article = SimpleNamespace(
        id=64001, title=case["raw"][:170], raw_text=case["raw"],
        source_name="Місцеве джерело", source_url=f"https://t.me/{case['id']}",
        media_json=json.dumps(case["media"], ensure_ascii=False),
        article_layout_json=json.dumps(case["layout"], ensure_ascii=False),
    )
    issues = prepublish_quality_issues(channel, article, case["final"])
    assert case["expected"] in issues, (case["id"], issues)


@pytest.mark.parametrize("case", CASES, ids=[x["id"] for x in CASES])
def test_operator_case_decision_is_source_or_media_grounded(case):
    article = SimpleNamespace(
        title=case["raw"], raw_text=case["raw"],
        source_url=f"https://t.me/{case['id']}",
        media_json=json.dumps(case["media"]),
        article_layout_json=json.dumps(case["layout"]),
    )
    if case["kind"] == "source_video_unbound":
        result = assess_monitoring_media(article, final_text=case["final"])
    else:
        result = assess_monitoring_source(article, final_text=case["final"])
    assert case["expected"] in result.reasons
