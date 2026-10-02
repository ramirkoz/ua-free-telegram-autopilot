from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram_autopilot.v2.domain import EditorialRuntimeProfile
from telegram_autopilot.v2.editorial_review import EditorialReviewService
from telegram_autopilot.v2.operational_retention import (
    _apply_scientific_news_profile,
    _compact_operational_database,
)
from telegram_autopilot.v2.storage import V2Store, now_iso


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).astimezone().isoformat(timespec="seconds")


def _seed_science_channel(store: V2Store, channel_id: int = 1, *, profile: str = "scientific_news") -> None:
    now = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,channel_mode,editorial_runtime_profile,dedupe_profile,
                   dedupe_scientific_names,dedupe_compound_events,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                channel_id,
                "Any channel name",
                "@test",
                "editorial",
                str(EditorialRuntimeProfile.STANDARD),
                profile,
                1,
                1,
                now,
                now,
            ),
        )
        con.execute(
            """INSERT INTO channel_policies(
                   channel_id,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,
                   extra_instructions,selector_extra_prompt,writer_extra_prompt,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (channel_id, "Technology news", "Readers", "Base select", "Base reject", "Base write", "Base style", "", "", "", now),
        )
        con.execute(
            "INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(?,?,?,?,?,?,?)",
            (channel_id, channel_id, "rss", "Source", f"https://example.com/{channel_id}", 1, 50),
        )


def _article(store: V2Store, external_id: str, *, days_old: int, final_text: str = "Готовий текст") -> int:
    with store.connect() as con:
        cur = con.execute(
            """INSERT INTO articles(
                   channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,
                   discovered_at,stage,decision,blocked_by,final_text,media_json,article_layout_json
               ) VALUES(1,1,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                external_id,
                "Story",
                f"https://example.com/{external_id}",
                f"https://example.com/{external_id}",
                "Large raw payload " * 100,
                _iso_days_ago(days_old),
                "WRITTEN",
                "REJECT",
                "NONE",
                final_text,
                '["https://example.com/image.jpg"]',
                '{"blocks":[{"type":"media"}]}',
            ),
        )
        return int(cur.lastrowid)


def test_rc103_editorial_review_is_bounded_to_seven_days(tmp_path):
    store = V2Store(tmp_path / "db.sqlite3")
    _seed_science_channel(store)
    recent = _article(store, "recent", days_old=6)
    old = _article(store, "old", days_old=8)

    ids = {item.article_id for item in EditorialReviewService(store).candidates(limit=200)}
    assert recent in ids
    assert old not in ids


def test_rc103_startup_compaction_archives_old_work_and_prunes_jobs(tmp_path):
    store = V2Store(tmp_path / "db.sqlite3")
    _seed_science_channel(store)
    old = _article(store, "old", days_old=8)
    with store.connect() as con:
        con.execute(
            """INSERT INTO jobs(article_id,channel_id,job_type,state,priority,available_at,created_at,updated_at)
               VALUES(?,1,'process','WAITING',100,?,?,?)""",
            (old, now_iso(), now_iso(), now_iso()),
        )
        con.execute(
            "INSERT INTO audit_events(created_at,stream,event) VALUES(?,?,?)",
            (_iso_days_ago(8), "test", "old"),
        )

    stats = _compact_operational_database(store, retention_days=7, payload_days=30)
    row = store.get_article(old)
    assert row is not None
    assert row["stage"] == "ARCHIVED"
    assert row["raw_text"] == ""
    assert row["media_json"] == "[]"
    assert row["final_text"] == "Готовий текст"
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE article_id=?", (old,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM audit_events WHERE event='old'").fetchone()[0] == 0
    assert stats["retention_archived"] == 1
    assert stats["jobs_pruned"] >= 1
    assert stats["audit_pruned"] >= 1


def test_rc103_scientific_profile_is_role_based_and_visible_in_channel_settings(tmp_path):
    store = V2Store(tmp_path / "db.sqlite3")
    _seed_science_channel(store)
    now = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,channel_mode,editorial_runtime_profile,dedupe_profile,
                   dedupe_scientific_names,dedupe_compound_events,created_at,updated_at
               ) VALUES(2,'Other','@other','editorial','standard','standard',0,0,?,?)""",
            (now, now),
        )
        con.execute(
            "INSERT INTO channel_policies(channel_id,purpose,audience,updated_at) VALUES(2,'Other purpose','Other audience',?)",
            (now,),
        )

    applied = _apply_scientific_news_profile(store)
    assert applied == 1
    with store.connect() as con:
        science = con.execute(
            """SELECT c.min_publish_interval_minutes,c.publish_start,c.publish_end,c.max_posts_per_cycle,
                      c.published_dedupe_window_hours,c.dedupe_rare_terms,c.editorial_weights_json,
                      p.target_min_chars,p.target_max_chars,p.selection_rules,p.writer_extra_prompt
                 FROM channels c JOIN channel_policies p ON p.channel_id=c.id WHERE c.id=1"""
        ).fetchone()
        other = con.execute("SELECT min_publish_interval_minutes,publish_start,publish_end FROM channels WHERE id=2").fetchone()

    assert science[0:6] == (45, "08:00", "20:00", 2, 720, 1)
    weights = json.loads(science[6])
    assert weights[0]["name"] == "AI" and weights[0]["weight"] == 38
    assert science[7:9] == (450, 600)
    assert "[SCIENTIFIC_NEWS_RC103]" in science[9]
    assert "[SCIENTIFIC_NEWS_RC103]" in science[10]
    assert tuple(other) == (10, "07:00", "00:00")


def test_rc103_profile_marker_is_not_burned_when_role_absent(tmp_path):
    store = V2Store(tmp_path / "db.sqlite3")
    assert _apply_scientific_news_profile(store) == 0
    with store.connect() as con:
        assert con.execute("SELECT value FROM meta WHERE key='rc103_scientific_news_profile_v1'").fetchone() is None


def test_rc103_ui_queries_are_recent_bounded_and_do_not_load_full_article_blobs():
    source = (Path(__file__).resolve().parents[1] / "telegram_autopilot" / "v2" / "operational_retention.py").read_text(encoding="utf-8")
    assert "datetime(a.discovered_at)>=datetime('now','-7 days')" in source
    assert "LIMIT 250" in source
    assert "LIMIT 300" in source
    assert "candidates(limit=150)" in source
    assert "SELECT a.*" not in source


def test_rc103_scientific_mix_is_explicit_persisted_policy_not_channel_name_hardcode():
    source = (Path(__file__).resolve().parents[1] / "telegram_autopilot" / "v2" / "operational_retention.py").read_text(encoding="utf-8")
    for marker in ('"AI", "weight": 38', '"Robotics", "weight": 18', '"Medicine / Biology", "weight": 3'):
        assert marker in source
    assert "[SCIENTIFIC_NEWS_RC103]" in source
    assert "CTRL+UA" not in source
    assert "ПРОДАНО" not in source
