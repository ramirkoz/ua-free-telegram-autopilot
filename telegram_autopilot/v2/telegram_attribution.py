from __future__ import annotations

import json

from ..telegram import (
    PreparedTelegramMedia,
    TelegramError,
    TelegramResult,
    _normalize_source_urls,
    _request,
    _request_files,
    _result_ids,
    _technical_code_entities,
    _utf16_units,
    build_post_text,
    normalize_chat_target,
    send_prepared_media_group,
    send_prepared_publication,
    send_text,
)


def _normalized_labels(urls: list[str], source_labels: list[str] | tuple[str, ...] | None) -> list[str]:
    provided = [" ".join(str(label or "").split()).strip() for label in list(source_labels or [])]
    labels: list[str] = []
    for idx in range(len(urls)):
        label = provided[idx] if idx < len(provided) else ""
        if not label:
            label = "Джерело" if len(urls) == 1 else f"Джерело {idx + 1}"
        labels.append(label)
    return labels


def build_attributed_post_text(
    text: str,
    *,
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    source_labels: list[str] | tuple[str, ...] | None = None,
    include_source_link: bool = True,
    hard_limit: int = 900,
) -> str:
    """Build the normal footer, with optional operator-defined clickable labels."""
    if not source_labels:
        return build_post_text(
            text,
            source_url=source_url,
            source_urls=source_urls,
            include_source_link=include_source_link,
            hard_limit=hard_limit,
        )
    clean = build_post_text(text, include_source_link=False, hard_limit=hard_limit)
    urls = _normalize_source_urls(source_url, source_urls)
    if include_source_link and urls:
        labels = _normalized_labels(urls, source_labels)
        clean += "\n\n" + "\n".join(labels)
    if len(clean) > hard_limit:
        raise TelegramError(f"Telegram-пост перевищує ліміт {hard_limit} символів.", retryable=False)
    return clean


def _attribution_entities(
    text: str,
    source_url: str,
    source_urls: list[str] | tuple[str, ...] | None,
    source_labels: list[str] | tuple[str, ...] | None,
) -> str:
    urls = _normalize_source_urls(source_url, source_urls)
    labels = _normalized_labels(urls, source_labels)
    value = str(text or "")
    entities: list[dict[str, object]] = list(_technical_code_entities(value))
    for label, url in zip(labels, urls):
        start = value.rfind(label)
        if start < 0:
            continue
        entities.append(
            {
                "type": "text_link",
                "offset": _utf16_units(value[:start]),
                "length": _utf16_units(label),
                "url": url,
            }
        )
    entities.sort(key=lambda item: (int(item.get("offset") or 0), int(item.get("length") or 0)))
    return json.dumps(entities, ensure_ascii=False, separators=(",", ":")) if entities else ""


def send_text_attributed(
    token: str,
    chat_id: str,
    text: str,
    *,
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    source_labels: list[str] | tuple[str, ...] | None = None,
    timeout: float = 45.0,
) -> TelegramResult:
    if not source_labels:
        return send_text(
            token, chat_id, text, source_url=source_url, source_urls=source_urls, timeout=timeout
        )
    token = token.strip()
    chat_id = normalize_chat_target(chat_id)
    text = text.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if not text:
        raise TelegramError("Порожній Telegram текст.", retryable=False)
    if len(text) > 4096:
        raise TelegramError("Telegram текст перевищує 4096 символів.", retryable=False)
    fields = {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    entities = _attribution_entities(text, source_url, source_urls, source_labels)
    if entities:
        fields["entities"] = entities
    result = _request(token, "sendMessage", fields, timeout=timeout)
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 0)


def send_prepared_publication_attributed(
    token: str,
    chat_id: str,
    caption: str,
    media: PreparedTelegramMedia,
    *,
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    source_labels: list[str] | tuple[str, ...] | None = None,
    timeout: float = 75.0,
) -> TelegramResult:
    if not source_labels:
        return send_prepared_publication(
            token,
            chat_id,
            caption,
            media,
            source_url=source_url,
            source_urls=source_urls,
            timeout=timeout,
        )
    token = token.strip()
    chat_id = normalize_chat_target(chat_id)
    caption = caption.strip()
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if len(caption) > 900:
        raise TelegramError("Telegram-пост перевищує ліміт 900 символів.", retryable=False)
    method = "sendVideo" if media.kind == "video" else "sendPhoto"
    field = "video" if media.kind == "video" else "photo"
    fields = {"chat_id": chat_id, "caption": caption}
    entities = _attribution_entities(caption, source_url, source_urls, source_labels)
    if entities:
        fields["caption_entities"] = entities
    result = _request_files(
        token,
        method,
        fields,
        [(field, media.filename, media.mime_type, media.data)],
        timeout=timeout,
    )
    ids = _result_ids(result)
    return TelegramResult(ids[0], ids, 1)


def send_prepared_media_group_attributed(
    token: str,
    chat_id: str,
    media_items: list[PreparedTelegramMedia] | tuple[PreparedTelegramMedia, ...],
    *,
    caption: str = "",
    source_url: str = "",
    source_urls: list[str] | tuple[str, ...] | None = None,
    source_labels: list[str] | tuple[str, ...] | None = None,
    timeout: float = 90.0,
) -> TelegramResult:
    if not source_labels:
        return send_prepared_media_group(
            token,
            chat_id,
            media_items,
            caption=caption,
            source_url=source_url,
            source_urls=source_urls,
            timeout=timeout,
        )
    token = token.strip()
    chat_id = normalize_chat_target(chat_id)
    items = list(media_items)
    if not token or not chat_id:
        raise TelegramError("Telegram bot token або Chat ID не налаштовано.", retryable=False)
    if not (2 <= len(items) <= 10):
        raise TelegramError("Для media group потрібно 2..10 медіа.", retryable=False, media_rejected=True)
    if caption and len(caption) > 900:
        raise TelegramError("Telegram caption media group перевищує 900 символів.", retryable=False)
    entities = _attribution_entities(caption, source_url, source_urls, source_labels) if caption else ""
    media_json: list[dict[str, object]] = []
    files: list[tuple[str, str, str, bytes]] = []
    for idx, item in enumerate(items):
        attach = f"media{idx}"
        row: dict[str, object] = {
            "type": "video" if item.kind == "video" else "photo",
            "media": f"attach://{attach}",
        }
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
