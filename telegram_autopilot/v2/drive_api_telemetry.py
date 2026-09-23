from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..network import NetworkError, fetch_url
from ..paths import runtime_dir
from ..secrets_store import load_secrets, save_secrets

_CONTENT_HEADER = b"UA_FREE_PORTABLE_AESGCM_V1\n"
_CONTENT_AAD = b"UA_FREE_Content_Tool_portable_config_v1"
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
        source="autopilot-secrets",
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


def _portable_content_config(config_path: Path) -> DriveCredentials | None:
    key_path = config_path.with_name("portable.key")
    if not config_path.is_file() or not key_path.is_file():
        return None
    encrypted = config_path.read_bytes()
    if not encrypted.startswith(_CONTENT_HEADER):
        return None
    key = key_path.read_bytes()
    if len(key) != 32:
        return None
    payload = encrypted[len(_CONTENT_HEADER):]
    if len(payload) < 13:
        return None
    nonce, ciphertext = payload[:12], payload[12:]
    try:
        raw = AESGCM(key).decrypt(nonce, ciphertext, _CONTENT_AAD)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    client_id = str(data.get("google_client_id") or "").strip()
    refresh_token = str(data.get("google_refresh_token") or "").strip()
    if not client_id or not refresh_token:
        return None
    return DriveCredentials(
        client_id=client_id,
        client_secret=str(data.get("google_client_secret") or "").strip(),
        refresh_token=refresh_token,
        account_email=str(data.get("google_account_email") or "").strip(),
        source=f"content-tool:{config_path.parent.parent}",
    )


def _content_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit_data = str(os.environ.get("UA_FREE_CONTENT_DATA") or "").strip()
    if explicit_data:
        candidates.append(Path(explicit_data).expanduser() / "config.portable")
    explicit_root = str(os.environ.get("UA_FREE_CONTENT_TOOL_ROOT") or "").strip()
    if explicit_root:
        candidates.append(Path(explicit_root).expanduser() / "Data" / "config.portable")

    root = runtime_dir()
    bases = [
        root.parent,
        root.parent.parent,
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "OneDrive" / "Desktop",
        Path.home() / "OneDrive" / "Робочий стіл",
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for base in bases:
        try:
            resolved = str(base.expanduser().absolute())
        except Exception:
            resolved = str(base)
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if not base.is_dir():
                continue
            for item in base.iterdir():
                try:
                    if not item.is_dir():
                        continue
                except OSError:
                    continue
                name = item.name.casefold()
                if not name.startswith("ua_free_content_tool"):
                    continue
                out.append(item / "Data" / "config.portable")
        except OSError:
            continue

    out.extend(candidates)
    unique: dict[str, Path] = {}
    for path in out:
        unique[str(path)] = path
    values = list(unique.values())
    values.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
    return values


def discover_drive_credentials(*, persist_companion: bool = True) -> DriveCredentials | None:
    for getter in (_own_credentials, _environment_credentials):
        value = getter()
        if value is not None and value.ready:
            return value

    for config_path in _content_config_candidates():
        value = _portable_content_config(config_path)
        if value is None or not value.ready:
            continue
        if persist_companion:
            try:
                cfg = load_secrets()
                cfg.google_client_id = value.client_id
                cfg.google_client_secret = value.client_secret
                cfg.google_refresh_token = value.refresh_token
                cfg.google_account_email = value.account_email
                save_secrets(cfg)
                return DriveCredentials(
                    client_id=value.client_id,
                    client_secret=value.client_secret,
                    refresh_token=value.refresh_token,
                    account_email=value.account_email,
                    source=value.source + ":persisted",
                )
            except Exception:
                pass
        return value
    return None


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

    It never reads commands and never changes sharing. OAuth credentials are taken
    from Autopilot secrets, environment variables, or the sibling portable Content
    Tool configuration already authorized by the same Windows user.
    """

    def __init__(self, folder_name: str) -> None:
        self.folder_name = str(folder_name or "").strip()
        self._credentials: DriveCredentials | None = None
        self._access_token = ""
        self._folder_id = ""
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
        value = discover_drive_credentials(persist_companion=True)
        if value is None:
            self._last_error = "Google Drive OAuth credentials not found; connect Drive in Content Tool or set UA_FREE_GOOGLE_*"
            raise DriveTelemetryError(self._last_error)
        self._credentials = value
        self._credential_source = value.source
        return value

    def _token(self, *, force: bool = False) -> str:
        if self._access_token and not force:
            return self._access_token
        creds = self._credentials_now(force=force)
        fields = {
            "client_id": creds.client_id,
            "refresh_token": creds.refresh_token,
            "grant_type": "refresh_token",
        }
        if creds.client_secret:
            fields["client_secret"] = creds.client_secret
        payload = _post_form("https://oauth2.googleapis.com/token", fields, timeout=30.0)
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise DriveTelemetryError("Google OAuth did not return access_token")
        self._access_token = token
        return token

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
            "https://www.googleapis.com/drive/v3/files?fields=id,name",
            method="POST",
            payload={"name": self.folder_name, "mimeType": _DRIVE_FOLDER_MIME, "parents": ["root"]},
        )
        folder_id = str(data.get("id") or "")
        if not folder_id:
            raise DriveTelemetryError(f"Google Drive did not return folder id for {self.folder_name}")
        self._folder_id = folder_id
        return folder_id

    def _upload_bytes(self, name: str, data: bytes, parent_id: str) -> str:
        existing = self._find_child(parent_id, name, folder=False)
        boundary = "ua_free_autopilot_" + secrets.token_hex(12)
        metadata: dict[str, object] = {"name": name}
        if not existing:
            metadata["parents"] = [parent_id]
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + json.dumps(metadata, ensure_ascii=False)
            + f"\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n"
        ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        token = self._token()
        if existing:
            url = f"https://www.googleapis.com/upload/drive/v3/files/{quote(existing, safe='')}?uploadType=multipart&fields=id,name,modifiedTime"
            method = "PATCH"
        else:
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,modifiedTime"
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
                self._folder_id = ""
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

    def upload_path(self, path: Path, *, name: str | None = None) -> str:
        source = Path(path)
        folder_id = self._ensure_folder()
        try:
            file_id = self._upload_bytes(name or source.name, source.read_bytes(), folder_id)
            self._last_ok_at = self._now_iso()
            self._last_error = ""
            return file_id
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"[:1200]
            raise

    def status(self) -> dict[str, object]:
        return {
            "mode": "google_drive_api",
            "folder_name": self.folder_name,
            "folder_id": self._folder_id,
            "credential_source": self._credential_source,
            "configured": self._credentials is not None or _own_credentials() is not None,
            "last_ok_at": self._last_ok_at,
            "last_error": self._last_error,
        }
