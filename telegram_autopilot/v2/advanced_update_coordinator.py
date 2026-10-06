from __future__ import annotations

import json
import re
import threading
import urllib.request
from pathlib import Path
from typing import Any

from .loghub import event
from .safe_update_protocol import SafeUpdateProtocol
from .update_coordinator import UpdateCoordinator
from .update_signing import verify_manifest_signature

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
        self._discovery_inflight = False
        self._discovery_backoff_ms = 900000

    @staticmethod
    def _approved_manifest(data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        if not verify_manifest_signature(data):
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

    def _request_from_manifest(
        self,
        data: dict[str, Any],
        *,
        source: str,
        require_newer: bool = True,
    ):
        target = str(data.get("version") or "").strip()
        request = self.protocol.validate_request({
            "request_id": str(data.get("request_id") or f"manifest-{target.replace('.', '-')}")[:96],
            "target_version": target,
            "sha256": str(data.get("sha256") or "").strip(),
            "created_at": str(data.get("created_at") or ""),
            "source": source,
        })
        if require_newer and not self.protocol.request_is_newer(request):
            return None
        if self.protocol.request_already_terminal(request):
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
            request = self._request_from_manifest(manifest, source="github-release-manifest", require_newer=True)
            if request is not None:
                return request
        return None

    def _drive_manifest_request(self, *, require_newer: bool = True):
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
        source = "drive-release-manifest-github-fallback"
        if artifact.is_file():
            try:
                if self.protocol.sha256(artifact).casefold() != expected_sha:
                    return None
                source = "drive-release-manifest"
            except OSError:
                return None
        return self._request_from_manifest(manifest, source=source, require_newer=require_newer)

    def _manifest_request(self):
        """Compatibility surface for manifest validation tests and legacy callers.

        Live polling performs its own newer-version gate before applying any request.
        """
        return self._drive_manifest_request(require_newer=False)

    def poll(self) -> None:
        """Run release discovery off the Tk thread.

        RC99 keeps this path dormant by default until authenticated update
        manifests are deployed, but manual/test callers still get a safe poll.
        """
        self._after_id = None
        if self._closed or self._inflight or self._discovery_inflight:
            return
        self._discovery_inflight = True

        def work() -> None:
            request = None
            error = None
            try:
                request = self._github_manifest_request()
                if request is None:
                    request = self.protocol.accept_mirror_request(self.supervisor.config.mirror_dir)
                if request is None:
                    request = self._drive_manifest_request(require_newer=True)
                if request is None:
                    request = self.protocol.load_request()
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
            except Exception as exc:
                error = exc
            try:
                self.app.after(0, lambda: finish(request, error))
            except Exception:
                self._discovery_inflight = False

        def finish(request, error) -> None:
            self._discovery_inflight = False
            if self._closed:
                return
            if error is not None:
                event("update", "update discovery failed", level=30, detail=str(error)[:1200])
                self._discovery_backoff_ms = min(3600000, max(900000, self._discovery_backoff_ms * 2))
                self._schedule(self._discovery_backoff_ms)
                return
            self._discovery_backoff_ms = 900000
            if request is None:
                self._schedule(self._discovery_backoff_ms)
                return
            if self.protocol.request_already_terminal(request):
                self._schedule(self._discovery_backoff_ms)
                return
            if not self.protocol.request_is_newer(request):
                self.protocol.write_result(
                    "REJECTED", request=request,
                    detail=f"Target {request.target_version} is not newer than the installed version",
                )
                try:
                    self.protocol.request_path.unlink()
                except FileNotFoundError:
                    pass
                self.protocol.mirror_status(self.supervisor.config.mirror_dir)
                self._schedule(self._discovery_backoff_ms)
                return
            self._begin(request)

        threading.Thread(target=work, daemon=True, name="V2-Update-Discovery").start()
