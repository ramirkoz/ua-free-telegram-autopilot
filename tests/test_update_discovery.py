from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import telegram_autopilot.v2.advanced_update_coordinator as updater


class _Protocol:
    def __init__(self, root: Path):
        self.request_path = root / "request.json"
        self.written = None

    def validate_request(self, data):
        return SimpleNamespace(
            request_id=data["request_id"],
            target_version=data["target_version"],
            sha256=data["sha256"],
            created_at=data["created_at"],
            source=data["source"],
        )

    def request_is_newer(self, request):
        return request.target_version == "2.0.0-rc95"

    def request_already_terminal(self, request):
        return False

    def load_request(self):
        return None

    def _atomic_json(self, path, payload):
        self.written = payload

    def write_state(self, *args, **kwargs):
        return None


def _coordinator(tmp_path: Path):
    value = object.__new__(updater.AdvancedUpdateCoordinator)
    value.protocol = _Protocol(tmp_path)
    return value


def test_github_release_manifest_is_discovered_without_drive(tmp_path: Path, monkeypatch) -> None:
    releases = [{
        "draft": False,
        "assets": [{
            "name": "release_manifest.json",
            "browser_download_url": "https://example.invalid/release_manifest.json",
        }],
    }]
    manifest = {
        "version": "2.0.0-rc95",
        "approved_for_auto_update": True,
        "ci_passed": True,
        "windows_build_passed": True,
        "artifact_filename": "UA_FREE_Telegram_Autopilot_v2.0.0-rc95_Update.zip",
        "sha256": "a" * 64,
        "request_id": "manifest-2-0-0-rc95",
        "created_at": "2026-09-27T00:00:00+03:00",
    }

    def fake_read(url, *, timeout=12):
        del timeout
        return releases if url == updater._RELEASES_URL else manifest

    monkeypatch.setattr(updater, "_read_json_url", fake_read)
    coordinator = _coordinator(tmp_path)

    request = coordinator._github_manifest_request()

    assert request is not None
    assert request.target_version == "2.0.0-rc95"
    assert request.source == "github-release-manifest"
    assert coordinator.protocol.written["target_version"] == "2.0.0-rc95"


def test_unapproved_manifest_is_ignored(tmp_path: Path, monkeypatch) -> None:
    releases = [{
        "draft": False,
        "assets": [{
            "name": "release_manifest.json",
            "browser_download_url": "https://example.invalid/release_manifest.json",
        }],
    }]
    manifest = {
        "version": "2.0.0-rc95",
        "approved_for_auto_update": False,
        "ci_passed": True,
        "windows_build_passed": True,
        "artifact_filename": "UA_FREE_Telegram_Autopilot_v2.0.0-rc95_Update.zip",
        "sha256": "b" * 64,
    }

    monkeypatch.setattr(
        updater,
        "_read_json_url",
        lambda url, timeout=12: releases if url == updater._RELEASES_URL else manifest,
    )
    coordinator = _coordinator(tmp_path)

    assert coordinator._github_manifest_request() is None
