from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from .loghub import event
from .safe_update_protocol import SafeUpdateProtocol
from .update_coordinator import UpdateCoordinator

_RELEASES_URL = "https://api.github.com/repos/ramirkoz/ua-free-telegram-autopilot/releases?per_page=20"
_VERSION_RE = re.compile(r"^2\.0\.0-rc(?P<rc>[1-9]\d*)$")


def _version_number(value: str) -> int:
    match = _VERSION_RE.fullmatch(str(value or "").strip())
    return int(match.group("rc")) if match else -1


def _read_json_url(url: str, *, timeout: int = 12) -> Any:
    request = urllib.request.Request(
        str(url),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "UA-FREE-Telegram-Autopilot-Updater",
        },
    )
    with urllib.request.urlopen(request, timeout=max(3, int(timeout))) as response:
        return json.loads(response.read().decode("utf-8-sig"))


class AdvancedUpdateCoordinator(UpdateCoordinator):
    """Discover approved releases and hand deterministic requests to the safe updater."""

    def __init__(self, app, store, runtime) -> None:
        super().__init__(app, store, runtime)
        self.protocol = SafeUpdateProtocol()

    @staticmethod
    def _approved_manifest(data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        if not (
            bool(data.get("approved_for_auto_update"))
            and bool(data.get("ci_passed"))
            and bool(data.get("windows_build_passed"))
        ):
            return None
        target = str(data.get("version") or "").strip()
        if _version_number(target) < 0:
            return None
        expected_asset = f"UA_FREE_Telegram_Autopilot_v{target}_Update.zip"
        if str(data.get("artifact_filename") or expected_asset).strip() != expected_asset:
            return None
        return data

    def _request_from_manifest(self, data: dict[str, Any], *, source: str):
        target = str(data.get("version") or "").strip()
        request = self.protocol.validate_request({
            "request_id": str(data.get("request_id") or f"manifest-{target.replace('.', '-')}")[:96],
            "target_version": target,
            "sha256": str(data.get("sha256") or "").strip(),
            "created_at": str(data.get("created_at") or ""),
            "source": source,
        })
        if not self.protocol.request_is_newer(request) or self.protocol.request_already_terminal(request):
            return None
        current = self.protocol.load_request()
        if current and current.request_id == request.request_id:
            return current
        self.protocol._atomic_json(self.protocol.request_path, {
            "request_id": request.request_id,
            "target_version": request.target_version,
            "sha256": request.sha256,
            "created_at": request.created_at,
            "source": request.source,
        })
        self.protocol.write_state("REQUESTED", request=request, detail=f"approved release manifest via {source}")
        event(
            "update",
            "approved release manifest accepted",
            target_version=request.target_version,
            request_id=request.request_id,
            source=request.source,
        )
        return request

    def _github_manifest_request(self):
        releases = _read_json_url(_RELEASES_URL)
        if not isinstance(releases, list):
            raise ValueError("UPDATE_RELEASES_JSON_INVALID")

        candidates: list[tuple[int, dict[str, Any]]] = []
        for release in releases:
            if not isinstance(release, dict) or bool(release.get("draft")):
                continue
            for asset in release.get("assets") or []:
                if not isinstance(asset, dict) or str(asset.get("name") or "") != "release_manifest.json":
                    continue
                manifest_url = str(asset.get("browser_download_url") or "").strip()
                if not manifest_url:
                    continue
                manifest = self._approved_manifest(_read_json_url(manifest_url))
                if manifest is None:
                    continue
                target = str(manifest.get("version") or "")
                candidates.append((_version_number(target), manifest))
                break

        for _number, manifest in sorted(candidates, key=lambda item: item[0], reverse=True):
            request = self._request_from_manifest(manifest, source="github-release-manifest")
            if request is not None:
                return request
        return None

    def _drive_manifest_request(self):
        raw = str(self.supervisor.config.mirror_dir or "").strip()
        if not raw:
            return None
        path = Path(raw) / "release_manifest.json"
        if not path.is_file():
            return None
        try:
            manifest = self._approved_manifest(json.loads(path.read_text(encoding="utf-8-sig")))
        except Exception as exc:
            raise ValueError(f"UPDATE_MANIFEST_JSON_INVALID: {exc}") from exc
        if manifest is None:
            return None

        target = str(manifest.get("version") or "").strip()
        expected_asset = f"UA_FREE_Telegram_Autopilot_v{target}_Update.zip"
        expected_sha = str(manifest.get("sha256") or "").strip().casefold()
        artifact = Path(raw) / expected_asset
        source = "drive-release-manifest-github-download"
        if artifact.is_file():
            try:
                if self.protocol.sha256(artifact).casefold() != expected_sha:
                    return None
                source = "drive-release-manifest"
            except OSError:
                return None
        return self._request_from_manifest(manifest, source=source)

    def poll(self) -> None:
        self._after_id = None
        if self._closed or self._inflight:
            return
        try:
            request = self._github_manifest_request()
            if request is None:
                request = self.protocol.accept_mirror_request(self.supervisor.config.mirror_dir)
            if request is None:
                request = self._drive_manifest_request()
            if request is None:
                request = self.protocol.load_request()
            self.protocol.mirror_status(self.supervisor.config.mirror_dir)
            if request is None:
                self._schedule()
                return
            if self.protocol.request_already_terminal(request):
                self._schedule()
                return
            if not self.protocol.request_is_newer(request):
                self.protocol.write_result(
                    "REJECTED",
                    request=request,
                    detail=f"Target {request.target_version} is not newer than the installed version",
                )
                try:
                    self.protocol.request_path.unlink()
                except FileNotFoundError:
                    pass
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                self._schedule()
                return
            self._begin(request)
        except Exception as exc:
            event("update", "update discovery failed", level=30, detail=str(exc)[:1200])
            # A temporary GitHub/network failure must not disable local Drive fallback.
            try:
                request = self.protocol.accept_mirror_request(self.supervisor.config.mirror_dir)
                if request is None:
                    request = self._drive_manifest_request()
                if request is not None and self.protocol.request_is_newer(request):
                    self._begin(request)
                    return
            except Exception as fallback_exc:
                event("update", "update Drive fallback failed", level=30, detail=str(fallback_exc)[:1200])
            self._schedule(10000)
