from __future__ import annotations

import threading
import time
from datetime import datetime

from telegram_autopilot.models import CollectedArticle
from telegram_autopilot.v2.dedupe import _same_event
from telegram_autopilot.v2.production_runtime import ProductionIngestService


def _row(*, source_id: int, title: str, raw_text: str = "", source_name: str = "source", source_url: str = "") -> dict[str, object]:
    return {
        "source_id": source_id,
        "title": title,
        "raw_text": raw_text,
        "event_summary": "",
        "source_name": source_name,
        "source_url": source_url,
        "canonical_source_url": source_url,
        "content_hash": "",
    }


def test_waymo_cross_source_headline_expansion_is_duplicate() -> None:
    verge = _row(
        source_id=1,
        source_name="The Verge",
        source_url="https://www.theverge.com/transportation/994405/waymo-pulls-over-calls-cops-on-riders-with-a-ghost-gun",
        title="Waymo pulls over, calls cops on riders with a ghost gun",
    )
    toms = _row(
        source_id=2,
        source_name="Tom's Hardware",
        source_url="https://www.tomshardware.com/tech-industry/drones/waymo-robotaxi-calls-cops-on-riders-handling-loaded-ar-style-ghost-gun",
        title=(
            "Waymo robotaxi calls cops on riders handling loaded AR-style ghost gun - "
            "Waymo alerted San Francisco police then juvenile riders were stopped and arrested"
        ),
    )
    same, reason = _same_event(toms, verge)
    assert same is True
    assert "title" in reason


def test_same_brand_different_waymo_event_is_not_duplicate() -> None:
    first = _row(source_id=1, title="Waymo pulls over, calls cops on riders with a ghost gun")
    other = _row(source_id=2, title="Waymo launches new airport robotaxi service in Miami")
    same, _reason = _same_event(first, other)
    assert same is False


class _FakeStore:
    def __init__(self, count: int = 40) -> None:
        self.rows = [
            {
                "id": idx,
                "channel_id": 1,
                "kind": "page",
                "name": f"source-{idx}",
                "url": f"https://example.com/{idx}",
                "enabled": 1,
                "initialized": 1,
                "last_checked_at": "",
                "last_error": "",
                "priority": 100,
            }
            for idx in range(1, count + 1)
        ]

    def sources_for_channel(self, _channel_id: int, *, enabled_only: bool = True):
        return list(self.rows)

    def source_cooldown_active(self, _source_id: int):
        return False, ""


def test_production_ingest_does_not_queue_entire_channel_during_stop(monkeypatch) -> None:
    stop = threading.Event()
    calls: list[int] = []

    def slow_collect(source):
        calls.append(int(source.id))
        time.sleep(0.08)
        return [CollectedArticle(str(source.id), "title", source.url, "body", datetime.now().isoformat(), [])]

    monkeypatch.setattr("telegram_autopilot.v2.production_runtime.collect", slow_collect)
    store = _FakeStore(40)
    service = ProductionIngestService(store, cancel_requested=stop.is_set)

    timer = threading.Timer(0.02, stop.set)
    timer.start()
    started = time.monotonic()
    result = service.collect_channel(1)
    elapsed = time.monotonic() - started
    timer.cancel()

    assert result["cancelled"] == 1
    # Only the bounded live lane may have started. RC29 submitted all 40 at once.
    assert len(calls) <= 3
    assert elapsed < 1.0
