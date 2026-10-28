"""2.2.48: recover only persisted false cooldowns from the 2.2.47 adapter crash."""
from __future__ import annotations

from types import SimpleNamespace
from telegram_autopilot.v2.storage import V2Store
from telegram_autopilot.v2.bounded_ingest import BoundedStrictIngestService

BUG = "_collect_current() got an unexpected keyword argument 'rss_enrich_eligible'"


def test_exact_commercial_cooldowns_recovered_once_and_other_channels_safe(tmp_path):
    store = V2Store(tmp_path / "live.sqlite3")
    with store.connect() as con:
        for cid, profile in ((1, "standard"), (2, "commercial_editorial"), (3, "standard")):
            con.execute(
                """INSERT INTO channels(id,name,telegram_chat_id,enabled,editorial_runtime_profile,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (cid, f"channel-{cid}", "@test", 1, profile,
                 "2026-10-28T12:00:00+02:00", "2026-10-28T12:00:00+02:00"),
            )
        for sid, cid, enabled in ((10, 1, 1), (20, 2, 1), (21, 2, 1), (22, 2, 0), (30, 3, 1)):
            con.execute(
                """INSERT INTO sources(id,channel_id,kind,name,url,enabled)
                   VALUES(?,?,'rss',?,?,?)""",
                (sid, cid, f"source-{sid}", f"https://example.org/{sid}", enabled),
            )
        for sid, error, outcome in (
            (10, BUG, "ERROR"), (20, BUG, "ERROR"),
            (21, "Remote source refused HTTP 403", "HTTP_403"),
            (22, BUG, "ERROR"), (30, BUG, "ERROR"),
        ):
            con.execute(
                """INSERT INTO source_health(
                      source_id,consecutive_failures,cooldown_until,last_outcome,
                      last_error,failure_count,success_count)
                   VALUES(?,4,'2099-01-01T00:00:00+00:00',?,?,9,5)""",
                (sid, outcome, error),
            )

    service = SimpleNamespace(store=store)
    repair = BoundedStrictIngestService._repair_v2247_commercial_keyword_cooldowns
    assert repair(service, 1) == 0
    assert repair(service, 2) == 1
    assert repair(service, 2) == 0
    assert repair(service, 3) == 0

    with store.connect() as con:
        recovered = con.execute("SELECT * FROM source_health WHERE source_id=20").fetchone()
        assert recovered["last_error"] == ""
        assert recovered["cooldown_until"] == ""
        assert recovered["consecutive_failures"] == 0
        assert recovered["last_outcome"] == "RECOVERED_248"
        assert recovered["failure_count"] == 9
        assert recovered["success_count"] == 5
        for sid in (10, 21, 22, 30):
            row = con.execute("SELECT * FROM source_health WHERE source_id=?", (sid,)).fetchone()
            assert row["cooldown_until"] == "2099-01-01T00:00:00+00:00"
            assert row["failure_count"] == 9
        assert con.execute("SELECT COUNT(*) FROM sources WHERE enabled=1").fetchone()[0] == 4
        assert con.execute("SELECT COUNT(*) FROM delivery_journal").fetchone()[0] == 0
