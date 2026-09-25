from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from pathlib import Path

from telegram_autopilot.v2.migration_service import MigrationManager
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_store(path: Path) -> V2Store:
    store = V2Store(path)
    stamp = now_iso()
    with store.connect() as con:
        con.execute("""INSERT INTO channels(
            id,name,telegram_chat_id,enabled,channel_mode,editorial_profile,editorial_runtime_profile,
            include_source_link,source_link_required,source_attribution_mode,poll_interval_minutes,
            min_publish_interval_minutes,dedupe_window_hours,dedupe_profile,dedupe_scientific_names,
            dedupe_compound_events,dedupe_rare_terms,published_dedupe_window_hours,max_age_hours,max_posts_per_cycle,
            publish_24h,publish_start,publish_end,publish_immediately,topic_balance_enabled,topic_daily_limit,
            related_spacing_posts,editorial_weights_json,editorial_thresholds_json,facebook_page_ids_json,
            language_mode,media_enrichment_mode,media_first_allowed,media_min_text_chars,legacy_config_json,created_at,updated_at
        ) VALUES(1,'TEST','@test',1,'monitoring','profile','standard',1,1,'named_source',15,10,72,
            'standard',1,1,1,168,24,3,1,'00:00','23:59',1,1,2,5,'[]','{}','["123"]',
            'ukru_to_uk','auto',1,500,'{"custom":"keep"}',?,?)""",(stamp,stamp))
        con.execute("""INSERT INTO channel_policies(
            channel_id,enabled,purpose,audience,selection_rules,rejection_rules,writing_rules,style_rules,
            positive_examples,negative_examples,extra_instructions,selector_extra_prompt,writer_extra_prompt,
            source_body_attribution_mode,source_body_attribution_marker,media_policy,target_min_chars,target_max_chars,updated_at
        ) VALUES(1,1,'purpose','aud','sel','rej','write','style','','','','','',
            'source_name_marker','marker','required',300,750,?)""",(stamp,))
        con.execute("""INSERT INTO sources(
            id,channel_id,kind,name,url,enabled,initialized,priority,last_checked_at,last_error,legacy_config_json
        ) VALUES(1,1,'telegram','Source','https://t.me/source',1,1,100,'','','{"publication":{"strip_body_links":true}}')""")
        con.execute("""INSERT INTO articles(
            id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,content_hash,
            source_published_at,discovered_at,stage,decision,blocked_by,final_text,published_at,telegram_message_id
        ) VALUES(1,1,1,'x','Test','https://t.me/source/1','https://t.me/source/1','Raw','h',?,?,'PUBLISHED','PUBLISH','NONE','Final',?,'100')""",
            (stamp,stamp,stamp))
    return store


def test_readonly_legacy_import_preserves_source_and_settings(tmp_path: Path) -> None:
    legacy_dir = tmp_path / "legacy" / "Data"
    target_dir = tmp_path / "new" / "Data"
    legacy_dir.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    legacy_db = legacy_dir / "telegram_autopilot.sqlite3"
    target_db = target_dir / "telegram_autopilot.sqlite3"

    _seed_store(legacy_db)
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    os.chmod(legacy_db, stat.S_IREAD)
    try:
        V2Store(target_db)
        report, _, _ = MigrationManager(target_db).import_legacy_atomic(legacy_dir, import_credentials=False)
        after = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
        assert before == after
        assert report.channels_imported == 1
        assert report.sources_imported == 1
        assert report.articles_imported == 1

        with sqlite3.connect(target_db) as con:
            con.row_factory = sqlite3.Row
            channel = con.execute("SELECT * FROM channels WHERE id=1").fetchone()
            policy = con.execute("SELECT * FROM channel_policies WHERE channel_id=1").fetchone()
            source = con.execute("SELECT * FROM sources WHERE id=1").fetchone()
            assert channel["source_attribution_mode"] == "named_source"
            assert channel["dedupe_scientific_names"] == 1
            assert channel["facebook_page_ids_json"] == '["123"]'
            assert '"custom":"keep"' in channel["legacy_config_json"]
            assert policy["source_body_attribution_mode"] == "source_name_marker"
            assert policy["source_body_attribution_marker"] == "marker"
            assert '"strip_body_links":true' in source["legacy_config_json"]
    finally:
        os.chmod(legacy_db, stat.S_IWRITE | stat.S_IREAD)


def test_source_equals_target_uses_snapshot(tmp_path: Path) -> None:
    data_dir = tmp_path / "Data"
    data_dir.mkdir()
    db = data_dir / "telegram_autopilot.sqlite3"
    _seed_store(db)
    report, _, _ = MigrationManager(db).import_legacy_atomic(data_dir, import_credentials=False)
    assert report.channels_imported == 1
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 1
