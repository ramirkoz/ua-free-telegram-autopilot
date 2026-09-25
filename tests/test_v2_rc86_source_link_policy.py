from __future__ import annotations

import json
from pathlib import Path

from telegram_autopilot.v2.publisher import _strip_all_publication_links
from telegram_autopilot.v2.storage import V2Store, now_iso


def _store(tmp_path: Path) -> V2Store:
    store = V2Store(tmp_path / "rc86.sqlite3")
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at)
               VALUES(1,'TEST','@test','monitoring',?,?)""",
            (stamp, stamp),
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,?)", (stamp,))
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority,legacy_config_json)
               VALUES(1,1,'telegram','ЗаБор Запоріжжя','https://t.me/zaborzp',1,100,'{}')"""
        )
    return store


def test_strip_all_publication_links_removes_zabor_promos() -> None:
    text = (
        "Кіберполіція попереджає про шахрайські кол-центри.\n\n"
        "Детальніше: https://zabor.zp.ua/new/example\n\n"
        "Деталі/реєстрація: https://t.me/zabornews_bot\n\n"
        "[Корисна назва](https://example.test/page)"
    )
    cleaned = _strip_all_publication_links(text)
    assert "http://" not in cleaned
    assert "https://" not in cleaned
    assert "Детальніше" not in cleaned
    assert "Деталі/реєстрація" not in cleaned
    assert "Корисна назва" in cleaned


def test_source_policy_is_operator_editable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_source_suppress_publication_links(1, True)
    assert store.source_suppress_publication_links(1) is True
    store.set_source_suppress_publication_links(1, False)
    assert store.source_suppress_publication_links(1) is False


def test_rc86_seed_enables_existing_zabor_sources_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with store.connect() as con:
        con.execute("DELETE FROM meta WHERE key='rc86_source_link_policy_seed_v1'")
        store._ensure_rc86_source_link_policy(con)
        raw = con.execute("SELECT legacy_config_json FROM sources WHERE id=1").fetchone()[0]
    payload = json.loads(raw)
    assert payload["publication"]["suppress_links"] is True

    # Operator remains authoritative after the one-time seed.
    store.set_source_suppress_publication_links(1, False)
    with store.connect() as con:
        store._ensure_rc86_source_link_policy(con)
    assert store.source_suppress_publication_links(1) is False
