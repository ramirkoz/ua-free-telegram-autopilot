from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.media import encode_media
from telegram_autopilot.v2.domain import ChannelConfig, ChannelMode, ChannelPolicy
from telegram_autopilot.v2.hardened_storage import HardenedV2Store
from telegram_autopilot.v2.media_pipeline import build_media_bundle, build_publication_media_bundle
from telegram_autopilot.v2.runtime import RuntimeEngine
from telegram_autopilot.v2.supervisor import SupervisorConfig
from telegram_autopilot.v2.advanced_supervisor import AdvancedSupervisorService
from telegram_autopilot.v2.update_protocol import UpdateProtocol
from telegram_autopilot.v2.storage import now_iso


def _channel(mode: ChannelMode = ChannelMode.EDITORIAL) -> ChannelConfig:
    return ChannelConfig(
        id=1, name="x", telegram_chat_id="@x", enabled=True, mode=mode,
        policy=ChannelPolicy(channel_id=1, media_policy="preferred"),
    )


def _seed(store: HardenedV2Store, mode: str = "editorial") -> None:
    stamp = now_iso()
    with store.connect() as con:
        con.execute("INSERT INTO channels(id,name,telegram_chat_id,enabled,channel_mode,created_at,updated_at) VALUES(1,'x','@x',1,?,?,?)", (mode, stamp, stamp))
        con.execute("INSERT INTO channel_policies(channel_id,enabled,media_policy,updated_at) VALUES(1,1,'preferred',?)", (stamp,))
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url,enabled,priority) VALUES(1,1,'rss','s','https://s.example/feed',1,100)")


def test_editorial_publication_bundle_cannot_resurrect_two_representations(monkeypatch) -> None:
    import telegram_autopilot.media_pipeline as legacy

    chosen = SimpleNamespace(kind="image", url="https://cdn.example/relevant-hbm.jpg")
    monkeypatch.setattr(legacy, "prepare_article_media", lambda *a, **k: SimpleNamespace(telegram_hero=chosen))
    article = {
        "title": "SK hynix HBM4 memory",
        "raw_text": "HBM4 memory chips",
        "final_text": "",
        "media_json": json.dumps(["https://cdn.example/generic.jpg"]),
        "article_layout_json": json.dumps({
            "blocks": [{"type": "media", "kind": "image", "url": chosen.url, "context": "SK hynix HBM4"}]
        }),
    }
    raw = build_media_bundle(article)
    assert raw.count == 2
    final = build_publication_media_bundle(_channel(), article)
    assert final.count == 1
    assert final.items[0].url == chosen.url


def test_store_persists_same_single_editorial_item_in_both_representations(tmp_path: Path, monkeypatch) -> None:
    import telegram_autopilot.media_pipeline as legacy

    chosen = SimpleNamespace(kind="image", url="https://cdn.example/hero.jpg")
    monkeypatch.setattr(legacy, "prepare_article_media", lambda *a, **k: SimpleNamespace(telegram_hero=chosen))
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    _seed(store)
    aid = store.insert_collected(
        channel_id=1, source_id=1, external_id="a", title="story", source_url="https://s.example/a",
        raw_text="story body",
        media_json=json.dumps(["https://cdn.example/generic.jpg", chosen.url]),
        article_layout_json=json.dumps({"blocks": [{"type": "media", "kind": "image", "url": chosen.url}]}),
    )
    row = store.get_article(aid)
    assert json.loads(row["media_json"]) == [encode_media("image", chosen.url)]
    bundle = build_media_bundle(row)
    assert bundle.count == 1
    assert bundle.items[0].url == chosen.url


def test_monitoring_keeps_real_album() -> None:
    article = {
        "media_json": json.dumps([f"https://cdn.example/{i}.jpg" for i in range(4)]),
        "article_layout_json": json.dumps({"source_kind": "telegram", "telegram": {"media_count": 4, "media_filter_version": 3}}),
    }
    assert build_publication_media_bundle(_channel(ChannelMode.MONITORING), article).count == 4


def test_update_request_still_uses_fixed_repository(tmp_path: Path) -> None:
    protocol = UpdateProtocol(tmp_path / "updates")
    req = protocol.validate_request({
        "request_id": "manifest-rc21", "target_version": "2.0.0-rc21", "sha256": "a" * 64,
        "source": "drive-release-manifest",
    })
    assert req.release_url.startswith("https://github.com/ramirkoz/ua-free-telegram-autopilot/releases/download/")
    assert "evil.example" not in req.release_url


def test_supervisor_detects_stalled_tk_heartbeat(tmp_path: Path) -> None:
    store = HardenedV2Store(tmp_path / "v2.sqlite3")
    runtime = RuntimeEngine(store)
    runtime.ui_heartbeat_at = "2000-01-01T00:00:00+00:00"
    supervisor = AdvancedSupervisorService(store, runtime, tmp_path / "logs")
    supervisor._expected_running = True
    snapshot = supervisor.build_snapshot()
    # Satisfy the two-second incident persistence guard without sleeping.
    supervisor._first_seen["UI_STALLED"] = time.time() - 10
    codes = {x.code for x in supervisor.evaluate(snapshot, SupervisorConfig())}
    assert "UI_STALLED" in codes
