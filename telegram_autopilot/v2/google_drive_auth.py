from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from ..network import fetch_url

_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
_OPENID_SCOPES = "openid email"
_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveSettingsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GoogleAuthorization:
    refresh_token: str
    access_token: str
    account_email: str


@dataclass(frozen=True, slots=True)
class GoogleDriveProfile:
    account_email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class GoogleDriveFolderProfile:
    folder_id: str
    name: str
    drive_id: str
    can_add_children: bool


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
        raise GoogleDriveSettingsError(f"Google OAuth повернув невалідну відповідь: HTTP {response.status}") from exc
    if response.status >= 400 or not isinstance(payload, dict):
        detail = ""
        if isinstance(payload, dict):
            detail = str(payload.get("error_description") or "")
            if not detail:
                error = payload.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or error.get("status") or "")
                elif error:
                    detail = str(error)
        raise GoogleDriveSettingsError(detail or f"Google OAuth HTTP {response.status}")
    return payload


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str, *, timeout: float = 20.0) -> str:
    client_id = str(client_id or "").strip()
    refresh_token = str(refresh_token or "").strip()
    if not client_id or not refresh_token:
        raise GoogleDriveSettingsError("Google Drive ще не підключено.")
    fields = {"client_id": client_id, "refresh_token": refresh_token, "grant_type": "refresh_token"}
    if str(client_secret or "").strip():
        fields["client_secret"] = str(client_secret).strip()
    payload = _post_form("https://oauth2.googleapis.com/token", fields, timeout=timeout)
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise GoogleDriveSettingsError("Google OAuth не повернув access token.")
    return token


def authorize_google_drive(client_id: str, client_secret: str, timeout_seconds: int = 240) -> GoogleAuthorization:
    client_id = str(client_id or "").strip()
    client_secret = str(client_secret or "").strip()
    if not client_id:
        raise GoogleDriveSettingsError("Вкажіть Google OAuth Client ID типу Desktop app.")

    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    result: dict[str, str] = {}
    ready = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = parse_qs(urlsplit(self.path).query)
            if (query.get("state") or [""])[0] != state:
                result["error"] = "Google OAuth повернув неправильний state."
            elif query.get("error"):
                result["error"] = str((query.get("error") or ["access_denied"])[0])
            else:
                result["code"] = str((query.get("code") or [""])[0])
            body = (
                "<html><meta charset='utf-8'><body style='font-family:Segoe UI;padding:40px'>"
                "<h2>Google Drive підключено</h2><p>Поверніться до UA FREE Telegram Autopilot. Це вікно можна закрити.</p>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            ready.set()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    server.timeout = 1.0
    redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth2callback"
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"{_OPENID_SCOPES} {_DRIVE_SCOPE}",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    webbrowser.open(auth_url, new=2)
    deadline = time.monotonic() + max(30, int(timeout_seconds))
    try:
        while time.monotonic() < deadline and not ready.is_set():
            server.handle_request()
    finally:
        server.server_close()
    if not ready.is_set():
        raise GoogleDriveSettingsError("Час очікування авторизації Google Drive минув.")
    if result.get("error"):
        raise GoogleDriveSettingsError(f"Google Drive не підключено: {result['error']}")
    code = result.get("code", "")
    if not code:
        raise GoogleDriveSettingsError("Google OAuth не повернув код авторизації.")

    fields = {
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        fields["client_secret"] = client_secret
    payload = _post_form("https://oauth2.googleapis.com/token", fields, timeout=45.0)
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise GoogleDriveSettingsError("Google не повернув довготривалий refresh token. Повторіть підключення.")

    email = ""
    try:
        response = fetch_url(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            max_bytes=512 * 1024,
            allowed_content_types={"application/json"},
            timeout=20,
            max_redirects=0,
            allow_http_errors=True,
        )
        info = response.json() if response.body else {}
        if isinstance(info, dict):
            email = str(info.get("email") or "")
    except Exception:
        pass
    return GoogleAuthorization(refresh_token=refresh_token, access_token=access_token, account_email=email)


def inspect_google_drive_connection(client_id: str, client_secret: str, refresh_token: str) -> GoogleDriveProfile:
    token = refresh_access_token(client_id, client_secret, refresh_token, timeout=15)
    response = fetch_url(
        "https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)&supportsAllDrives=true",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        max_bytes=512 * 1024,
        allowed_content_types={"application/json"},
        timeout=15,
        max_redirects=0,
        allow_http_errors=True,
    )
    payload = response.json() if response.body else {}
    if response.status >= 400 or not isinstance(payload, dict):
        raise GoogleDriveSettingsError(f"Google Drive відхилив перевірку доступу: HTTP {response.status}")
    user = payload.get("user")
    if not isinstance(user, dict):
        raise GoogleDriveSettingsError("Google Drive не повернув дані підключеного акаунта.")
    return GoogleDriveProfile(
        account_email=str(user.get("emailAddress") or ""),
        display_name=str(user.get("displayName") or ""),
    )


def inspect_drive_folder(client_id: str, client_secret: str, refresh_token: str, folder_id: str) -> GoogleDriveFolderProfile:
    folder_id = str(folder_id or "").strip()
    if not folder_id:
        raise GoogleDriveSettingsError("Вкажіть Folder ID для telemetry.")
    token = refresh_access_token(client_id, client_secret, refresh_token, timeout=15)
    url = (
        f"https://www.googleapis.com/drive/v3/files/{quote(folder_id, safe='')}?"
        + urlencode({"fields": "id,name,mimeType,driveId,capabilities(canAddChildren)", "supportsAllDrives": "true"})
    )
    response = fetch_url(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        max_bytes=512 * 1024,
        allowed_content_types={"application/json"},
        timeout=15,
        max_redirects=0,
        allow_http_errors=True,
    )
    payload = response.json() if response.body else {}
    if response.status >= 400 or not isinstance(payload, dict):
        raise GoogleDriveSettingsError(f"Папка Google Drive недоступна: HTTP {response.status}")
    if str(payload.get("mimeType") or "") != _DRIVE_FOLDER_MIME:
        raise GoogleDriveSettingsError("Заданий Folder ID не є папкою Google Drive.")
    caps = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    return GoogleDriveFolderProfile(
        folder_id=str(payload.get("id") or folder_id),
        name=str(payload.get("name") or ""),
        drive_id=str(payload.get("driveId") or ""),
        can_add_children=bool(caps.get("canAddChildren", False)),
    )
