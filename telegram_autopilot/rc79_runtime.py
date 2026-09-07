from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Mapping

LOG = logging.getLogger("telegram_autopilot.rc79")
_INSTALLED = False
_PREV: dict[str, Any] = {}
_CTX = threading.local()

_RC79_SENTINEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdac\xf8\xcf"
    b"\x00\x00\x02\x05\x01\x02'\r\xe0B\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _clean(value: Any, limit: int = 12000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _json_layout(value: Any) -> dict[str, Any]:
    try:
        obj = json.loads(str(value or "") or "{}")
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _telegram_meta(row: Any) -> dict[str, Any]:
    layout = _json_layout(_v(row, "article_layout_json", ""))
    tg = layout.get("telegram")
    return tg if isinstance(tg, dict) else {}


@dataclass(slots=True)
class _TelegramEntry:
    post: str
    text: str
    published: str | None
    media: list[str] = field(default_factory=list)
    forwarded: bool = False
    forwarded_from: str = ""


class _TelegramRC79Parser(HTMLParser):
    """Public Telegram HTML parser that keeps forwards and media-only messages."""

    def __init__(self, username: str) -> None:
        super().__init__(convert_charrefs=True)
        self.username = username
        self.depth = 0
        self.message_depth: int | None = None
        self.text_depth: int | None = None
        self.forward_depth: int | None = None
        self.current: dict[str, Any] | None = None
        self.entries: list[_TelegramEntry] = []

    @staticmethod
    def _classes(attrs: dict[str, str]) -> set[str]:
        return {item for item in attrs.get("class", "").split() if item}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        from .media import encode_media

        self.depth += 1
        values = {str(k).casefold(): str(v or "") for k, v in attrs}
        classes = self._classes(values)
        if tag.casefold() == "div" and "tgme_widget_message" in classes and values.get("data-post"):
            self._finish_current()
            self.current = {
                "post": values["data-post"], "text": [], "published": None, "media": [],
                "forwarded": False, "forward_parts": [],
            }
            self.message_depth = self.depth
        if self.current is None:
            return

        if "tgme_widget_message_text" in classes:
            self.text_depth = self.depth

        if any("forwarded" in c.casefold() for c in classes):
            self.current["forwarded"] = True
            if self.forward_depth is None:
                self.forward_depth = self.depth

        if bool(self.current.get("forwarded")):
            origin = values.get("title") or values.get("data-peer") or ""
            if origin:
                self.current["forward_parts"].append(origin)

        if tag.casefold() == "time" and values.get("datetime"):
            self.current["published"] = values["datetime"]

        media = self.current["media"]
        if tag.casefold() == "img" and values.get("src"):
            encoded = encode_media("image", values["src"])
            if encoded not in media:
                media.append(encoded[:3020])
        if tag.casefold() in {"video", "source"} and values.get("src"):
            encoded = encode_media("video", values["src"])
            if encoded not in media:
                media.append(encoded[:3020])
        style = values.get("style", "")
        if style:
            match = re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)", style, flags=re.I)
            if match:
                encoded = encode_media("image", match.group(1))
                if encoded not in media:
                    media.append(encoded[:3020])

    def handle_data(self, data: str) -> None:
        if self.current is None:
            return
        if self.text_depth is not None and self.depth >= self.text_depth:
            self.current["text"].append(data)
        if self.forward_depth is not None and self.depth >= self.forward_depth:
            self.current["forward_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is not None and self.text_depth == self.depth:
            self.text_depth = None
        if self.current is not None and self.forward_depth == self.depth:
            self.forward_depth = None
        if self.current is not None and self.message_depth == self.depth and tag.casefold() == "div":
            self._finish_current()
        self.depth = max(0, self.depth - 1)

    def close(self) -> None:
        super().close()
        self._finish_current()

    def _finish_current(self) -> None:
        if not self.current:
            return
        post = str(self.current.get("post") or "").strip()
        text = " ".join("".join(self.current.get("text") or []).split())
        media = list(dict.fromkeys(self.current.get("media") or []))[:24]
        forwarded_from = " ".join(" ".join(self.current.get("forward_parts") or []).split())[:500]
        if post and (text or media):
            self.entries.append(_TelegramEntry(
                post=post,
                text=text,
                published=str(self.current.get("published") or "") or None,
                media=media,
                forwarded=bool(self.current.get("forwarded")),
                forwarded_from=forwarded_from,
            ))
        self.current = None
        self.message_depth = self.text_depth = self.forward_depth = None


def _post_number(post: str) -> int | None:
    try:
        tail = str(post or "").rsplit("/", 1)[-1]
        return int(tail) if tail.isdigit() else None
    except Exception:
        return None


def _entry_dt(entry: _TelegramEntry) -> datetime | None:
    try:
        value = str(entry.published or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _adjacent(a: _TelegramEntry, b: _TelegramEntry, *, seconds: int = 120) -> bool:
    ai, bi = _post_number(a.post), _post_number(b.post)
    if ai is not None and bi is not None and bi != ai + 1:
        return False
    adt, bdt = _entry_dt(a), _entry_dt(b)
    if adt is not None and bdt is not None:
        delta = (bdt - adt).total_seconds()
        return 0 <= delta <= seconds
    return ai is not None and bi is not None and bi == ai + 1


def _held_for_possible_media(entry: _TelegramEntry, *, now: datetime | None = None) -> bool:
    if entry.media or not entry.text:
        return False
    dt = _entry_dt(entry)
    if dt is None:
        return False
    current = now or datetime.now(timezone.utc)
    return 0 <= (current - dt).total_seconds() <= 100


def _layout_for_telegram(
    username: str,
    text: str,
    entries: list[_TelegramEntry],
    media: list[str],
) -> str:
    from .media import decode_media

    blocks: list[dict[str, Any]] = []
    context = ("Telegram media attached to this source message. " + text[:700]).strip()
    for idx, encoded in enumerate(media[:10], 1):
        try:
            kind, url = decode_media(encoded)
        except Exception:
            continue
        if kind not in {"image", "video"} or not url:
            continue
        blocks.append({
            "type": "media", "index": idx, "kind": kind, "url": url,
            "caption": "", "alt": "", "context": context,
            "position": min(0.35, 0.03 + idx * 0.02),
        })
    message_ids = [str(_post_number(e.post) or e.post.rsplit("/", 1)[-1]) for e in entries]
    forwarded_from = " | ".join(dict.fromkeys(
        x.forwarded_from for x in entries if x.forwarded_from
    ))[:800]
    return json.dumps({
        "version": 79,
        "source_kind": "telegram",
        "telegram": {
            "source_username": username,
            "message_ids": message_ids,
            "forwarded": any(e.forwarded for e in entries),
            "forwarded_from": forwarded_from,
            "stitched": len(entries) > 1,
            "media_count": len(media),
        },
        "blocks": blocks,
    }, ensure_ascii=False, separators=(",", ":"))


def _entry_to_article(username: str, primary: _TelegramEntry, attached: list[_TelegramEntry]):
    from .models import CollectedArticle

    group = [primary, *attached]
    media: list[str] = []
    for entry in group:
        for item in entry.media:
            if item not in media:
                media.append(item)
    title = primary.text[:220] + ("…" if len(primary.text) > 220 else "")
    url = "https://t.me/" + primary.post
    return CollectedArticle(
        primary.post[:1000],
        title or "Telegram",
        url,
        primary.text,
        primary.published,
        media[:24],
        _layout_for_telegram(username, primary.text, group, media),
    )


def _stitch_telegram_entries(
    username: str,
    entries: list[_TelegramEntry],
    *,
    now: datetime | None = None,
) -> list[Any]:
    """Turn physical Telegram messages into human-visible logical posts."""

    result: list[Any] = []
    i = 0
    while i < len(entries):
        current = entries[i]

        if not current.text and current.media:
            run = [current]
            j = i + 1
            while j < len(entries) and not entries[j].text and entries[j].media and _adjacent(run[-1], entries[j]):
                run.append(entries[j])
                j += 1
            if j < len(entries) and entries[j].text and _adjacent(run[-1], entries[j]):
                primary = entries[j]
                attached = run[:]
                k = j + 1
                while k < len(entries) and not entries[k].text and entries[k].media and _adjacent(entries[k - 1], entries[k]):
                    attached.append(entries[k])
                    k += 1
                result.append(_entry_to_article(username, primary, attached))
                i = k
                continue
            i = j
            continue

        if current.text:
            attached: list[_TelegramEntry] = []
            j = i + 1
            previous = current
            while j < len(entries) and not entries[j].text and entries[j].media and _adjacent(previous, entries[j]):
                attached.append(entries[j])
                previous = entries[j]
                j += 1

            if not current.media and not attached and j >= len(entries) and _held_for_possible_media(current, now=now):
                i = j
                continue

            result.append(_entry_to_article(username, current, attached))
            i = j
            continue

        i += 1
    return result


def _collect_telegram_rc79(source: Any):
    from . import collector

    username = collector._telegram_username(source.url)
    if not username:
        raise collector.CollectorError("Telegram-джерело має містити публічну адресу t.me/username.")
    response = collector._source_fetch(
        f"https://t.me/s/{username}",
        max_bytes=8 * 1024 * 1024,
        allowed_content_types={"text/html", "application/xhtml+xml"},
        timeout=35,
    )
    parser = _TelegramRC79Parser(username)
    parser.feed(response.body.decode("utf-8", errors="replace"))
    parser.close()
    items = _stitch_telegram_entries(username, parser.entries)
    if not items:
        raise collector.CollectorError("Не вдалося прочитати публікації Telegram-каналу. Перевірте, що канал публічний.")
    return items[-40:]


def _policy(service_or_db: Any, channel_id: int):
    db = getattr(service_or_db, "db", service_or_db)
    try:
        return db.rc59_get_channel_policy(int(channel_id))
    except Exception:
        from . import rc59_universal_policy as rc59
        channel = db.get_channel(int(channel_id)) if hasattr(db, "get_channel") else None
        return rc59.default_policy(channel)


def _policy_media(policy: Any) -> str:
    value = str(getattr(policy, "media_policy", "required") or "required").casefold()
    return value if value in {"required", "preferred", "optional"} else "required"


def _rule_mentions(rules: str, *tokens: str) -> bool:
    low = str(rules or "").casefold()
    return any(token.casefold() in low for token in tokens)


def _configured_local_monitoring_exclusion(policy: Any, article: Any) -> str:
    """Only deterministic exclusions explicitly configured in this channel."""

    rules = str(getattr(policy, "rejection_rules", "") or "")
    if not rules.strip():
        return ""
    low = (str(_v(article, "title", "")) + "\n" + str(_v(article, "raw_text", ""))).casefold()
    meta = _telegram_meta(article)

    if bool(meta.get("forwarded")) and _rule_mentions(rules, "репост", "переслан", "forward"):
        origin = _clean(meta.get("forwarded_from"), 160)
        return "Нативний Telegram-репост/переслане повідомлення" + (f" ({origin})" if origin else "")

    if _rule_mentions(rules, "хвилин", "мовчан", "пошан") and (
        "хвилина мовчання" in low or "хвилин" in low and ("мовчан" in low or "пошан" in low)
    ):
        return "Хвилина мовчання/пошани — явне exclusion rule каналу"

    if _rule_mentions(rules, "тривог", "відбій", "летить", "повітря") and any(
        re.search(pattern, low, re.I) for pattern in (
            r"\bповітрян\w*\s+тривог", r"\bвідбій\b.*\bтривог", r"\bтривог\w*\s+скас",
            r"\b(бпла|ракета|шахед\w*)\b.*\b(летить|рухаєть|курс\w*)",
            r"\b(летить|рухаєть)\b.*\b(бпла|ракета|шахед\w*)",
        )
    ):
        return "Оперативне повідомлення про тривогу/відбій/рух повітряної загрози"

    if _rule_mentions(rules, "привітан", "календар", "свят", "пам'ятн", "пам’ятн") and any(
        token in low for token in ("вітаємо", "привітав", "привітала", "привітали", "щиро віта", "з нагоди", "побажав", "побажала")
    ):
        return "Протокольне/календарне привітання без окремої інформаційної події"

    if _rule_mentions(rules, "настр", "побажан", "гарного дня", "без поді", "мотивац") and any(
        token in low for token in (
            "гарного дня", "вдалого дня", "вдалого тижня", "спокійного ранку",
            "доброго ранку", "хорошого настрою", "нехай усе", "нехай все",
            "маленьких приводів", "настрій на день",
        )
    ):
        return "Побажання/пост настрою без інформаційної події"

    return ""


def _monitoring_selector_rc79(policy: Any, article: Any, *, channel_id: int):
    reason = _configured_local_monitoring_exclusion(policy, article)
    if reason:
        from .ai_router import Result
        result = Result("monitoring-local-reject", "local-rule", "rc79-monitoring-local", "RC79 deterministic exclusion")
        return result, {
            "decision": "reject", "fit_score": 0,
            "reason": "RC79 MONITORING_LOCAL_REJECT: " + reason,
            "angle": "", "topic_tags": [],
        }
    return _PREV["monitoring_selector"](policy, article, channel_id=int(channel_id))


def _extract_actionable_facts(article: Any) -> list[str]:
    raw = str(_v(article, "raw_text", "") or "")
    title = str(_v(article, "title", "") or "")
    source = title + "\n" + raw
    out: list[str] = []

    def add(label: str, value: str) -> None:
        value = " ".join(str(value or "").split()).strip(" ,;")
        item = f"{label}: {value}" if value else ""
        if item and item not in out:
            out.append(item[:420])

    for url in re.findall(r"https?://[^\s<>()\]\[{}\"']+", source, flags=re.I):
        add("URL", url.rstrip(".,;:!?"))
    for email in re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", source, flags=re.I):
        add("EMAIL", email)
    for phone in re.findall(r"(?<!\d)(?:\+?\d[\d\s()\-]{7,}\d)(?!\d)", source):
        digits = re.sub(r"\D", "", phone)
        if 8 <= len(digits) <= 15:
            add("ТЕЛЕФОН", phone)

    for line in [x.strip() for x in raw.splitlines() if x.strip()]:
        low = line.casefold()
        if any(token in low for token in (
            "адрес", "вул.", "вулиц", "просп.", "проспект", "зупинка",
            "графік", "працює", "прийом", "реєстрац", "дедлайн", "до ", "о ",
        )) and (re.search(r"\d", line) or "адрес" in low or "реєстрац" in low):
            add("ПРАКТИЧНА ДЕТАЛЬ", line)

    return out[:20]


def _writer_prompt_rc79(policy: Any, channel: Any, article: Any, selector: dict[str, Any], *, hard_limit: int) -> str:
    base = _PREV["writer_prompt"](policy, channel, article, selector, hard_limit=hard_limit)
    facts = _extract_actionable_facts(article)
    if not facts:
        return base
    return base + """

RC79 PROTECTED ACTIONABLE FACTS:
Нижче автоматично витягнуті точні практичні дані SOURCE. Це не додаткові факти.
Якщо CHANNEL POLICY вимагає зберігати контакти/адреси/дати/час/умови/посилання, не викидай релевантні читачеві значення і не змінюй їх.
Телефон та URL копіюй дослівно й повністю; не скорочуй URL до фрагмента.
Не вставляй значення, яке не потрібне для змісту поста лише тому, що воно є в цьому блоці.

""" + "\n".join("- " + item for item in facts)


def _policy_value_allowed(data: Mapping[str, Any], fit_score: int) -> tuple[bool, str, int]:
    from . import rc68_editorial_value as rc68

    allowed, code, score = _PREV["value_allowed"](data)
    if allowed:
        return allowed, code, score

    if int(fit_score) < 60:
        return False, code, score
    mechanism = rc68._score(data.get("mechanism"))
    insight = rc68._score(data.get("consequence_or_insight"))
    payoff = rc68._score(data.get("reader_payoff"))
    retell = rc68._score(data.get("retellability"))
    novelty = rc68._score(data.get("novelty"))

    if score >= 48 and mechanism >= 60 and payoff >= 55 and retell >= 50:
        return True, "policy_fit_mechanism_lane", score
    if score >= 48 and insight >= 62 and payoff >= 55 and retell >= 48:
        return True, "policy_fit_insight_lane", score
    if score >= 50 and novelty >= 65 and payoff >= 55 and retell >= 58:
        return True, "policy_fit_creative_lane", score
    return False, code, score


def _run_selector_rc79(policy: Any, article: Any, *, channel_id: int = 0):
    from . import rc68_editorial_value as rc68

    if rc68._monitoring(int(channel_id or 0)):
        return rc68._monitoring_selector(policy, article, channel_id=int(channel_id or 0))

    fit_result, fit = rc68._run_channel_fit(policy, article, channel_id=int(channel_id or 0))
    data = dict(fit)
    if str(data.get("decision") or "") != "publish":
        LOG.info(
            "RC79 CHANNEL_FIT_REJECT channel_id=%s article_id=%s fit=%s reason=%s",
            channel_id, _v(article, "id", "?"), data.get("fit_score", 0), _clean(data.get("reason"), 500),
        )
        return fit_result, data

    value, _old_allowed, old_code, score, value_result = rc68._run_value_gate(article)
    allowed, code, score = _policy_value_allowed(value, int(data.get("fit_score", 0) or 0))
    try:
        rc68._save_value(article, value, allowed, code, score)
    except Exception:
        pass
    data["editorial_value_score"] = score
    data["editorial_value_reason"] = _clean(value.get("reason"), 500)
    if not allowed:
        data["decision"] = "reject"
        data["angle"] = ""
        data["reason"] = (
            f"RC79 EDITORIAL_VALUE_REJECT score={score}; code={code}; "
            f"payoff={rc68._score(value.get('reader_payoff'))}; retell={rc68._score(value.get('retellability'))}; "
            f"insight={rc68._score(value.get('consequence_or_insight'))}; mechanism={rc68._score(value.get('mechanism'))}; "
            f"why_now={rc68._score(value.get('why_now'))}. " + _clean(value.get("reason"), 420)
        )
        LOG.info("RC79 EDITORIAL_VALUE_REJECT channel_id=%s article_id=%s %s", channel_id, _v(article, "id", "?"), data["reason"])
        return value_result or fit_result, data

    data["reason"] = (
        f"RC79 EDITORIAL_VALUE_PASS score={score}; lane={code}; fit={int(data.get('fit_score', 0) or 0)}. "
        + _clean(data.get("reason"), 320)
    )
    LOG.info(
        "RC79 EDITORIAL_VALUE_PASS channel_id=%s article_id=%s score=%s lane=%s",
        channel_id, _v(article, "id", "?"), score, code,
    )
    return value_result or fit_result, data


def _is_telegram_layout(layout_json: str) -> bool:
    return str(_json_layout(layout_json).get("source_kind") or "").casefold() == "telegram"


def _has_valid_donor_media(media_urls: list[str]) -> bool:
    from .media import valid_public_media
    return any(valid_public_media(str(item)) is not None for item in media_urls)


def _deferred_media_rc79():
    from .media_pipeline import PreparedArticleMedia, PreparedMedia

    item = PreparedMedia(
        index=-7900, kind="image", url="https://rc79.invalid/deferred-media.png",
        caption="RC79 deferred media", alt="RC79 deferred media", position=0.0,
        featured=True, mime_type="image/png", width=1, height=1,
        digest="rc79-deferred", data=_RC79_SENTINEL_PNG,
        context="internal deferred media sentinel", classification="photo", relevance_score=100.0,
    )
    return PreparedArticleMedia(featured=item, body=[])


def _has_publishable_media(value: Any) -> bool:
    return bool(getattr(value, "telegram_hero", None) is not None or getattr(value, "telegram_direct_video", None) is not None)


def _prepare_media_rc79(
    layout_json: str,
    media_urls: list[str],
    *,
    title: str = "",
    article_text: str = "",
    marketing_context: bool = False,
):
    current = _PREV["prepare_media"](
        layout_json, media_urls, title=title, article_text=article_text, marketing_context=marketing_context
    )
    if _has_publishable_media(current):
        return current

    try:
        from . import rc71_editorial_pipeline as rc71
        service, channel, row = rc71._context_article()
    except Exception:
        service = channel = row = None
    if channel is None or service is None:
        return current

    policy = _policy(service, int(channel.id))
    media_policy = _policy_media(policy)
    exact_telegram_media = _is_telegram_layout(layout_json) and _has_valid_donor_media(media_urls)

    if exact_telegram_media or media_policy in {"preferred", "optional"}:
        return _deferred_media_rc79()
    return current


def _caption_with_sources(body: str, urls: list[str], *, video_link: str = "", hard_limit: int = 900) -> tuple[str, list[dict[str, Any]]]:
    from .telegram import _utf16_units

    clean_body = str(body or "").strip()
    if video_link:
        clean_body += "\n\n🎬 Відео: " + str(video_link).strip()
    clean_urls = [u for u in dict.fromkeys(str(x or "").strip() for x in urls) if u]
    if not clean_urls:
        if len(clean_body) > hard_limit:
            clean_body = clean_body[:hard_limit].rstrip()
        return clean_body, []

    labels = ["Джерело"] if len(clean_urls) == 1 else [f"Джерело {i}" for i in range(1, len(clean_urls) + 1)]
    footer = "\n\n" + " · ".join(labels)
    allowance = hard_limit - len(footer)
    if allowance < 180:
        raise RuntimeError("RC79 source footer leaves too little space for Telegram text")
    if len(clean_body) > allowance:
        trimmed = clean_body[:allowance].rstrip()
        cut = max(trimmed.rfind(". "), trimmed.rfind("! "), trimmed.rfind("? "), trimmed.rfind("… "))
        clean_body = trimmed[:cut + 1] if cut >= max(120, allowance // 2) else trimmed.rstrip()
    text = clean_body + footer

    entities: list[dict[str, Any]] = []
    search_from = len(clean_body) + 2
    for label, url in zip(labels, clean_urls):
        pos = text.find(label, search_from)
        if pos < 0:
            continue
        entities.append({
            "type": "text_link",
            "offset": _utf16_units(text[:pos]),
            "length": _utf16_units(label),
            "url": url,
        })
        search_from = pos + len(label)
    return text, entities


def _entities_json(entities: list[dict[str, Any]]) -> str:
    return json.dumps(entities, ensure_ascii=False, separators=(",", ":")) if entities else ""


def _send_text_rc79(token: str, chat_id: str, text: str, entities: list[dict[str, Any]]):
    from . import telegram as tg

    token = token.strip()
    chat = tg.normalize_chat_target(chat_id)
    fields = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
    if entities:
        fields["entities"] = _entities_json(entities)
    result = tg._request(token, "sendMessage", fields, timeout=45.0)
    ids = tg._result_ids(result)
    return tg.TelegramResult(ids[0], ids, 0)


def _valid_source_media(media_urls: list[str]) -> list[tuple[str, str]]:
    from .media import valid_public_media

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in media_urls:
        parsed = valid_public_media(str(raw))
        if not parsed:
            continue
        kind, url = parsed
        if kind not in {"image", "video"} or url in seen:
            continue
        seen.add(url)
        out.append((kind, url))
    return out[:10]


def _send_media_group_rc79(token: str, chat_id: str, caption: str, entities: list[dict[str, Any]], items: list[tuple[str, str]]):
    from . import telegram as tg

    if len(items) < 2:
        raise tg.TelegramError("RC79 media group requires at least two media items.", retryable=False, media_rejected=True)
    media: list[dict[str, Any]] = []
    for idx, (kind, url) in enumerate(items[:10]):
        row: dict[str, Any] = {"type": "video" if kind == "video" else "photo", "media": url}
        if idx == 0:
            row["caption"] = caption
            if entities:
                row["caption_entities"] = entities
        media.append(row)
    result = tg._request(
        token, "sendMediaGroup",
        {"chat_id": tg.normalize_chat_target(chat_id), "media": json.dumps(media, ensure_ascii=False, separators=(",", ":"))},
        timeout=60.0, media_write=True,
    )
    ids = tg._result_ids(result)
    return tg.TelegramResult(ids[0], ids, len(ids))


def _send_source_media_one_rc79(token: str, chat_id: str, caption: str, entities: list[dict[str, Any]], item: tuple[str, str]):
    from . import telegram as tg

    kind, url = item
    method = "sendVideo" if kind == "video" else "sendPhoto"
    field = "video" if kind == "video" else "photo"
    fields = {
        "chat_id": tg.normalize_chat_target(chat_id), field: url,
        "caption": caption, "show_caption_above_media": "true",
    }
    if entities:
        fields["caption_entities"] = _entities_json(entities)
    result = tg._request(token, method, fields, timeout=60.0, media_write=True)
    ids = tg._result_ids(result)
    return tg.TelegramResult(ids[0], ids, 1)


def _send_prepared_photo_rc79(token: str, chat_id: str, caption: str, entities: list[dict[str, Any]], hero: Any):
    from . import telegram as tg

    fields = {"chat_id": tg.normalize_chat_target(chat_id), "caption": caption, "show_caption_above_media": "true"}
    if entities:
        fields["caption_entities"] = _entities_json(entities)
    result = tg._request_file(
        token, "sendPhoto", fields,
        file_field="photo", filename=hero.filename, mime_type=hero.mime_type or "image/jpeg",
        data=hero.data, timeout=60.0,
    )
    ids = tg._result_ids(result)
    return tg.TelegramResult(ids[0], ids, 1)


def _send_direct_video_rc79(token: str, chat_id: str, caption: str, entities: list[dict[str, Any]], video: Any):
    return _send_source_media_one_rc79(token, chat_id, caption, entities, ("video", video.url))


def _publish_one_rc79(service: Any, channel: Any, row: Any) -> bool:
    from . import rc66_editorial_queue as rc66
    from . import rc66_clusters as clusters
    from . import service as svc
    from .media_pipeline import prepare_article_media
    from .secrets_store import load_secrets
    from .telegram import TelegramError

    aid = int(_v(row, "id", 0) or 0)
    fresh = service.db.get_article(aid)
    if fresh is None:
        return False
    body = str(_v(fresh, "teaser_text", "") or "").strip()
    issue = rc66.structural_issue(body)
    if issue:
        service.db.schedule_retry(aid, f"RC79 FINAL STRUCTURE BLOCK before Telegram: {issue}")
        service._audit("rc79_final_gate", "retry", issue, channel_id=int(channel.id), article_id=aid)
        return False

    policy = _policy(service, int(channel.id))
    media_policy = _policy_media(policy)
    raw_media = service.db.media_urls(fresh)
    donor_media = _valid_source_media(raw_media) if _is_telegram_layout(service.db.article_layout_json(fresh)) else []

    media = prepare_article_media(
        service.db.article_layout_json(fresh), raw_media,
        title=str(_v(fresh, "title", "")), article_text=str(_v(fresh, "raw_text", "")),
        marketing_context=False,
    )
    urls = clusters.source_urls(service.db, fresh)
    caption, entities = _caption_with_sources(
        body, urls, video_link=str(getattr(media, "video_link", "") or ""),
        hard_limit=svc.MEDIA_POST_HARD_LIMIT,
    )

    secrets = load_secrets()
    token = secrets.channel_bot_tokens.get(str(channel.id), "") or secrets.default_telegram_bot_token
    service.db.update_article(aid, status="telegram_writing", rewrite_text=caption)

    result = None
    media_error = ""
    try:
        if donor_media:
            if len(donor_media) >= 2:
                result = _send_media_group_rc79(token, channel.telegram_chat_id, caption, entities, donor_media)
            else:
                result = _send_source_media_one_rc79(token, channel.telegram_chat_id, caption, entities, donor_media[0])
        elif getattr(media, "telegram_direct_video", None) is not None:
            result = _send_direct_video_rc79(token, channel.telegram_chat_id, caption, entities, media.telegram_direct_video)
        elif getattr(media, "telegram_hero", None) is not None:
            result = _send_prepared_photo_rc79(token, channel.telegram_chat_id, caption, entities, media.telegram_hero)
    except TelegramError as exc:
        media_error = str(exc)
        if media_policy == "required":
            raise
        service._audit("rc79_media", "degraded_to_text", media_error, channel_id=int(channel.id), article_id=aid)
        result = None

    if result is None:
        if media_policy == "required":
            service.db.schedule_retry(aid, "RC79 required media missing or unusable")
            service._audit("rc79_media", "required_missing", "required media unavailable", channel_id=int(channel.id), article_id=aid)
            return False
        result = _send_text_rc79(token, channel.telegram_chat_id, caption, entities)

    rc66._PREV["update_article"](
        service.db, aid,
        status="published",
        published_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        telegram_message_id=result.message_id,
        telegram_media_count=result.media_count,
        retry_count=0, next_retry_at=None, last_error=None, reject_reason=None,
    )
    with service.db.connect() as con:
        con.execute("UPDATE articles SET ready_at=NULL WHERE id=?", (aid,))
    service._audit(
        "telegram", "published",
        f"RC79 READY; message_id={result.message_id}; media={result.media_count}; media_policy={media_policy}; sources={len(urls)}",
        channel_id=int(channel.id), article_id=aid,
    )
    service._emit("publish", f"{channel.name}: опубліковано #{aid} з READY-пулу, Telegram {result.message_id}, медіа {result.media_count}")
    return True


def _strong_event_tokens(value: str) -> set[str]:
    text = str(value or "")
    tokens = set()
    for token in re.findall(r"\b[A-Za-zА-Яа-яІіЇїЄєҐґ]{1,12}[- ]?\d+[A-Za-z0-9-]*\b|\b\d+[A-Za-z]{1,8}\d*\b", text, re.I):
        normalized = re.sub(r"[\s_-]+", "", token).casefold()
        if len(normalized) >= 3:
            tokens.add(normalized)
    return tokens


def _fallback_relation_rc79(current: Any, candidate: Any, a: Any, b: Any) -> tuple[str, str]:
    a_text = str(_v(current, "title", "")) + " " + str(_v(current, "raw_text", ""))[:1600]
    b_text = str(_v(candidate, "title", "")) + " " + str(_v(candidate, "raw_text", ""))[:1600]
    aa, bb = _strong_event_tokens(a_text), _strong_event_tokens(b_text)
    shared = aa & bb
    only_a, only_b = aa - shared, bb - shared
    if shared and only_a and only_b:
        return "RELATED", (
            "RC79 event-anchor guard: спільна тема/версія, але різні сильні event anchors "
            f"A={','.join(sorted(only_a)[:4])}; B={','.join(sorted(only_b)[:4])}"
        )
    return _PREV["fallback_relation"](current, candidate, a, b)


def install_rc79_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import collector
    from . import media_pipeline
    from . import rc59_universal_policy as rc59
    from . import rc66_clusters as clusters
    from . import rc66_editorial_queue as rc66
    from . import rc67_nonblocking_runtime as rc67
    from . import rc68_editorial_value as rc68
    from . import service as svc

    _PREV.update(
        collect_telegram=collector._collect_telegram,
        monitoring_selector=rc68._monitoring_selector,
        writer_prompt=rc59._writer_prompt,
        run_selector=rc59._run_selector,
        value_allowed=rc68.editorial_value_allowed,
        prepare_media=media_pipeline.prepare_article_media,
        publish_one=rc66._publish_one,
        fallback_relation=clusters._fallback_relation,
        core_process=rc67._PREV.get("core_process"),
    )

    collector._collect_telegram = _collect_telegram_rc79

    rc68._monitoring_selector = _monitoring_selector_rc79
    rc59._writer_prompt = _writer_prompt_rc79
    rc59._run_selector = _run_selector_rc79
    rc68._GATE_VERSION = 79

    media_pipeline.prepare_article_media = _prepare_media_rc79
    svc.prepare_article_media = _prepare_media_rc79

    rc66._publish_one = _publish_one_rc79
    clusters._fallback_relation = _fallback_relation_rc79

    LOG.info(
        "RC79 installed: Telegram forward metadata, adjacent-message stitching, donor albums, "
        "config-driven preferred/required/optional media, deterministic monitoring exclusions, "
        "protected actionable facts, compact multi-source links, safer event anchors and multi-shape editorial value"
    )
    _INSTALLED = True
