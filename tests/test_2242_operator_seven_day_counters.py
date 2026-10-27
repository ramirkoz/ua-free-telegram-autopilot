"""7-day operational publication counters never show prehistoric material."""
from datetime import datetime, timedelta, timezone

from telegram_autopilot.v2.storage import V2Store, now_iso
from telegram_autopilot.v2.supervisor import SupervisorService


def test_queue_and_channels_count_only_last_seven_days(tmp_path):
    store = V2Store(tmp_path / "v2.sqlite3")
    current = now_iso()
    with store.connect() as con:
        con.execute(
            """INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at)
               VALUES(1,'Science','@science','editorial',?,?)""",
            (current, current),
        )
        con.execute(
            """INSERT INTO sources(id,channel_id,kind,name,url)
               VALUES(1,1,'rss','test','https://example.org/rss')"""
        )
        for i, age in [(1, 9), (2, 1)]:
            date = (datetime.now(timezone.utc) - timedelta(days=age)).isoformat(timespec="seconds")
            con.execute(
                """INSERT INTO articles(
                       channel_id,source_id,external_id,title,source_url,
                       canonical_source_url,raw_text,source_published_at,discovered_at,
                       stage,decision,published_at,final_text
                   ) VALUES(1,1,?,?,?,?,'article',?,?,'PUBLISHED','PUBLISH',?,'copy')""",
                (str(i), str(i), f"https://example.org/{i}", f"https://example.org/{i}", date, date, date),
            )

    sup = SupervisorService(store, None, tmp_path / "logs")
    queue = sup._queue_snapshot()
    channels = sup._channel_stats()
    assert queue["published_total"] == 1
    assert channels["1"]["published_total"] == 1
    assert queue["last_publish"]
    assert queue["published_today"] in {0, 1}
