from __future__ import annotations

import json
from pathlib import Path

from telegram_autopilot.v2.domain import ChannelPolicy
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_channel(store: V2Store, channel_id: int = 2, profile: str = "commercial_editorial") -> None:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,editorial_runtime_profile,
               editorial_thresholds_json,created_at,updated_at)
               VALUES(?,?,?,1,'editorial',?,'{}',?,?)""",
            (channel_id, f"channel-{channel_id}", f"@channel{channel_id}", profile, stamp, stamp),
        )
        con.execute(
            """INSERT INTO channel_policies(channel_id,media_policy,selector_extra_prompt,updated_at)
               VALUES(?,'required','',?)""",
            (channel_id, stamp),
        )


def test_rc112_runtime_media_policy_honors_operator_configuration() -> None:
    assert ChannelPolicy(media_policy="required").normalized_media_policy() == "required"
    assert ChannelPolicy(media_policy="preferred").normalized_media_policy() == "preferred"
    assert ChannelPolicy(media_policy="optional").normalized_media_policy() == "optional"
    assert ChannelPolicy(media_policy="nonsense").normalized_media_policy() == "optional"


def test_rc108_migration_releases_ready_media_blockers_and_tunes_commercial(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "rc108.sqlite3")
    _seed_channel(store)
    stamp = now_iso()
    with store.connect() as con:
        source_id = int(con.execute(
            "INSERT INTO sources(channel_id,kind,name,url) VALUES(2,'page','S','https://example.com')"
        ).lastrowid)
        article_id = int(con.execute(
            """INSERT INTO articles(channel_id,source_id,external_id,title,source_url,canonical_source_url,
               raw_text,discovered_at,stage,decision,blocked_by,final_text,ready_at,last_error_code,last_error_detail)
               VALUES(2,?,'a','A','https://example.com/a','https://example.com/a','body',?,
                      'READY','PUBLISH','MEDIA','approved text',?,'MEDIA_REQUIRED','missing')""",
            (source_id, stamp, stamp),
        ).lastrowid)
        con.execute("DELETE FROM meta WHERE key='rc108_global_media_and_commercial_tuning_v1'")
        V2Store._ensure_rc108_global_media_and_commercial_tuning(con)

    row = store.get_article(article_id)
    assert row is not None
    assert str(row["blocked_by"]) == "NONE"
    assert str(row["last_error_code"]) == ""

    channel = store.get_channel(2)
    assert channel is not None
    assert channel.policy.media_policy == "optional"
    thresholds = json.loads(channel.editorial_thresholds_json)
    assert thresholds["broad_interest_fit"] == 45
    assert thresholds["broad_interest_score"] == 42
    assert thresholds["broad_general_interest"] == 46
    assert thresholds["broad_retellability"] == 46
    assert "[RC108_BROAD_THROUGHPUT]" in channel.policy.selector_extra_prompt


def test_rc108_tuning_is_idempotent(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "idempotent.sqlite3")
    _seed_channel(store)
    with store.connect() as con:
        con.execute("DELETE FROM meta WHERE key='rc108_global_media_and_commercial_tuning_v1'")
        V2Store._ensure_rc108_global_media_and_commercial_tuning(con)
        first = con.execute("SELECT selector_extra_prompt FROM channel_policies WHERE channel_id=2").fetchone()[0]
        V2Store._ensure_rc108_global_media_and_commercial_tuning(con)
        second = con.execute("SELECT selector_extra_prompt FROM channel_policies WHERE channel_id=2").fetchone()[0]
    assert first == second
    assert str(second).count("[RC108_BROAD_THROUGHPUT]") == 1
