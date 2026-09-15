from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2.advanced_supervisor import AdvancedSupervisorService
from telegram_autopilot.v2.update_protocol import UpdateProtocol
from telegram_autopilot.v2 import updater_helper


def test_expected_running_never_builds_snapshot_on_caller_thread(tmp_path: Path) -> None:
    supervisor = object.__new__(AdvancedSupervisorService)
    import threading
    supervisor._lock = threading.RLock()
    supervisor._expected_running = False
    supervisor._poke = threading.Event()
    supervisor.write_snapshot = lambda: (_ for _ in ()).throw(AssertionError("must not run on Tk/caller thread"))
    AdvancedSupervisorService.set_expected_running(supervisor, True)
    assert supervisor._expected_running is True
    assert supervisor._poke.is_set()


def test_mirror_autodiscovery_prefers_existing_active_feed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AUTOPILOT_SUPERVISOR_MIRROR", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    empty = tmp_path / "My Drive" / "SUPERVISOR FEED — Autopilot V2"
    active = tmp_path / "Google Drive" / "My Drive" / "SUPERVISOR FEED — Autopilot V2"
    empty.mkdir(parents=True)
    active.mkdir(parents=True)
    (active / "status.json").write_text('{"version":"2.0.0-rc20"}', encoding="utf-8")
    (active / "agent_journal_since_review.json").write_text('{}', encoding="utf-8")
    found = AdvancedSupervisorService._discover_mirror_dir()
    assert Path(found) == active


def test_updater_prefers_drive_mirror_artifact(tmp_path: Path, monkeypatch) -> None:
    protocol = UpdateProtocol(tmp_path / "updates")
    request = protocol.validate_request({
        "request_id": "release-2-0-0-rc22",
        "target_version": "2.0.0-rc22",
        "sha256": "a" * 64,
        "source": "drive-release-manifest",
    })
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    payload = b"exact-update-overlay"
    (mirror / request.asset_name).write_bytes(payload)
    target = tmp_path / "work" / request.asset_name
    monkeypatch.setattr(updater_helper, "_configured_mirror_dir", lambda: mirror)
    monkeypatch.setattr(updater_helper, "_download", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("GitHub fallback must not be used")))
    source = updater_helper._obtain_archive(request, target)
    assert source == "drive-mirror"
    assert target.read_bytes() == payload


def test_remote_update_workflow_exports_manifest_and_agent_bundle() -> None:
    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "release-update-overlay.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "release_manifest.json" in text
    assert "approved_for_auto_update=$true" in text
    assert "windows_build_passed=$true" in text
    assert "REMOTE_UPDATE" in text
    assert "$env:UPDATE_MANIFEST" in text


def test_manifest_allows_github_fallback_and_rejects_bad_drive_hash(tmp_path: Path) -> None:
    import hashlib
    import json
    from telegram_autopilot.v2.advanced_update_coordinator import AdvancedUpdateCoordinator

    mirror = tmp_path / "mirror"
    mirror.mkdir()
    payload = b"overlay-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "version": "2.0.0-rc22",
        "artifact_filename": "UA_FREE_Telegram_Autopilot_v2.0.0-rc22_Update.zip",
        "sha256": digest,
        "request_id": "release-2-0-0-rc22",
        "approved_for_auto_update": True,
        "ci_passed": True,
        "windows_build_passed": True,
    }
    (mirror / "release_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    coordinator = object.__new__(AdvancedUpdateCoordinator)
    coordinator.supervisor = SimpleNamespace(config=SimpleNamespace(mirror_dir=str(mirror)))
    coordinator.protocol = UpdateProtocol(tmp_path / "updates")

    request = coordinator._manifest_request()
    assert request is not None
    assert request.target_version == "2.0.0-rc22"
    assert request.source == "drive-release-manifest-github-fallback"

    (mirror / manifest["artifact_filename"]).write_bytes(b"wrong")
    assert coordinator._manifest_request() is None

    (mirror / manifest["artifact_filename"]).write_bytes(payload)
    request = coordinator._manifest_request()
    assert request is not None
    # The already accepted request keeps its original provenance. The detached
    # SHA-aware helper still prefers the now-complete Drive ZIP at execution time.
    assert request.source == "drive-release-manifest-github-fallback"
