from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode


from ..network import NetworkError, fetch_url
from ..secrets_store import load_secrets

_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveTelemetryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DriveCredentials:
    client_id: str
    client_secret: str
    refresh_token: str
    account_email: str = ""
    source: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.client_id.strip() and self.refresh_token.strip())


def _own_credentials() -> DriveCredentials | None:
    try:
        cfg = load_secrets()
    except Exception:
        return None
    client_id = str(getattr(cfg, "google_client_id", "") or "").strip()
    refresh_token = str(getattr(cfg, "google_refresh_token", "") or "").strip()
    if not client_id or not refresh_token:
        return None
    return DriveCredentials(
        client_id=client_id,
        client_secret=str(getattr(cfg, "google_client_secret", "") or "").strip(),
        refresh_token=refresh_token,
        account_email=str(getattr(cfg, "google_account_email", "") or "").strip(),
        source=str(getattr(cfg, "google_credential_origin", "") or "legacy-unverified"),
    )


def _environment_credentials() -> DriveCredentials | None:
    client_id = str(os.environ.get("UA_FREE_GOOGLE_CLIENT_ID") or "").strip()
    refresh_token = str(os.environ.get("UA_FREE_GOOGLE_REFRESH_TOKEN") or "").strip()
    if not client_id or not refresh_token:
        return None
    return DriveCredentials(
        client_id=client_id,
        client_secret=str(os.environ.get("UA_FREE_GOOGLE_CLIENT_SECRET") or "").strip(),
        refresh_token=refresh_token,
        account_email=str(os.environ.get("UA_FREE_GOOGLE_ACCOUNT_EMAIL") or "").strip(),
        source="environment",
    )


def _credential_candidates() -> list[DriveCredentials]:
    """Only credentials expressly configured for Autopilot; never scan other apps."""
    out: list[DriveCredentials] = []
    seen: set[tuple[str, str]] = set()
    for getter in (_own_credentials, _environment_credentials):
        value = getter()
        if value is not None and value.ready:
            key = (value.client_id, value.refresh_token)
            if key not in seen:
                out.append(value)
                seen.add(key)
    return out


def discover_drive_credentials(*, persist_companion: bool = False) -> DriveCredentials | None:
    """Compatibility signature; the old Content Tool import is permanently disabled."""
    candidates = _credential_candidates()
    return candidates[0] if candidates else None


def _post_form(url: str, fields: dict[str, str], *, timeout: float = 30.0) -> dict:
    response = fetch_url(
        url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        body=urlencode(fields).encode("utf-8"),
        max_bytes=2 * 1024 * 1024,
        allowed_content_types={"application/json", "text/javascript"},
        timeout=timeout,
        max_redirects=0,
        allow_http_errors=True,
    )
    try:
        payload = response.json() if response.body else {}
    except Exception as exc:
        raise DriveTelemetryError(f"Google OAuth returned invalid JSON: HTTP {response.status}") from exc
    if response.status >= 400 or not isinstance(payload, dict):
        detail = payload.get("error_description") if isinstance(payload, dict) else ""
        if not detail and isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message") or error.get("status") or error
            elif error:
                detail = error
        raise DriveTelemetryError(str(detail or f"Google OAuth HTTP {response.status}"))
    return payload


class DirectDriveTelemetry:
    """Outbound-only Google Drive transport for passive supervisor telemetry.

    It never reads commands and never changes sharing. OAuth credentials are exclusively from Autopilot secrets or explicit
    Autopilot environment variables. Other applications are never scanned.
    """

    def __init__(self, folder_name: str, *, folder_id: str = "") -> None:
        self.folder_name = str(folder_name or "").strip()
        # RC103: prefer one explicit canonical Drive folder ID over name-only
        # discovery. This avoids Shared Drive / My Drive ambiguity and duplicate
        # folders with the same display name.
        self._configured_folder_id = str(
            folder_id or os.environ.get("UA_FREE_AUTOPILOT_LIVE_FOLDER_ID") or ""
        ).strip()
        self._credentials: DriveCredentials | None = None
        self._access_token = ""
        self._folder_id = self._configured_folder_id
        self._last_credential_probe = 0.0
        self._last_ok_at = ""
        self._last_error = ""
        self._credential_source = ""

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _credentials_now(self, *, force: bool = False) -> DriveCredentials:
        now = time.monotonic()
        if self._credentials is not None and not force:
            return self._credentials
        if not force and now - self._last_credential_probe < 15.0:
            raise DriveTelemetryError(self._last_error or "Google Drive credentials not found")
        self._last_credential_probe = now
        value = discover_drive_credentials()
        if value is None:
            self._last_error = "Autopilot Google Drive not configured. Connect in Autopilot Drive settings."
            raise DriveTelemetryError(self._last_error)
        self._credentials = value
        self._credential_source = value.source
        return value

    def _token(self, *, force: bool = False) -> str:
        if self._access_token and not force:
            return self._access_token

        candidates: list[DriveCredentials] = []
        if self._credentials is not None and self._credentials.ready:
            candidates.append(self._credentials)
        for value in _credential_candidates():
            if any(
                value.client_id == existing.client_id
                and value.refresh_token == existing.refresh_token
                for existing in candidates
            ):
                continue
            candidates.append(value)

        if not candidates:
            self._last_error = (
                "Autopilot Google Drive credentials absent. Connect inside Autopilot."
            )
            raise DriveTelemetryError(self._last_error)

        errors: list[str] = []
        for creds in candidates:
            fields = {
                "client_id": creds.client_id,
                "refresh_token": creds.refresh_token,
                "grant_type": "refresh_token",
            }
            if creds.client_secret:
                fields["client_secret"] = creds.client_secret
            try:
                payload = _post_form("https://oauth2.googleapis.com/token", fields, timeout=30.0)
                token = str(payload.get("access_token") or "").strip()
                if not token:
                    raise DriveTelemetryError("Google OAuth did not return access_token")
            except Exception as exc:
                errors.append(f"{creds.source or 'unknown'}: {type(exc).__name__}: {exc}")
                continue

            self._credentials = creds
            self._credential_source = creds.source
            self._access_token = token
            self._last_error = ""
            return token

        self._credentials = None
        self._access_token = ""
        self._last_error = ("All Google Drive OAuth credential sources failed: " + "; ".join(errors))[:1200]
        raise DriveTelemetryError(self._last_error)

    def _json_request(self, url: str, *, method: str = "GET", payload: dict | None = None, retry_auth: bool = True) -> dict:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        response = fetch_url(
            url,
            method=method,
            headers=headers,
            body=body,
            max_bytes=3 * 1024 * 1024,
            allowed_content_types={"application/json"},
            timeout=30.0,
            max_redirects=0,
            allow_http_errors=True,
        )
        if response.status in {401, 403} and retry_auth:
            self._access_token = ""
            self._credentials = None
            return self._json_request(url, method=method, payload=payload, retry_auth=False)
        try:
            data = response.json() if response.body else {}
        except Exception as exc:
            raise DriveTelemetryError(f"Google Drive returned invalid JSON: HTTP {response.status}") from exc
        if response.status >= 400 or not isinstance(data, dict):
            detail = ""
            if isinstance(data, dict):
                error = data.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or error.get("status") or "")
                elif error:
                    detail = str(error)
            raise DriveTelemetryError(detail or f"Google Drive API HTTP {response.status}")
        return data

    @staticmethod
    def _escape_q(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace("'", "\\'")

    def _find_child(self, parent_id: str, name: str, *, folder: bool) -> str:
        parts = [
            f"name='{self._escape_q(name)}'",
            f"'{self._escape_q(parent_id)}' in parents",
            "trashed=false",
            f"mimeType{'=' if folder else '!='}'{_DRIVE_FOLDER_MIME}'",
        ]
        url = "https://www.googleapis.com/drive/v3/files?" + urlencode({
            "q": " and ".join(parts),
            "fields": "files(id,name,mimeType,modifiedTime,size)",
            "pageSize": "10",
            "orderBy": "modifiedTime desc",
            "spaces": "drive",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "corpora": "allDrives",
        })
        data = self._json_request(url)
        files = data.get("files")
        if isinstance(files, list) and files and isinstance(files[0], dict):
            return str(files[0].get("id") or "")
        return ""

    def _ensure_folder(self) -> str:
        if self._folder_id:
            return self._folder_id
        found = self._find_child("root", self.folder_name, folder=True)
        if found:
            self._folder_id = found
            return found
        data = self._json_request(
            "https://www.googleapis.com/drive/v3/files?fields=id,name&supportsAllDrives=true",
            method="POST",
            payload={"name": self.folder_name, "mimeType": _DRIVE_FOLDER_MIME, "parents": ["root"]},
        )
        folder_id = str(data.get("id") or "")
        if not folder_id:
            raise DriveTelemetryError(f"Google Drive did not return folder id for {self.folder_name}")
        self._folder_id = folder_id
        return folder_id

    def _upload_resumable(self, name: str, data: bytes, parent_id: str) -> str:
        """Upload big SQLite snapshots without multipart's small-file assumptions."""
        existing = self._find_child(parent_id, name, folder=False)
        metadata: dict[str, object] = {"name": name, "mimeType": "application/octet-stream"}
        if not existing:
            metadata["parents"] = [parent_id]
        if existing:
            url = f"https://www.googleapis.com/upload/drive/v3/files/{quote(existing, safe='')}?uploadType=resumable&fields=id,name,modifiedTime&supportsAllDrives=true"
            method = "PATCH"
        else:
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,modifiedTime&supportsAllDrives=true"
            method = "POST"
        token = self._token()
        start = fetch_url(
            url, method=method, headers={
                "Authorization": f"Bearer {token}", "Accept": "application/json",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
                "X-Upload-Content-Length": str(len(data)),
            },
            body=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            max_bytes=1024 * 1024, timeout=45.0, max_redirects=0, allow_http_errors=True,
        )
        if start.status not in (200, 201):
            raise DriveTelemetryError(f"Google Drive resumable session failed: HTTP {start.status}")
        session = str(start.headers.get("location") or "")
        from urllib.parse import urlsplit
        parsed = urlsplit(session)
        if parsed.scheme != "https" or not (
            parsed.hostname == "googleapis.com" or str(parsed.hostname or "").endswith(".googleapis.com")
        ):
            raise DriveTelemetryError("Google Drive resumable session URL missing or untrusted")
        finish = fetch_url(
            session, method="PUT", headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
                "Content-Range": f"bytes 0-{len(data)-1}/{len(data)}",
            },
            body=data, max_bytes=2 * 1024 * 1024,
            timeout=180.0, max_redirects=0, allow_http_errors=True,
        )
        if finish.status not in (200, 201):
            raise DriveTelemetryError(f"Google Drive resumable upload failed: HTTP {finish.status}")
        try:
            value = finish.json()
        except Exception as exc:
            raise DriveTelemetryError("Google Drive resumable upload returned invalid JSON") from exc
        file_id = str(value.get("id") or existing) if isinstance(value, dict) else ""
        if not file_id:
            raise DriveTelemetryError("Google Drive resumable upload returned no file ID")
        return file_id

    def _upload_bytes(self, name: str, data: bytes, parent_id: str) -> str:
        if name.casefold().endswith(".sqlite3") and len(data) > 5 * 1024 * 1024:
            return self._upload_resumable(name, data, parent_id)
        existing = self._find_child(parent_id, name, folder=False)
        boundary = "ua_free_autopilot_" + secrets.token_hex(12)
        metadata: dict[str, object] = {"name": name}
        if not existing:
            metadata["parents"] = [parent_id]
        payload_type = "application/octet-stream" if name.casefold().endswith(".sqlite3") else "application/json"
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + json.dumps(metadata, ensure_ascii=False)
            + f"\r\n--{boundary}\r\nContent-Type: {payload_type}\r\n\r\n"
        ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        token = self._token()
        if existing:
            url = f"https://www.googleapis.com/upload/drive/v3/files/{quote(existing, safe='')}?uploadType=multipart&fields=id,name,modifiedTime&supportsAllDrives=true"
            method = "PATCH"
        else:
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,modifiedTime&supportsAllDrives=true"
            method = "POST"
        response = fetch_url(
            url,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            body=body,
            max_bytes=2 * 1024 * 1024,
            allowed_content_types={"application/json"},
            timeout=45.0,
            max_redirects=0,
            allow_http_errors=True,
        )
        if response.status in {401, 403}:
            self._access_token = ""
            self._credentials = None
            if existing:
                self._folder_id = self._configured_folder_id
            raise DriveTelemetryError(f"Google Drive authentication failed: HTTP {response.status}")
        try:
            payload = response.json() if response.body else {}
        except Exception as exc:
            raise DriveTelemetryError(f"Google Drive upload returned invalid JSON: HTTP {response.status}") from exc
        if response.status >= 400 or not isinstance(payload, dict):
            raise DriveTelemetryError(f"Google Drive upload failed: HTTP {response.status}")
        file_id = str(payload.get("id") or existing)
        if not file_id:
            raise DriveTelemetryError(f"Google Drive did not return file id for {name}")
        return file_id

    def upload_bytes(self, name: str, payload: bytes) -> str:
        """Upload a stable supervisor snapshot, not a file changing mid-request.

        Transport remains outbound-only; no remote command handling or new
        credential, source, and sharing logic is introduced.
        """
        try:
            folder_id = self._ensure_folder()
            file_id = self._upload_bytes(str(name), bytes(payload), folder_id)
            self._last_ok_at = self._now_iso()
            self._last_error = ""
            return file_id
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"[:1200]
            raise

    def upload_path(self, path: Path, *, name: str | None = None) -> str:
        source = Path(path)
        return self.upload_bytes(name or source.name, source.read_bytes())

    def status(self) -> dict[str, object]:
        return {
            "mode": "google_drive_api",
            "folder_name": self.folder_name,
            "folder_id": self._folder_id,
            "configured_folder_id": self._configured_folder_id,
            "credential_source": self._credential_source,
            "configured": self._credentials is not None or _own_credentials() is not None,
            "last_ok_at": self._last_ok_at,
            "last_error": self._last_error,
        }
