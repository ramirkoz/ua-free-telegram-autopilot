from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

from .network import NetworkError, fetch_url
from .media import valid_public_media


class TelegramError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        outcome_unknown: bool = False,
        media_rejected: bool = False,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown
        self.media_rejected = media_rejected


@dataclass(frozen=True, slots=True)
class TelegramResult:
    message_id: str
    message_ids: tuple[str, ...]
    media_count: int


def normalize_chat_target(value: str) -> str:
    """Accept the forms humans actually paste for a Telegram channel.

    Supported: numeric chat IDs, @username, t.me/username and full
    https://t.me/username links. Bot API accepts @username directly.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("-") and raw[1:].isdigit():
        return raw
    if raw.isdigit():
        return raw
    if raw.startswith("@"):
        username = raw[1:].strip()
        if username and all(ch.isalnum() or ch == "_" for ch in username):
            return "@" + username
        raise TelegramError("Некоректний Telegram username.", retryable=False)
    candidate = raw if "://" in raw else ("https://" + raw if raw.lower().startswith(("t.me/", "telegram.me/")) else "")
    if candidate:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
        if host in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
            segments = [segment for segment in parts.path.split("/") if segment]
            if not segments:
                raise TelegramError("У Telegram-посиланні немає назви каналу.", retryable=False)
            username = segments[0]
            if username in {"joinchat", "+"} or username.startswith("+"):
                raise TelegramError("Для публікації потрібен публічний @username каналу або його Chat ID.", retryable=False)
            if not all(ch.isalnum() or ch == "_" for ch in username):
                raise TelegramError("Некоректне посилання на Telegram-канал.", retryable=False)
            return "@" + username
    # Also accept a bare public username to reduce pointless ceremony.
    if all(ch.isalnum() or ch == "_" for ch in raw):
        return "@" + raw
    raise TelegramError("Вставте посилання t.me/..., @username або Chat ID каналу.", retryable=False)


def _clean_paragraphs(value: str) -> str:
    parts = [" ".join(part.split()).strip() for part in str(value or "").splitlines() if part.strip()]
    return "\n\n".join(parts)


def build_post_text(
    text_or_internal_headline: str,
    body: str | None = None,
    *,
    source_url: str = "",
    include_source_link: bool = False,
    hard_limit: int = 900,
) -> str:
    """Build one body-only Telegram post with no separate headline.

    ``body`` keeps compatibility with older cached service calls that still pass
    an internal headline/cache marker as the first positional argument. The
    marker is deliberately ignored and is never rendered to Telegram.
    """
    clean = _clean_paragraphs(body if body is not None else text_or_internal_headline)
    if not clean:
        raise TelegramError("Порожній текст Telegram-поста.", retryable=False)
    if include_source_link and source_url.strip():
        clean += "\n\nДжерело"
    if len(clean) > hard_limit:
        raise TelegramError(f"Telegram-пост перевищує ліміт {hard_limit} символів.", retryable=False)
    return clean


def _utf16_units(value: str) -> int:
    return len(str(value or "").encode("utf-16-le")) // 2


def _source_link_entities(text: str, source_url: str) -> str:
    """Return Bot API JSON for a clickable trailing ``Джерело`` label."""
    url = str(source_url or "").strip()
    value = str(text or "")
    label = "Джерело"
    if not url or not value.rstrip().endswith(label):
        return ""
    start = value.rfind(label)
    entity = [{
        "type": "text_link",
        "offset": _utf16_units(value[:start]),
        "length": _utf16_units(label),
        "url": url,
    }]
    return json.dumps(entity, ensure_ascii=False, separators=(",", ":"))


def _request(token: str, method: str, fields: dict[str, str], *, timeout: float = 45.0, media_write: bool = False) -> object:
    body = urlencode(fields).encode("utf-8")
    try:
        response = fetch_url(
            f"https://api.telegram.org/bot{token}/{method}",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            body=body,
            max_bytes=3 * 1024 * 1024,
            allowed_content_types={"application/json", "text/javascript"},
            timeout=timeout,
            max_redirects=0,
            allow_http_errors=True,
        )
    except NetworkError as exc:
        raise TelegramError(f"Telegram network error: {exc}", retryable=False, outcome_unknown=True) from exc
    payload = response.json() if response.body else {}
    if not isinstance(payload, dict):
        raise TelegramError("Telegram повернув неправильний JSON.", outcome_unknown=True)
    if response.status >= 400 or payload.get("ok") is not True:
        code = int(payload.get("error_code", response.status) or response.status)
        desc = str(payload.get("description") or f"HTTP {response.status}")
        retryable = code == 429 or code >= 500
        # A definite 4xx from a media method means Telegram rejected the URL/media and no post was created.
        media_rejected = bool(media_write and 400 <= code < 500 and code != 429)
        raise TelegramError(f"Telegram: {desc} (код {code})", retryable=retryable, media_rejected=media_rejected)
    return payload.get("result")


def _result_ids(result: object) -> tuple[str, ...]:
    if isinstance(result, list):
        ids = tuple(str(row.get("message_id")) for row in result if isinstance(row, dict) and row.get("message_id"))
    elif isinstance(result, dict) and result.get("message_id"):
        ids = (str(result.get("message_id")),)
    else:
        ids = ()
    if not ids:
        raise TelegramError("Telegram не повернув message_id.", retryable=False, outcome_unknown=True)
    return ids


def send_text(token: str, chat_id: str, text: str, *, source_url: str = "", timeout: float = 45.0) -> TelegramResult:
    token = token.strip(); chat_id = normalize_chat_target(chat_id); text = text.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if not text:
        raise TelegramError("Порожній Telegram текст.", retryable=False)
    if len(text) > 4096:
        raise TelegramError("Telegram текст перевищує 4096 символів.", retryable=False)
    fields = {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    entities = _source_link_entities(text, source_url)
    if entities:
        fields["entities"] = entities
    result = _request(token, "sendMessage", fields, timeout=timeout)
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 0)


def send_publication(token: str, chat_id: str, caption: str, media_urls: list[str], *, source_url: str = "", timeout: float = 45.0) -> TelegramResult:
    """Compatibility wrapper that deliberately publishes at most one media file."""
    token = token.strip(); chat_id = normalize_chat_target(chat_id); caption = caption.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if len(caption) > 900:
        raise TelegramError("Telegram-пост перевищує ліміт 900 символів.", retryable=False)
    selected: tuple[str, str] | None = None
    for item in media_urls:
        parsed = valid_public_media(str(item))
        if parsed and parsed[0] != "iframe":
            selected = parsed
            break
    if selected is None:
        return send_text(token, chat_id, caption, source_url=source_url, timeout=timeout)
    kind, url = selected
    method = "sendVideo" if kind == "video" else "sendPhoto"
    field = "video" if kind == "video" else "photo"
    result = _request(
        token, method,
        {
            "chat_id": chat_id, field: url, "caption": caption, "show_caption_above_media": "true",
            **({"caption_entities": _source_link_entities(caption, source_url)} if _source_link_entities(caption, source_url) else {}),
        },
        timeout=timeout, media_write=True,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)


def test_bot(token: str, chat_id: str) -> str:
    token = token.strip(); chat_id = normalize_chat_target(chat_id)
    if not token or not chat_id:
        raise TelegramError("Вкажіть token та Chat ID.", retryable=False)
    response = fetch_url(
        f"https://api.telegram.org/bot{token}/getChat?" + urlencode({"chat_id": chat_id}),
        headers={"Accept": "application/json"},
        max_bytes=1024 * 1024,
        allowed_content_types={"application/json"},
        timeout=20,
        max_redirects=0,
        allow_http_errors=True,
    )
    payload = response.json() if response.body else {}
    if response.status >= 400 or not isinstance(payload, dict) or payload.get("ok") is not True:
        raise TelegramError(str(payload.get("description") if isinstance(payload, dict) else f"HTTP {response.status}"), retryable=False)
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return str(result.get("title") or result.get("username") or result.get("id") or chat_id)


def _multipart_body(fields: dict[str, str], file_field: str, filename: str, mime_type: str, data: bytes) -> tuple[str, bytes]:
    import secrets
    boundary = "----UAFreeAutopilot" + secrets.token_hex(12)
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    safe_name = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")[:120] or "image.jpg"
    chunks.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{safe_name}\"\r\n"
        f"Content-Type: {mime_type or 'application/octet-stream'}\r\n\r\n".encode("utf-8")
    )
    chunks.append(data)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("ascii"))
    return boundary, b"".join(chunks)


def _request_file(
    token: str,
    method: str,
    fields: dict[str, str],
    *,
    file_field: str,
    filename: str,
    mime_type: str,
    data: bytes,
    timeout: float = 60.0,
) -> object:
    boundary, body = _multipart_body(fields, file_field, filename, mime_type, data)
    try:
        response = fetch_url(
            f"https://api.telegram.org/bot{token}/{method}",
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
            body=body,
            max_bytes=3 * 1024 * 1024,
            allowed_content_types={"application/json", "text/javascript"},
            timeout=timeout,
            max_redirects=0,
            allow_http_errors=True,
        )
    except NetworkError as exc:
        raise TelegramError(f"Telegram network error: {exc}", retryable=False, outcome_unknown=True) from exc
    payload = response.json() if response.body else {}
    if not isinstance(payload, dict):
        raise TelegramError("Telegram повернув неправильний JSON.", outcome_unknown=True)
    if response.status >= 400 or payload.get("ok") is not True:
        code = int(payload.get("error_code", response.status) or response.status)
        desc = str(payload.get("description") or f"HTTP {response.status}")
        retryable = code == 429 or code >= 500
        media_rejected = bool(400 <= code < 500 and code != 429)
        raise TelegramError(f"Telegram: {desc} (код {code})", retryable=retryable, media_rejected=media_rejected)
    return payload.get("result")



def send_video_url(
    token: str,
    chat_id: str,
    caption: str,
    video_url: str,
    *,
    source_url: str = "",
    timeout: float = 60.0,
) -> TelegramResult:
    """Ask Telegram to fetch a direct public video URL.

    Embedded players (YouTube/Vimeo iframe URLs) are deliberately not sent as
    videos; production publishes their preview image plus a canonical watch link.
    """
    token = token.strip(); chat_id = normalize_chat_target(chat_id); caption = caption.strip(); video_url = video_url.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    parsed = valid_public_media("video|" + video_url)
    if not parsed or parsed[0] != "video":
        raise TelegramError("Некоректна адреса відео.", retryable=False, media_rejected=True)
    if len(caption) > 1024:
        raise TelegramError("Telegram caption перевищує 1024 символи.", retryable=False)
    fields = {"chat_id": chat_id, "video": parsed[1], "caption": caption, "show_caption_above_media": "true"}
    entities = _source_link_entities(caption, source_url)
    if entities:
        fields["caption_entities"] = entities
    result = _request(token, "sendVideo", fields, timeout=timeout, media_write=True)
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)

def send_prepared_photo(
    token: str,
    chat_id: str,
    caption: str,
    *,
    filename: str,
    mime_type: str,
    data: bytes,
    source_url: str = "",
    timeout: float = 60.0,
) -> TelegramResult:
    """Upload the editorial hero as bytes instead of asking Telegram to hotlink it.

    Many publishers/CDNs allow the desktop app to fetch an image but reject Telegram's
    remote fetch. Uploading the already validated image fixes that class of failure.
    """
    token = token.strip(); chat_id = normalize_chat_target(chat_id); caption = caption.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if len(caption) > 1024:
        raise TelegramError("Telegram caption перевищує 1024 символи.", retryable=False)
    if not data:
        return send_text(token, chat_id, caption, source_url=source_url, timeout=timeout)
    if len(data) > 9_500_000:
        raise TelegramError("Головне фото завелике для безпечного Telegram upload.", retryable=False, media_rejected=True)
    result = _request_file(
        token,
        "sendPhoto",
        {
            "chat_id": chat_id, "caption": caption, "show_caption_above_media": "true",
            **({"caption_entities": _source_link_entities(caption, source_url)} if _source_link_entities(caption, source_url) else {}),
        },
        file_field="photo",
        filename=filename,
        mime_type=mime_type or "image/jpeg",
        data=data,
        timeout=timeout,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)
