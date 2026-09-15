from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2.advanced_update_coordinator import AdvancedUpdateCoordinator
from telegram_autopilot.v2.safe_update_protocol import SafeUpdateProtocol
from telegram_autopilot.v2.safe_updater_helper import _safe_obtain_archive
from telegram_autopilot.v2.semantic_dedupe import SemanticDedupeEngine, semantic_same_event
from telegram_autopilot.v2.storage import V2Store, now_iso
from telegram_autopilot.v2.supervisor import SupervisorConfig
from telegram_autopilot.v2.telemetry_supervisor import TelemetryProductionSupervisorService
from telegram_autopilot.v2.update_protocol import UpdateRequest


def _row(source_id: int, title: str, raw_text: str, final_text: str = "") -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_name": f"source-{source_id}",
        "title": title,
        "raw_text": raw_text,
        "final_text": final_text,
        "event_summary": "",
        "source_url": f"https://example.test/{source_id}",
        "canonical_source_url": f"https://example.test/{source_id}",
        "content_hash": "",
    }


_COMMON_READING = (
    "reading pleasure memory empathy mental health brain structure cognitive reserve "
    "research review participants children adults attention language comprehension "
    "grey matter white matter connections ageing stress wellbeing sleep learning "
    "books fiction literacy development university researchers evidence analysis "
    "longitudinal surveys benefits cognition emotions communication vocabulary "
    "regular readers performance resilience social understanding exercise brain "
    "study results association mechanisms neural pathways education behaviour "
)


def test_same_study_cross_source_is_duplicate() -> None:
    first = _row(
        1,
        "Reading for pleasure improves memory empathy and mental health",
        _COMMON_READING + "first publisher adds a discussion of novels and long term habits",
    )
    second = _row(
        2,
        "All the ways reading for pleasure supports mental health",
        _COMMON_READING + "second publisher adds a discussion of screens and daily routines",
    )
    same, reason = semantic_same_event(second, first)
    assert same is True
    assert "event" in reason or "fingerprint" in reason


_COMMON_CASE = (
    "supreme court lawyer appeal murder conviction fabricated witnesses false testimony "
    "police evidence artificial intelligence filing contempt disciplinary board attorney "
    "failed verify facts legal citations client hearing judge court document generated "
    "chatbot hallucinated names statements record proceedings sanctions fine professional "
    "responsibility review brief counsel admitted using tool without checking output "
    "real people invented testimony investigation order decision state justices evidence "
    "accuracy verification legal duty submission case record defense proceedings "
)


def test_two_anchor_court_case_is_duplicate() -> None:
    first = _row(
        1,
        "Lawyer fined after fabricated witnesses appeared in murder appeal",
        _COMMON_CASE + "one outlet focuses on the fine and the appeal",
    )
    second = _row(
        2,
        "Chatbot using lawyer punished for fake testimony from witnesses",
        _COMMON_CASE + "another outlet focuses on discipline and verification",
    )
    same, reason = semantic_same_event(second, first)
    assert same is True
    assert "fingerprint" in reason or "event" in reason


def test_same_product_different_story_is_not_duplicate() -> None:
    review = _row(
        1,
        "Steam Frame headset review",
        "steam frame headset virtual reality display battery comfort tracking games review "
        "hardware performance lenses controllers graphics testing price ergonomics experience",
    )
    release = _row(
        2,
        "Valve bundles a classic game with Steam Frame",
        "steam frame headset virtual reality games valve bundle classic game arm port release "
        "software compatibility store launch package download owners",
    )
    same, _reason = semantic_same_event(release, review)
    assert same is False


def _insert_fixture(store: V2Store) -> tuple[int, int]:
    stamp = now_iso()
    with store.connect() as con:
        con.execute(
            "INSERT INTO channels(id,name,created_at,updated_at,dedupe_window_hours) VALUES(1,'CTRL+UA',?,?,72)",
            (stamp, stamp),
        )
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url) VALUES(1,1,'rss','one','https://one.test')")
        con.execute("INSERT INTO sources(id,channel_id,kind,name,url) VALUES(2,1,'rss','two','https://two.test')")
        cur = con.execute(
            """INSERT INTO articles(
                 channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,discovered_at,
                 stage,decision,final_text,published_at,telegram_message_id
               ) VALUES(1,1,'published','Reading for pleasure improves memory empathy and mental health',
                 'https://one.test/a','https://one.test/a',?,?,'PUBLISHED','PUBLISH','published copy',?,'790')""",
            (_COMMON_READING, stamp, stamp),
        )
        published_id = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO articles(
                 channel_id,source_id,external_id,title,source_url,canonical_source_url,raw_text,discovered_at,
                 stage,decision,final_text,ready_at
               ) VALUES(1,2,'ready','All the ways reading for pleasure supports mental health',
                 'https://two.test/b','https://two.test/b',?,?,'READY','PUBLISH','ready copy',?)""",
            (_COMMON_READING, stamp, stamp),
        )
        ready_id = int(cur.lastrowid)
    return published_id, ready_id


def test_prepublish_guard_marks_inherited_ready_duplicate(tmp_path: Path) -> None:
    store = V2Store(tmp_path / "autopilot.sqlite3")
    published_id, ready_id = _insert_fixture(store)
    result = SemanticDedupeEngine(store).prepublish(ready_id)
    assert result.relation == "DUPLICATE"
    assert result.duplicate_of == published_id
    row = store.get_article(ready_id)
    assert row is not None
    assert row["decision"] == "DUPLICATE"
    assert int(row["duplicate_of"]) == published_id


def _manifest(version: str, sha: str) -> dict[str, object]:
    return {
        "schema": "ua-free-autopilot-update-v1",
        "version": version,
        "artifact_filename": f"UA_FREE_Telegram_Autopilot_v{version}_Update.zip",
        "sha256": sha,
        "source_commit": "test",
        "created_at": "2026-09-15T06:00:00Z",
        "request_id": "release-2-0-0-rc32",
        "approved_for_auto_update": True,
        "ci_passed": True,
        "windows_build_passed": True,
    }


def test_manifest_can_request_github_fallback_without_drive_zip(tmp_path: Path) -> None:
    sha = "a" * 64
    (tmp_path / "release_manifest.json").write_text(json.dumps(_manifest("2.0.0-rc32", sha)), encoding="utf-8")
    coordinator = AdvancedUpdateCoordinator.__new__(AdvancedUpdateCoordinator)
    coordinator.supervisor = SimpleNamespace(
        config=SimpleNamespace(mirror_dir=str(tmp_path)),
        ensure_live_mirror=lambda force=False: str(tmp_path),
    )
    coordinator.protocol = SafeUpdateProtocol(root=tmp_path / "local")
    request = coordinator._manifest_request()
    assert request is not None
    assert request.target_version == "2.0.0-rc32"
    assert request.source == "drive-release-manifest-github-fallback"


def test_safe_updater_ignores_partial_drive_zip(monkeypatch, tmp_path: Path) -> None:
    good = b"validated update bytes"
    sha = hashlib.sha256(good).hexdigest()
    request = UpdateRequest("release-2-0-0-rc32", "2.0.0-rc32", sha, "2026-09-15T06:00:00Z")
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / request.asset_name).write_bytes(b"partial")
    target = tmp_path / "download" / request.asset_name

    from telegram_autopilot.v2 import updater_helper as base

    monkeypatch.setattr(base, "_configured_mirror_dir", lambda: mirror)

    def fake_download(_request, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(good)

    monkeypatch.setattr(base, "_download", fake_download)
    source = _safe_obtain_archive(request, target)
    assert source == "github-release"
    assert target.read_bytes() == good


def test_telemetry_force_rediscovery_repairs_stale_path(tmp_path: Path) -> None:
    old = tmp_path / "old"
    live = tmp_path / "live"
    old.mkdir()
    live.mkdir()
    (live / "status.json").write_text("{}", encoding="utf-8")

    service = TelemetryProductionSupervisorService.__new__(TelemetryProductionSupervisorService)
    service._lock = threading.RLock()
    service._config = SupervisorConfig(mirror_dir=str(old))
    service._telemetry_last_discovery_epoch = 0.0
    service._telemetry_last_discovery_error = ""
    service._telemetry_last_repair_at = ""
    service._telemetry_repair_count = 0
    service._discover_live_mirror_dir = lambda: str(live)
    service._discover_mirror_dir = lambda: ""

    def save_config(cfg):
        service._config = cfg
        return cfg

    service.save_config = save_config
    repaired = service.ensure_live_mirror(force=True)
    assert repaired == str(live)
    assert service.config.mirror_dir == str(live)
    assert service._telemetry_repair_count == 1
