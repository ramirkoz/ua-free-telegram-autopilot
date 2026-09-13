from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlencode, urlsplit

from .network import NetworkError, fetch_url
from .media import media_identity, valid_public_media


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


@dataclass(frozen=True, slots=True)
class PreparedTelegramMedia:
    """Media fetched by Autopilot and ready for Bot API multipart upload.

    RC17 deliberately does not ask Telegram to hotlink third-party media.  Several
    Telegram/CDN URLs are readable from the operator machine but fail inside the
    Bot API with WEBPAGE_CURL_FAILED.  Keeping the bytes here also lets us dedupe
    URL variants by their actual content digest before publication.
    """

    kind: str
    source_url: str
    filename: str
    mime_type: str
    data: bytes
    digest: str


_MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,video/*,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.7",
    "Cache-Control": "no-cache",
}


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


def _normalize_source_urls(source_url: str = "", source_urls: list[str] | tuple[str, ...] | None = None) -> list[str]:
    out: list[str] = []
    for item in [str(source_url or ""), *(list(source_urls or []))]:
        url = str(item or "").strip()
        if url.startswith(("http://", "https://")) and url not in out:
            out.append(url)
    return out


def build_post_text(
    text_or_internal_headline: str,
    body: str | None = None,
    *,
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    include_source_link: bool = False,
    hard_limit: int = 900,
) -> str:
    """Build a Telegram caption/text with attribution at the bottom.

    ``body`` keeps compatibility with older cached service calls that still pass
    an internal headline/cache marker as the first positional argument. The
    marker is deliberately ignored and is never rendered to Telegram.
    """
    clean = _clean_paragraphs(body if body is not None else text_or_internal_headline)
    if not clean:
        raise TelegramError("Порожній текст Telegram-поста.", retryable=False)
    urls = _normalize_source_urls(source_url, source_urls)
    if include_source_link and urls:
        if len(urls) == 1:
            footer = "Джерело"
        else:
            footer = "\n".join(f"Джерело {idx}" for idx in range(1, len(urls) + 1))
        clean += "\n\n" + footer
    if len(clean) > hard_limit:
        raise TelegramError(f"Telegram-пост перевищує ліміт {hard_limit} символів.", retryable=False)
    return clean


def _utf16_units(value: str) -> int:
    return len(str(value or "").encode("utf-16-le")) // 2


def _source_link_entities(
    text: str,
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Return Bot API JSON for clickable source labels at the very bottom."""
    urls = _normalize_source_urls(source_url, source_urls)
    value = str(text or "")
    if not urls:
        return ""
    labels = ["Джерело"] if len(urls) == 1 else [f"Джерело {i}" for i in range(1, len(urls) + 1)]
    entities = []
    for label, url in zip(labels, urls):
        # Attribution labels are deliberately at the bottom. rfind avoids
        # accidentally hyperlinking the word "Джерело" if it occurs in body text.
        start = value.rfind(label)
        if start < 0:
            return ""
        entities.append({
            "type": "text_link",
            "offset": _utf16_units(value[:start]),
            "length": _utf16_units(label),
            "url": url,
        })
    return json.dumps(entities, ensure_ascii=False, separators=(",", ":"))


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


def send_text(token: str, chat_id: str, text: str, *, source_url: str = "", source_urls: list[str] | tuple[str, ...] | None = None, timeout: float = 45.0) -> TelegramResult:
    token = token.strip(); chat_id = normalize_chat_target(chat_id); text = text.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if not text:
        raise TelegramError("Порожній Telegram текст.", retryable=False)
    if len(text) > 4096:
        raise TelegramError("Telegram текст перевищує 4096 символів.", retryable=False)
    fields = {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    entities = _source_link_entities(text, source_url, source_urls)
    if entities:
        fields["entities"] = entities
    result = _request(token, "sendMessage", fields, timeout=timeout)
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 0)


def _valid_media_items(media_urls: list[str] | tuple[str, ...]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in media_urls:
        parsed = valid_public_media(str(item or ""))
        if not parsed:
            continue
        kind, url = parsed
        if kind not in {"image", "video"}:
            continue
        identity = media_identity(kind, url)
        if identity in seen:
            continue
        seen.add(identity)
        out.append((kind, url))
        if len(out) >= 10:
            break
    return out


def send_media_only(token: str, chat_id: str, media_url: str, *, timeout: float = 55.0) -> TelegramResult:
    """Send one photo/video with no caption. Used when media is a separate publication part."""
    token = token.strip(); chat_id = normalize_chat_target(chat_id)
    items = _valid_media_items([media_url])
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if not items:
        raise TelegramError("Немає валідного медіа для Telegram.", retryable=False, media_rejected=True)
    kind, url = items[0]
    method = "sendVideo" if kind == "video" else "sendPhoto"
    field = "video" if kind == "video" else "photo"
    result = _request(token, method, {"chat_id": chat_id, field: url}, timeout=timeout, media_write=True)
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)


def send_media_group(token: str, chat_id: str, media_urls: list[str] | tuple[str, ...], *, caption: str = "", source_url: str = "", source_urls: list[str] | tuple[str, ...] | None = None, timeout: float = 60.0) -> TelegramResult:
    """Send a real Telegram media group, preserving source order, up to ten items."""
    token = token.strip(); chat_id = normalize_chat_target(chat_id)
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    items = _valid_media_items(media_urls)
    if len(items) < 2:
        raise TelegramError("Для media group потрібно щонайменше два валідні медіа.", retryable=False, media_rejected=True)
    if caption and len(caption) > 1024:
        raise TelegramError("Telegram caption media group перевищує 1024 символи.", retryable=False)
    media: list[dict[str, object]] = []
    entities = _source_link_entities(caption, source_url, source_urls) if caption else ""
    for idx, (kind, url) in enumerate(items):
        row: dict[str, object] = {"type": "video" if kind == "video" else "photo", "media": url}
        if idx == 0 and caption:
            row["caption"] = caption
            if entities:
                row["caption_entities"] = json.loads(entities)
        media.append(row)
    result = _request(
        token, "sendMediaGroup",
        {"chat_id": chat_id, "media": json.dumps(media, ensure_ascii=False, separators=(",", ":"))},
        timeout=timeout, media_write=True,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, len(ids))


def send_publication(token: str, chat_id: str, caption: str, media_urls: list[str], *, source_url: str = "", source_urls: list[str] | tuple[str, ...] | None = None, timeout: float = 45.0) -> TelegramResult:
    """Publish one photo/video with the normal <=900 character caption contract."""
    token = token.strip(); chat_id = normalize_chat_target(chat_id); caption = caption.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if len(caption) > 900:
        raise TelegramError("Telegram-пост перевищує ліміт 900 символів.", retryable=False)
    selected: tuple[str, str] | None = None
    items = _valid_media_items(media_urls)
    if items:
        selected = items[0]
    if selected is None:
        return send_text(token, chat_id, caption, source_url=source_url, timeout=timeout)
    kind, url = selected
    method = "sendVideo" if kind == "video" else "sendPhoto"
    field = "video" if kind == "video" else "photo"
    result = _request(
        token, method,
        {
            "chat_id": chat_id, field: url, "caption": caption,
            # Telegram's default is caption below the media. Keep the <=900-char
            # text and source attribution attached to this media post.
            **({"caption_entities": _source_link_entities(caption, source_url, source_urls)} if _source_link_entities(caption, source_url, source_urls) else {}),
        },
        timeout=timeout, media_write=True,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)


def _safe_media_filename(url: str, mime_type: str, kind: str, index: int = 0) -> str:
    try:
        raw = unquote(urlsplit(url).path.rsplit("/", 1)[-1]).strip()
    except Exception:
        raw = ""
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:96].strip("._")
    if not raw:
        raw = f"media_{index + 1}"
    suffix = ""
    try:
        suffix = urlsplit(url).path.rsplit("/", 1)[-1]
        suffix = "." + suffix.rsplit(".", 1)[-1].lower() if "." in suffix else ""
    except Exception:
        suffix = ""
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".m4v", ".mov", ".webm"}
    if suffix not in valid_exts or not raw.lower().endswith(suffix):
        guessed = mimetypes.guess_extension(mime_type or "") or (".mp4" if kind == "video" else ".jpg")
        if guessed == ".jpe":
            guessed = ".jpg"
        if "." not in raw.rsplit("/", 1)[-1]:
            raw += guessed
    return raw[:120]


def prepare_telegram_media(media_value: str, *, timeout: float = 35.0, index: int = 0) -> PreparedTelegramMedia:
    """Fetch one source media object locally and validate it for Telegram upload."""
    parsed = valid_public_media(str(media_value or ""))
    if not parsed:
        raise TelegramError("Невалідне медіа URL.", retryable=False, media_rejected=True)
    kind, url = parsed
    if kind not in {"image", "video"}:
        raise TelegramError("Непідтримуваний тип медіа.", retryable=False, media_rejected=True)
    max_bytes = 9_500_000 if kind == "image" else 45_000_000
    try:
        response = fetch_url(
            url,
            headers=_MEDIA_DOWNLOAD_HEADERS,
            timeout=max(8.0, float(timeout)),
            max_bytes=max_bytes,
            max_redirects=5,
            allow_http_errors=True,
        )
    except NetworkError as exc:
        raise TelegramError(f"Не вдалося завантажити медіа: {exc}", retryable=True, media_rejected=True) from exc
    if response.status >= 400:
        # 4xx is normally a stable hotlink/access restriction, but a later source
        # refresh can replace the URL. Backoff is handled by the publisher.
        raise TelegramError(
            f"Джерело медіа повернуло HTTP {response.status}.",
            retryable=response.status in {408, 425, 429} or response.status >= 500,
            media_rejected=True,
        )
    data = bytes(response.body or b"")
    if not data:
        raise TelegramError("Джерело медіа повернуло порожній файл.", retryable=False, media_rejected=True)
    mime = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if kind == "image":
        if not mime.startswith("image/"):
            raise TelegramError(f"Медіа не є зображенням: {mime or 'unknown content-type'}.", retryable=False, media_rejected=True)
        if len(data) > 9_500_000:
            raise TelegramError("Зображення завелике для Telegram upload.", retryable=False, media_rejected=True)
    else:
        if not mime.startswith("video/"):
            # Some CDNs incorrectly return octet-stream for direct MP4 files.
            path = urlsplit(response.final_url or url).path.casefold()
            if not (mime in {"application/octet-stream", "binary/octet-stream", ""} and path.endswith((".mp4", ".m4v", ".mov", ".webm"))):
                raise TelegramError(f"Медіа не є відео: {mime or 'unknown content-type'}.", retryable=False, media_rejected=True)
            mime = mimetypes.guess_type(path)[0] or "video/mp4"
        if len(data) > 45_000_000:
            raise TelegramError("Відео завелике для безпечного Telegram upload.", retryable=False, media_rejected=True)
    digest = hashlib.sha256(data).hexdigest()
    return PreparedTelegramMedia(
        kind=kind,
        source_url=url,
        filename=_safe_media_filename(response.final_url or url, mime, kind, index=index),
        mime_type=mime or ("video/mp4" if kind == "video" else "image/jpeg"),
        data=data,
        digest=digest,
    )


def prepare_telegram_media_list(media_values: list[str] | tuple[str, ...], *, timeout: float = 35.0) -> tuple[list[PreparedTelegramMedia], list[tuple[str, TelegramError]]]:
    """Download source media in order and dedupe exact binary duplicates."""
    prepared: list[PreparedTelegramMedia] = []
    failures: list[tuple[str, TelegramError]] = []
    seen_digest: set[str] = set()
    for index, value in enumerate(media_values):
        try:
            item = prepare_telegram_media(str(value or ""), timeout=timeout, index=index)
        except TelegramError as exc:
            failures.append((str(value or ""), exc))
            continue
        if item.digest in seen_digest:
            continue
        seen_digest.add(item.digest)
        prepared.append(item)
    return prepared, failures


def _multipart_body_files(fields: dict[str, str], files: list[tuple[str, str, str, bytes]]) -> tuple[str, bytes]:
    import secrets
    boundary = "----UAFreeAutopilot" + secrets.token_hex(12)
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    for field_name, filename, mime_type, data in files:
        safe_field = re.sub(r"[^A-Za-z0-9_-]+", "_", field_name)[:64] or "file"
        safe_name = str(filename or "media.bin").replace('"', "_").replace("\r", "_").replace("\n", "_")[:120]
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{safe_field}\"; filename=\"{safe_name}\"\r\n"
            f"Content-Type: {mime_type or 'application/octet-stream'}\r\n\r\n".encode("utf-8")
        )
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return boundary, b"".join(chunks)


def _request_files(
    token: str,
    method: str,
    fields: dict[str, str],
    files: list[tuple[str, str, str, bytes]],
    *,
    timeout: float = 75.0,
) -> object:
    boundary, body = _multipart_body_files(fields, files)
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


def send_prepared_publication(
    token: str,
    chat_id: str,
    caption: str,
    media: PreparedTelegramMedia,
    *,
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    timeout: float = 75.0,
) -> TelegramResult:
    """Upload one locally fetched media object with the <=900-char caption."""
    token = token.strip(); chat_id = normalize_chat_target(chat_id); caption = caption.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if len(caption) > 900:
        raise TelegramError("Telegram-пост перевищує ліміт 900 символів.", retryable=False)
    method = "sendVideo" if media.kind == "video" else "sendPhoto"
    field = "video" if media.kind == "video" else "photo"
    fields = {"chat_id": chat_id, "caption": caption}
    entities = _source_link_entities(caption, source_url, source_urls)
    if entities:
        fields["caption_entities"] = entities
    result = _request_files(
        token, method, fields,
        [(field, media.filename, media.mime_type, media.data)],
        timeout=timeout,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)


def send_prepared_media_only(token: str, chat_id: str, media: PreparedTelegramMedia, *, timeout: float = 75.0) -> TelegramResult:
    token = token.strip(); chat_id = normalize_chat_target(chat_id)
    method = "sendVideo" if media.kind == "video" else "sendPhoto"
    field = "video" if media.kind == "video" else "photo"
    result = _request_files(
        token, method, {"chat_id": chat_id},
        [(field, media.filename, media.mime_type, media.data)],
        timeout=timeout,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)


def send_prepared_media_group(
    token: str,
    chat_id: str,
    media_items: list[PreparedTelegramMedia] | tuple[PreparedTelegramMedia, ...],
    *,
    caption: str = "",
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    timeout: float = 90.0,
) -> TelegramResult:
    """Upload 2..10 local files as one Bot API media group."""
    token = token.strip(); chat_id = normalize_chat_target(chat_id)
    items = list(media_items)
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if not (2 <= len(items) <= 10):
        raise TelegramError("Для media group потрібно 2..10 медіа.", retryable=False, media_rejected=True)
    if caption and len(caption) > 900:
        raise TelegramError("Telegram caption media group перевищує 900 символів.", retryable=False)
    entities = _source_link_entities(caption, source_url, source_urls) if caption else ""
    media_json: list[dict[str, object]] = []
    files: list[tuple[str, str, str, bytes]] = []
    for idx, item in enumerate(items):
        attach = f"media{idx}"
        row: dict[str, object] = {"type": "video" if item.kind == "video" else "photo", "media": f"attach://{attach}"}
        if idx == 0 and caption:
            row["caption"] = caption
            if entities:
                row["caption_entities"] = json.loads(entities)
        media_json.append(row)
        files.append((attach, item.filename, item.mime_type, item.data))
    result = _request_files(
        token,
        "sendMediaGroup",
        {"chat_id": chat_id, "media": json.dumps(media_json, ensure_ascii=False, separators=(",", ":"))},
        files,
        timeout=timeout,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, len(ids))


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
