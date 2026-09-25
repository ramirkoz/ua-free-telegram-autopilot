from __future__ import annotations

import json
from pathlib import Path

from .loghub import event
from .safe_update_protocol import SafeUpdateProtocol
from .update_coordinator import UpdateCoordinator


class AdvancedUpdateCoordinator(UpdateCoordinator):
    """Production coordinator for approved Drive manifests and deterministic updates."""

    def __init__(self, app, store, runtime) -> None:
        super().__init__(app, store, runtime)
        self.protocol = SafeUpdateProtocol()

    def _refresh_mirror(self) -> None:
        ensure = getattr(self.supervisor, "ensure_live_mirror", None)
        if callable(ensure):
            try:
                ensure(force=False)
            except Exception as exc:
                event("update", "telemetry mirror refresh before update poll failed", level=30, detail=str(exc)[:800])

    def _manifest_request(self):
        self._refresh_mirror()
        raw = str(self.supervisor.config.mirror_dir or "").strip()
        if not raw:
            return None
        path = Path(raw) / "release_manifest.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
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

        # The small signed/approved manifest is sufficient to request an update.
        # The detached helper always constructs the GitHub URL from the fixed repo
        # and verifies this SHA. If Drive has already synced the exact overlay we use
        # it; otherwise the helper safely downloads the same release from GitHub.
        source = "drive-release-manifest-github-fallback"
        if artifact.is_file():
            try:
                if self.protocol.sha256(artifact).casefold() != expected_sha:
                    # A partially synced Drive ZIP must never win the helper race.
                    return None
                source = "drive-release-manifest"
            except OSError:
                return None

        request = self.protocol.validate_request({
            "request_id": str(data.get("request_id") or f"manifest-{target.replace('.', '-')}")[:96],
            "target_version": target,
            "sha256": str(data.get("sha256") or "").strip(),
            "created_at": str(data.get("created_at") or ""),
            "source": source,
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
        event(
            "update", "approved release manifest accepted",
            target_version=request.target_version, request_id=request.request_id, source=request.source,
        )
        return request

    def poll(self) -> None:
        self._after_id = None
        if self._closed or self._inflight:
            return
        try:
            self._refresh_mirror()
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
