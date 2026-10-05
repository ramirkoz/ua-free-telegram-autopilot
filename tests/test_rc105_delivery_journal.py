from __future__ import annotations

from telegram_autopilot.v2.domain import BlockedBy, Decision, Stage
from telegram_autopilot.v2.editorial import _parse_json
from telegram_autopilot.v2.storage import V2Store, now_iso


def _seed_ready(store: V2Store) -> int:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,telegram_chat_id,created_at,updated_at) VALUES(1,'T','@t',?,?)",
            (stamp, stamp),
        )
        con.execute("INSERT INTO channel_policies(channel_id,updated_at) VALUES(1,?)", (stamp,))
        source_id = int(
            con.execute(
                "INSERT INTO sources(channel_id,kind,name,url) VALUES(1,'page','S','https://example.com')"
            ).lastrowid
        )
        article_id = int(
            con.execute(
                """INSERT INTO articles(
                       channel_id,source_id,external_id,title,source_url,canonical_source_url,
                       raw_text,discovered_at,stage,decision,blocked_by,final_text
                   ) VALUES(1,?,'x','x','https://example.com/a','https://example.com/a',
                            'x',?,'READY','PUBLISH','NONE','hello')""",
                (source_id, stamp),
            ).lastrowid
        )
    return article_id


def test_rc105_delivery_journal_commits_with_publication(tmp_path) -> None:
    store = V2Store(tmp_path / "rc105.sqlite3")
    article_id = _seed_ready(store)

    assert store.prepare_delivery(article_id, mode="text")["state"] == "PREPARED"
    assert store.mark_delivery_sending(article_id, mode="text")["state"] == "SENDING"

    store.acknowledge_delivery(
        article_id,
        message_id="101",
        message_ids=["101"],
        media_count=0,
        complete=True,
        mode="text",
    )
    assert store.delivery_journal(article_id)["state"] == "ACKNOWLEDGED"

    store.mark_published(article_id, message_id="101", message_ids=["101"])

    article = store.get_article(article_id)
    assert article is not None
    assert str(article["stage"]) == str(Stage.PUBLISHED)
    assert str(article["decision"]) == str(Decision.PUBLISH)
    assert str(article["blocked_by"]) == str(BlockedBy.NONE)
    journal = store.delivery_journal(article_id)
    assert journal["state"] == "COMMITTED"
    assert journal["primary_message_id"] == "101"
    assert store.delivery_journal_summary()["unresolved"] == 0


def test_rc105_unknown_outcome_is_durable(tmp_path) -> None:
    store = V2Store(tmp_path / "unknown.sqlite3")
    article_id = _seed_ready(store)
    store.mark_delivery_sending(article_id, mode="text")
    store.fail_delivery(article_id, "connection died after send", outcome_unknown=True)

    journal = store.delivery_journal(article_id)
    assert journal["state"] == "UNKNOWN"
    assert store.delivery_journal_summary()["unresolved"] == 1


def test_rc105_json_parser_repairs_common_structured_output_damage() -> None:
    assert _parse_json('''```json
{"a":1,}
```''')["a"] == 1
    assert _parse_json("prefix {'a': 2} suffix")["a"] == 2
    assert _parse_json('blah {"a":{"b":3}} trailing')["a"]["b"] == 3
