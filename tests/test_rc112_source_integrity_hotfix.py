from __future__ import annotations

from pathlib import Path

from telegram_autopilot.v2.commercial_profile_audit import audit_commercial_profiles
from telegram_autopilot.v2.storage import V2Store, now_iso


def _store(tmp_path: Path) -> V2Store:
    store = V2Store(tmp_path / "rc112-source-integrity.sqlite3")
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                 id,name,telegram_chat_id,enabled,channel_mode,editorial_runtime_profile,
                 media_first_allowed,media_min_text_chars,created_at,updated_at
               ) VALUES(1,'ПРОДАНО!','@test',1,'editorial','commercial_editorial',1,120,?,?)""",
            (stamp, stamp),
        )
        con.execute(
            """INSERT INTO channel_policies(channel_id,media_policy,updated_at)
               VALUES(1,'required',?)""",
            (stamp,),
        )
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority)
               VALUES(1,1,'rss','Shots','https://shots.net/',1,100)"""
        )
    return store


def test_rc112_reused_external_id_with_different_url_creates_distinct_article(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.insert_collected(
        channel_id=1,
        source_id=1,
        external_id="reused-guid",
        title="KFC launches Italian focaccia campaign",
        source_url="https://shots.net/news/view/kfc-focaccia-campaign",
        raw_text="KFC launched a focaccia campaign in Italy with Fabrizio Brienza.",
        content_hash="hash-kfc",
    )
    store.update_article(first, final_text="KFC запустив кампанію з італійською фокаччею.")
    store.mark_ready(first)

    second = store.insert_collected(
        channel_id=1,
        source_id=1,
        external_id="reused-guid",
        title="West Coast Awards reception",
        source_url="https://shots.net/news/view/amp-hosts-inaugural-west-coast-awards-reception",
        raw_text="The West Coast branch of AMP held its inaugural awards reception.",
        content_hash="hash-awards",
    )

    assert second != first
    row_first = store.get_article(first)
    row_second = store.get_article(second)
    assert row_first is not None and row_second is not None
    assert row_first["source_url"] == "https://shots.net/news/view/kfc-focaccia-campaign"
    assert row_first["canonical_source_url"] == "https://shots.net/news/view/kfc-focaccia-campaign"
    assert row_first["final_text"] == "KFC запустив кампанію з італійською фокаччею."
    assert row_second["source_url"] == "https://shots.net/news/view/amp-hosts-inaugural-west-coast-awards-reception"
    assert "::url::" in str(row_second["external_id"])


def test_rc112_ready_source_binding_blocks_late_source_mutation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    article_id = store.insert_collected(
        channel_id=1,
        source_id=1,
        external_id="guid-kfc",
        title="KFC campaign",
        source_url="https://shots.net/news/view/kfc-focaccia-campaign",
        raw_text="KFC campaign body",
        content_hash="hash-kfc",
    )
    store.update_article(article_id, final_text="Готовий текст про KFC.")
    store.mark_ready(article_id)
    assert store.publication_guard(article_id) == (True, "OK")

    store.update_article(
        article_id,
        source_url="https://shots.net/news/view/amp-hosts-inaugural-west-coast-awards-reception",
        canonical_source_url="https://shots.net/news/view/amp-hosts-inaugural-west-coast-awards-reception",
        content_hash="hash-awards",
    )
    assert store.publication_guard(article_id) == (False, "SOURCE_BINDING_MISMATCH")


def test_rc112_commercial_profile_audit_reports_required_as_effective(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = audit_commercial_profiles(store)
    assert report["channels"] == 1
    row = report["results"][0]
    assert row["configured_media_policy"] == "required"
    assert row["media_policy"] == "required"
