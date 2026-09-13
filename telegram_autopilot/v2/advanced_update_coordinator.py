from __future__ import annotations

import json
from pathlib import Path

from .loghub import event
from .update_coordinator import UpdateCoordinator


class AdvancedUpdateCoordinator(UpdateCoordinator):
    """RC21 coordinator that also understands KONTUR-style Drive release manifests."""

    def _manifest_request(self):
        raw = str(self.supervisor.config.mirror_dir or "").strip()
        if not raw:
            return None
        path = Path(raw) / "release_manifest.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"UPDATE_MANIFEST_JSON_INVALID: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("UPDATE_MANIFEST_JSON_INVALID")
        if not (
            bool(data.get("approved_for_auto_update"))
            and bool(data.get("ci_passed"))
            and bool(data.get("windows_build_passed"))
        ):
            return None
        target = str(data.get("version") or "").strip()
        expected_asset = f"UA_FREE_Telegram_Autopilot_v{target}_Update.zip"
        if str(data.get("artifact_filename") or expected_asset).strip() != expected_asset:
            raise ValueError("UPDATE_MANIFEST_ASSET_INVALID")
        expected_sha = str(data.get("sha256") or "").strip().casefold()
        artifact = Path(raw) / expected_asset
        # Never stop the live application until the Drive-synced artifact itself is
        # present and matches the manifest. The manifest can arrive a few seconds
        # before a large ZIP through Drive for Desktop.
        if not artifact.is_file():
            return None
        try:
            if self.protocol.sha256(artifact).casefold() != expected_sha:
                return None
        except OSError:
            return None
        request = self.protocol.validate_request({
            "request_id": str(data.get("request_id") or f"manifest-{target.replace('.', '-')}")[:96],
            "target_version": target,
            "sha256": str(data.get("sha256") or "").strip(),
            "created_at": str(data.get("created_at") or ""),
            "source": "drive-release-manifest",
        })
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
        self.protocol.write_state("REQUESTED", request=request, detail="approved Drive release_manifest.json")
        return request

    def poll(self) -> None:
        self._after_id = None
        if self._closed or self._inflight:
            return
        try:
            request = self.protocol.accept_mirror_request(self.supervisor.config.mirror_dir)
            if request is None:
                request = self._manifest_request()
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
                    "REJECTED", request=request,
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
            event("update", "update request/manifest poll failed", level=30, detail=str(exc)[:1200])
            self._schedule(10000)
