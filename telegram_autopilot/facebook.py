from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class FacebookError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True, code: str = "") -> None:
        super().__init__(message)
        self.retryable = bool(retryable)
        self.code = str(code or "")


@dataclass(frozen=True, slots=True)
class FacebookPage:
    id: str
    name: str
    access_token: str


def _version(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "v26.0"
    return text if text.startswith("v") else "v" + text


def _graph_json(
    path: str,
    *,
    token: str,
    version: str = "v26.0",
    method: str = "GET",
    data: dict[str, Any] | None = None,
    timeout: float = 25.0,
) -> dict[str, Any]:
    access_token = str(token or "").strip()
    if not access_token:
        raise FacebookError("Facebook access token не налаштовано.", retryable=False, code="AUTH_MISSING")
    base = f"https://graph.facebook.com/{_version(version)}/{str(path).lstrip('/')}"
    payload = {str(k): str(v) for k, v in dict(data or {}).items() if v is not None}
    payload["access_token"] = access_token
    body = None
    url = base
    headers = {"Accept": "application/json", "User-Agent": "UA-FREE-Telegram-Autopilot/2"}
    if str(method).upper() == "GET":
        url += ("&" if "?" in url else "?") + parse.urlencode(payload)
    else:
        body = parse.urlencode(payload).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = request.Request(url, data=body, headers=headers, method=str(method).upper())
    try:
        with request.urlopen(req, timeout=max(5.0, float(timeout))) as response:
            raw = response.read().decode("utf-8", "replace")
            obj = json.loads(raw or "{}")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            obj = json.loads(raw or "{}")
            err = obj.get("error") if isinstance(obj, dict) else None
            message = str((err or {}).get("message") or raw or exc.reason)
            code = str((err or {}).get("code") or exc.code)
            subcode = str((err or {}).get("error_subcode") or "")
        except Exception:
            message, code, subcode = str(exc.reason), str(exc.code), ""
        retryable = exc.code >= 500 or code in {"1", "2", "4", "17", "32", "341", "613"}
        if code in {"10", "102", "190", "200"}:
            retryable = False
        suffix = f" (code {code}{('/' + subcode) if subcode else ''})" if code else ""
        raise FacebookError("Facebook Graph API: " + message + suffix, retryable=retryable, code=code) from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise FacebookError(f"Facebook Graph API недоступний: {exc}", retryable=True, code="NETWORK") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise FacebookError("Facebook Graph API повернув некоректну відповідь.", retryable=True, code="BAD_RESPONSE") from exc
    if not isinstance(obj, dict):
        raise FacebookError("Facebook Graph API повернув неочікуваний формат.", retryable=True, code="BAD_RESPONSE")
    if isinstance(obj.get("error"), dict):
        err = obj["error"]
        code = str(err.get("code") or "")
        raise FacebookError(
            "Facebook Graph API: " + str(err.get("message") or "невідома помилка"),
            retryable=code not in {"10", "102", "190", "200"},
            code=code,
        )
    return obj


def discover_pages(user_access_token: str, graph_version: str = "v26.0") -> list[FacebookPage]:
    obj = _graph_json(
        "me/accounts",
        token=user_access_token,
        version=graph_version,
        data={"fields": "id,name,access_token", "limit": "100"},
        timeout=30.0,
    )
    result: list[FacebookPage] = []
    seen: set[str] = set()
    rows = obj.get("data") if isinstance(obj, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        page_id = str(row.get("id") or "").strip()
        token = str(row.get("access_token") or "").strip()
        if not page_id or not token or page_id in seen:
            continue
        seen.add(page_id)
        result.append(FacebookPage(page_id, str(row.get("name") or page_id).strip() or page_id, token))
    return result


def inspect_page(page_id: str, page_access_token: str, graph_version: str = "v26.0") -> FacebookPage:
    obj = _graph_json(
        str(page_id).strip(),
        token=page_access_token,
        version=graph_version,
        data={"fields": "id,name"},
        timeout=20.0,
    )
    value = str(obj.get("id") or page_id).strip()
    return FacebookPage(value, str(obj.get("name") or value).strip() or value, str(page_access_token or "").strip())


def publish_page_link(
    page_id: str,
    page_access_token: str,
    *,
    message: str,
    telegram_post_url: str,
    graph_version: str = "v26.0",
) -> str:
    text = str(message or "").strip()
    link = str(telegram_post_url or "").strip()
    if not text:
        raise FacebookError("Facebook-текст порожній.", retryable=False, code="TEXT_MISSING")
    if not link.startswith(("http://", "https://")):
        raise FacebookError("Немає посилання на Telegram-пост для Facebook.", retryable=False, code="TELEGRAM_LINK_MISSING")
    obj = _graph_json(
        f"{str(page_id).strip()}/feed",
        token=page_access_token,
        version=graph_version,
        method="POST",
        data={"message": text, "link": link},
        timeout=35.0,
    )
    post_id = str(obj.get("id") or "").strip()
    if not post_id:
        raise FacebookError("Facebook не повернув ID опублікованого поста.", retryable=True, code="POST_ID_MISSING")
    return post_id
