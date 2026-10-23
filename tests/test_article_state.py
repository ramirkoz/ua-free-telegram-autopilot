"""Article lifecycle state machine: transition table, guards and MEDIA routing."""
import json

import pytest

from telegram_autopilot.v2 import article_state
from telegram_autopilot.v2.article_state import (
    MEDIA_ARCHIVE_PERMANENT, MEDIA_BACKOFF, MEDIA_RESTORE_223, MEDIA_UNBLOCK_NEW_ASSET,
    MEDIA_UNBLOCK_READY_BUNDLE, IllegalTransition, can_transition, plan, transition,
)
from telegram_autopilot.v2.domain import BlockedBy
from telegram_autopilot.v2.storage import V2Store


def _state(stage="READY", decision="PUBLISH", blocked_by="NONE", code=""):
    return {"stage": stage, "decision": decision, "blocked_by": blocked_by, "last_error_code": code}


def _store(tmp_path):
    store = V2Store(tmp_path / "db.sqlite")
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,channel_mode,created_at,updated_at) VALUES(1,'C','@c','editorial','now','now')")
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','S','https://example.test/feed')")
        con.execute(
            "INSERT INTO articles(id,channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,discovered_at) "
            "VALUES(1,1,1,'e1','T','https://example.test/a','https://example.test/a','body','now')"
        )
    return store


def _set(store, **fields):
    store.update_article(1, **fields)


def _row(store):
    return store.get_article(1)


# --- table and pure guards -------------------------------------------------

def test_every_transition_never_leaves_published():
    for name, spec in article_state.TRANSITIONS.items():
        assert "PUBLISHED" in spec.guard.exclude_stages, name
        assert not can_transition(_state(stage="PUBLISHED", blocked_by="MEDIA", code="MEDIA_REQUIRED_PERMANENT"), name)


@pytest.mark.parametrize("name,state,allowed", [
    (MEDIA_BACKOFF, _state(), True),
    (MEDIA_BACKOFF, _state(stage="QA_PASSED", decision="PENDING"), False),
    (MEDIA_UNBLOCK_NEW_ASSET, _state(stage="COLLECTED", decision="PENDING", blocked_by="MEDIA"), True),
    (MEDIA_UNBLOCK_NEW_ASSET, _state(blocked_by="TELEGRAM", code="TELEGRAM_429"), False),
    (MEDIA_UNBLOCK_READY_BUNDLE, _state(blocked_by="MEDIA", code="MEDIA_REQUIRED"), True),
    (MEDIA_UNBLOCK_READY_BUNDLE, _state(blocked_by="MEDIA", code="MONITORING_VIDEO_DELIVERY_INCOMPLETE"), False),
    (MEDIA_UNBLOCK_READY_BUNDLE, _state(blocked_by="QUALITY", code="MEDIA_REQUIRED"), False),
    (MEDIA_ARCHIVE_PERMANENT, _state(blocked_by="MEDIA", code="MEDIA_REQUIRED"), True),
    (MEDIA_ARCHIVE_PERMANENT, _state(stage="ARCHIVED", decision="REJECT"), False),
    (MEDIA_RESTORE_223, _state(stage="ARCHIVED", decision="REJECT", blocked_by="MEDIA", code="MEDIA_REQUIRED_PERMANENT"), True),
    (MEDIA_RESTORE_223, _state(stage="ARCHIVED", decision="REJECT", code="STALE_READY_MAX_AGE"), False),
])
def test_guards(name, state, allowed):
    assert can_transition(state, name) is allowed


def test_plan_rejects_unknown_codes_fields_and_names():
    with pytest.raises(IllegalTransition):
        plan("NOPE")
    with pytest.raises(IllegalTransition):
        plan(MEDIA_BACKOFF, error_code="TELEGRAM_429", detail="x", next_retry_at="")
    with pytest.raises(IllegalTransition):
        plan(MEDIA_UNBLOCK_NEW_ASSET, extra={"final_text": "x"})
    with pytest.raises(IllegalTransition):
        plan(MEDIA_UNBLOCK_NEW_ASSET, next_retry_at="2030-01-01T00:00:00+00:00")
    with pytest.raises(IllegalTransition):
        plan(MEDIA_ARCHIVE_PERMANENT, count_attempt=True)


def test_plan_assignments():
    backoff = plan(MEDIA_BACKOFF, error_code="MEDIA_REQUIRED", detail="d", next_retry_at="", count_attempt=True)
    assert backoff.assignments == {
        "blocked_by": "MEDIA", "last_error_code": "MEDIA_REQUIRED", "last_error_detail": "d", "next_retry_at": "",
    }
    assert backoff.retry_increment == 1
    unblock = plan(MEDIA_UNBLOCK_NEW_ASSET).assignments
    assert unblock == {"blocked_by": "NONE", "last_error_code": "", "last_error_detail": "", "next_retry_at": ""}
    archive = plan(MEDIA_ARCHIVE_PERMANENT).assignments
    assert archive["stage"] == "ARCHIVED" and archive["last_error_code"] == "MEDIA_REQUIRED_PERMANENT"
    assert "last_error_detail" not in archive  # None keeps the stored detail


# --- guarded writes --------------------------------------------------------

def test_transition_is_compare_and_set(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="READY", decision="PUBLISH", blocked_by="TELEGRAM", last_error_code="TELEGRAM_429", next_retry_at="x")
    with store.connect() as con:
        assert transition(con, 1, MEDIA_UNBLOCK_NEW_ASSET) is False
    row = _row(store)
    assert row["blocked_by"] == "TELEGRAM" and row["next_retry_at"] == "x"

    _set(store, blocked_by="MEDIA", last_error_code="MEDIA_REQUIRED")
    with store.connect() as con:
        assert transition(con, 1, MEDIA_UNBLOCK_NEW_ASSET) is True
    row = _row(store)
    assert (row["blocked_by"], row["last_error_code"], row["next_retry_at"]) == ("NONE", "", "")


def test_published_article_is_never_touched(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="PUBLISHED", decision="PUBLISH", blocked_by="NONE")
    store.publication_backoff(1, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_REQUIRED", detail="d", retry_seconds=600)
    store.archive_permanent_missing_media(1, detail="d")
    row = _row(store)
    assert (row["stage"], row["blocked_by"], row["last_error_code"]) == ("PUBLISHED", "NONE", "")


def test_media_backoff_via_store_counts_attempts(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="READY", decision="PUBLISH")
    retry_at = store.publication_backoff(1, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_DOWNLOAD_RETRY", detail="d", retry_seconds=600)
    row = _row(store)
    assert retry_at and row["next_retry_at"] == retry_at
    assert (row["blocked_by"], row["last_error_code"], int(row["retry_count"])) == ("MEDIA", "MEDIA_DOWNLOAD_RETRY", 1)
    store.publication_backoff(1, blocked_by=BlockedBy.MEDIA, error_code="MEDIA_REQUIRED", detail="d", retry_seconds=None, count_attempt=False)
    row = _row(store)
    assert row["next_retry_at"] == "" and int(row["retry_count"]) == 1


def test_non_media_backoff_is_unchanged(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="READY", decision="PUBLISH")
    store.publication_backoff(1, blocked_by=BlockedBy.TELEGRAM, error_code="TELEGRAM_429", detail="d", retry_seconds=60)
    row = _row(store)
    assert (row["blocked_by"], row["last_error_code"]) == ("TELEGRAM", "TELEGRAM_429")


def test_reingest_does_not_clear_a_non_media_blocker(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="READY", decision="PUBLISH", blocked_by="TELEGRAM", last_error_code="MEDIA_REQUIRED",
         media_json=json.dumps(["https://example.test/one.jpg"]))
    store.insert_collected(channel_id=1, source_id=1, external_id="e1", title="T", source_url="https://example.test/a",
                           raw_text="body", media_json=json.dumps(["https://example.test/two.jpg"]))
    assert _row(store)["blocked_by"] == "TELEGRAM"


def test_reingest_with_new_asset_clears_media_blocker(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="READY", decision="PUBLISH", blocked_by="MEDIA", last_error_code="MEDIA_REQUIRED",
         next_retry_at="2999-01-01T00:00:00+00:00", media_json=json.dumps(["https://example.test/one.jpg"]))
    store.insert_collected(channel_id=1, source_id=1, external_id="e1", title="T", source_url="https://example.test/a",
                           raw_text="body", media_json=json.dumps(["https://example.test/two.jpg"]))
    row = _row(store)
    assert (row["blocked_by"], row["last_error_code"], row["next_retry_at"]) == ("NONE", "", "")


def test_reingest_with_same_asset_keeps_media_backoff(tmp_path):
    store = _store(tmp_path)
    _set(store, stage="READY", decision="PUBLISH", blocked_by="MEDIA", last_error_code="MEDIA_REQUIRED",
         next_retry_at="2999-01-01T00:00:00+00:00", media_json=json.dumps(["https://example.test/one.jpg"]))
    store.insert_collected(channel_id=1, source_id=1, external_id="e1", title="T", source_url="https://example.test/a",
                           raw_text="body", media_json=json.dumps(["https://example.test/one.jpg"]))
    row = _row(store)
    assert (row["blocked_by"], row["next_retry_at"]) == ("MEDIA", "2999-01-01T00:00:00+00:00")


def test_media_writers_go_through_article_state():
    import inspect
    from telegram_autopilot.v2 import ready_backlog, storage
    for fn in (
        storage.V2Store.publication_backoff, storage.V2Store.archive_permanent_missing_media,
        storage.V2Store._ensure_v2120_archive_stale_permanent_media, storage.V2Store.insert_collected,
        ready_backlog.ReadyBacklogStore._recover_ready_media_blocker,
        ready_backlog.ReadyBacklogStore._restore_223_media_permanent_once,
    ):
        source = inspect.getsource(fn)
        assert "article_state.transition(" in source, fn.__qualname__
        assert "blocked_by=CASE" not in source, fn.__qualname__
