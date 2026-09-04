from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import telegram_autopilot.rc67_nonblocking_runtime as rc67


def channel(**overrides):
    base = dict(id=1, name="CTRL+UA", poll_immediate=True, poll_interval_minutes=1, max_posts_per_cycle=3)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_strong_candidate_filter_avoids_single_generic_keyword_but_keeps_real_overlap():
    assert not rc67._worth_ai({"keyword:model"})
    assert not rc67._worth_ai({"minor:ai models & agents"})
    assert rc67._worth_ai({"entity:nvidia"})
    assert rc67._worth_ai({"minor:xenotransplantation", "keyword:pig kidney"})
    assert rc67._worth_ai({"keyword:pig kidney", "keyword:kidney transplant"})


def test_pending_target_exposes_only_one_article_to_legacy_pipeline(monkeypatch):
    rows = [{"id": 3}, {"id": 2}, {"id": 1}]
    monkeypatch.setitem(rc67._PREV, "pending", lambda _db, _cid, _limit: rows)
    rc67._TARGET.article_id = 2
    try:
        assert [row["id"] for row in rc67._pending_target(object(), 1, 20)] == [2]
    finally:
        rc67._TARGET.article_id = None
    assert [row["id"] for row in rc67._pending_target(object(), 1, 2)] == [3, 2]


def test_run_channel_services_ready_before_slow_work(monkeypatch):
    events = []
    monkeypatch.setattr(rc67.rc66, "_publish_ready", lambda _service, _channel: events.append("ready"))
    monkeypatch.setattr(rc67, "_start_collect_if_due", lambda _service, _channel, *, force: events.append("collect"))
    monkeypatch.setattr(rc67, "_start_prepare_worker", lambda _service, _channel: events.append("prepare"))
    rc67._run_channel(SimpleNamespace(), channel(), force=False)
    assert events == ["ready", "collect", "prepare"]


def test_collection_is_started_in_background_and_does_not_block(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def slow_collect(_service, _channel, *, force=False):
        entered.set()
        release.wait(2)

    monkeypatch.setitem(rc67._PREV, "collect", slow_collect)
    service = SimpleNamespace(
        _last_collect={},
        _stop=threading.Event(),
        _audit=lambda *_a, **_k: None,
        _emit=lambda *_a, **_k: None,
    )
    start = time.monotonic()
    rc67._start_collect_if_due(service, channel(), force=False)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5
    assert entered.wait(1)
    worker = service._rc67_collect_workers[1]
    assert worker.is_alive()
    release.set()
    worker.join(2)
    assert not worker.is_alive()


def test_preparation_worker_uses_small_bounded_batch(monkeypatch):
    calls = []
    monkeypatch.setattr(rc67, "_prepare_one", lambda _service, _channel: calls.append(1) or True)
    service = SimpleNamespace(_stop=threading.Event())
    rc67._prepare_worker(service, channel(max_posts_per_cycle=10))
    assert len(calls) == 2


def test_process_does_not_run_legacy_synchronous_cluster_pass(monkeypatch):
    events = []
    monkeypatch.setattr(rc67.rc66, "_publish_ready", lambda _service, _channel: events.append("ready"))
    monkeypatch.setattr(rc67, "_start_prepare_worker", lambda _service, _channel: events.append("worker"))
    rc67._process(SimpleNamespace(), channel())
    assert events == ["ready", "worker"]
