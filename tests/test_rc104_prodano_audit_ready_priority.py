from __future__ import annotations

from telegram_autopilot.v2.commercial_profile_audit import audit_commercial_profiles
from telegram_autopilot.v2.runtime_hardening import HardenedReadyStore
from telegram_autopilot.v2.storage import now_iso


def _seed_channel(store: HardenedReadyStore) -> int:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(
                   id,name,telegram_chat_id,channel_mode,editorial_runtime_profile,
                   created_at,updated_at
               ) VALUES(1,'ПРОДАНО!','@prodano','editorial','commercial_editorial',?,?)""",
            (stamp, stamp),
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,?)", (stamp,))
        cur = con.execute(
            "INSERT INTO sources(channel_id,kind,name,url,enabled,priority) VALUES(1,'page','src','https://example.com',1,100)"
        )
        return int(cur.lastrowid)


def test_rc104_human_approved_ready_has_priority(tmp_path) -> None:
    store = HardenedReadyStore(tmp_path / "rc104.sqlite3")
    source_id = _seed_channel(store)
    with store.connect() as con:
        con.execute(
            """INSERT INTO articles(
                   channel_id,source_id,external_id,title,source_url,canonical_source_url,
                   raw_text,content_hash,source_published_at,stage,decision,blocked_by,
                   status_detail,ready_at,final_text,discovered_at
               ) VALUES(1,?,'auto','AUTO','https://example.com/a','https://example.com/a',
                        'x','h1','2026-10-04T16:50:00+03:00','READY','PUBLISH','NONE',
                        'auto','2026-10-04T16:55:00+03:00','x','2026-10-04T16:50:00+03:00')""",
            (source_id,),
        )
        cur = con.execute(
            """INSERT INTO articles(
                   channel_id,source_id,external_id,title,source_url,canonical_source_url,
                   raw_text,content_hash,source_published_at,stage,decision,blocked_by,
                   status_detail,ready_at,final_text,discovered_at
               ) VALUES(1,?,'human','HUMAN','https://example.com/b','https://example.com/b',
                        'x','h2','2026-10-01T10:00:00+03:00','READY','PUBLISH','NONE',
                        'Погоджено редактором вручну','2026-10-04T16:00:00+03:00','x',
                        '2026-10-01T10:00:00+03:00')""",
            (source_id,),
        )
        human_id = int(cur.lastrowid)
        con.execute(
            """INSERT INTO editorial_actions(article_id,channel_id,action,title,before_text,after_text,detail,created_at)
               VALUES(?,1,'approve','HUMAN','x','x','','2026-10-04T16:00:00+03:00')""",
            (human_id,),
        )

    rows = store.ready_articles(1, limit=10)
    assert [str(row["title"]) for row in rows[:2]] == ["HUMAN", "AUTO"]


def test_rc104_commercial_profile_audit_is_non_mutating(tmp_path) -> None:
    store = HardenedReadyStore(tmp_path / "audit.sqlite3")
    _seed_channel(store)
    before = store.get_channel(1)
    result = audit_commercial_profiles(store)
    after = store.get_channel(1)

    assert result["mode"] == "non_mutating"
    assert result["channels"] == 1
    assert before == after
