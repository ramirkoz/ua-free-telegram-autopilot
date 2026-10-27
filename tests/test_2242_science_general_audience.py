"""Scientific/News broad-reader fix: no microniche by numeric novelty alone."""
from __future__ import annotations

import json

from telegram_autopilot.v2.domain import (
    ChannelConfig, ChannelMode, DedupeProfile, EditorialRuntimeProfile,
)
from telegram_autopilot.v2.operational_retention import _apply_scientific_news_profile
from telegram_autopilot.v2.science_broad_audience_242 import (
    MARKER, OLD_MARKER, WEIGHTS, apply_science_general_audience_profile,
    broad_science_value_rejection, is_science_general_channel,
)
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed(store, cid: int, *, name: str, scientific: bool) -> None:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
              id,name,telegram_chat_id,channel_mode,editorial_runtime_profile,
              dedupe_profile,dedupe_scientific_names,dedupe_compound_events,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (cid,name,f"@test{cid}","editorial","standard",
             "scientific_news" if scientific else "standard",
             int(scientific),int(scientific),stamp,stamp),
        )
        con.execute(
            """INSERT INTO channel_policies(
               channel_id,selection_rules,rejection_rules,selector_extra_prompt,
               writer_extra_prompt,updated_at
               ) VALUES(?,?,?,?,?,?)""",
            (cid,"Operator selection","Operator exclusions","Operator selector",
             "Operator writer",stamp),
        )


def test_profile_removes_prior_geek_mix_and_keeps_operator_rules(tmp_path):
    store = V2Store(tmp_path / "profile.sqlite")
    _seed(store,7,name="Science role",scientific=True)
    _seed(store,2,name="CTRL+UA",scientific=False)
    assert _apply_scientific_news_profile(store) == 1
    with store.connect() as con:
        old=con.execute("SELECT selection_rules FROM channel_policies WHERE channel_id=7").fetchone()[0]
        assert OLD_MARKER in old
        existing=con.execute(
            "SELECT min_publish_interval_minutes,publish_start,publish_end FROM channels WHERE id=7"
        ).fetchone()
        untouched=tuple(con.execute(
            "SELECT selection_rules,rejection_rules FROM channel_policies WHERE channel_id=2"
        ).fetchone())

    assert apply_science_general_audience_profile(store)==1
    assert apply_science_general_audience_profile(store)==0
    with store.connect() as con:
        row=con.execute("""SELECT c.min_publish_interval_minutes,c.publish_start,c.publish_end,
                             c.editorial_weights_json,p.selection_rules,p.rejection_rules,
                             p.selector_extra_prompt,p.writer_extra_prompt
                             FROM channels c JOIN channel_policies p ON p.channel_id=c.id
                             WHERE c.id=7""").fetchone()
        unrelated=tuple(con.execute(
            "SELECT selection_rules,rejection_rules FROM channel_policies WHERE channel_id=2"
        ).fetchone())
    assert tuple(row[:3])==tuple(existing)
    assert json.loads(row[3])==WEIGHTS
    assert sum(x["weight"] for x in WEIGHTS)==100
    assert WEIGHTS[0]["name"]=="Science / Space"
    assert WEIGHTS[-1]["name"]=="Hardware" and WEIGHTS[-1]["weight"]<=5
    assert all(MARKER in row[i] and OLD_MARKER not in row[i] for i in (4,5,6,7))
    assert "Operator selection" in row[4] and "Operator exclusions" in row[5]
    assert "Operator selector" in row[6] and "Operator writer" in row[7]
    assert unrelated==untouched


def test_role_selection_not_name_or_channel_id():
    science=ChannelConfig(id=19,name="Any title",telegram_chat_id="@science",
                          mode=ChannelMode.EDITORIAL,dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
                          editorial_runtime_profile=EditorialRuntimeProfile.STANDARD,
                          dedupe_scientific_names=True,dedupe_compound_events=True)
    other=ChannelConfig(id=19,name="CTRL+UA",telegram_chat_id="@other",
                        mode=ChannelMode.EDITORIAL)
    marketing=ChannelConfig(id=2,name="ПРОДАНО!",telegram_chat_id="@sell",
                            mode=ChannelMode.EDITORIAL,
                            editorial_runtime_profile=EditorialRuntimeProfile.COMMERCIAL_EDITORIAL,
                            dedupe_profile=DedupeProfile.SCIENTIFIC_NEWS,
                            dedupe_scientific_names=True,dedupe_compound_events=True)
    assert is_science_general_channel(science)
    assert not is_science_general_channel(other)
    assert not is_science_general_channel(marketing)


def test_component_only_incremental_spec_is_rejected_even_with_high_mechanism():
    metrics=dict(novelty=78,mechanism=95,consequence_or_insight=20,
                 concrete_stakes=10,reader_payoff=34,retellability=22)
    assert broad_science_value_rejection(metrics).startswith("SCIENCE_AUDIENCE_REJECT")


def test_unproven_future_impact_not_accepted_as_general_news():
    metrics=dict(novelty=80,mechanism=95,consequence_or_insight=18,
                 concrete_stakes=15,reader_payoff=72,retellability=78)
    assert broad_science_value_rejection(metrics).startswith("SCIENCE_AUDIENCE_REJECT")


def test_foundational_scientific_discovery_accepted_without_immediate_product():
    metrics=dict(novelty=94,mechanism=65,consequence_or_insight=35,
                 concrete_stakes=20,reader_payoff=85,retellability=88)
    assert broad_science_value_rejection(metrics)==""


def test_big_medicine_energy_and_social_tech_consequences_accepted():
    for metrics in (
        dict(novelty=63,consequence_or_insight=91,concrete_stakes=81,reader_payoff=76,retellability=70),
        dict(novelty=70,consequence_or_insight=60,concrete_stakes=57,reader_payoff=72,retellability=71),
    ):
        assert broad_science_value_rejection(metrics)==""


def test_missing_model_metrics_fail_closed():
    assert broad_science_value_rejection({}).startswith("SCIENCE_AUDIENCE_REJECT")
