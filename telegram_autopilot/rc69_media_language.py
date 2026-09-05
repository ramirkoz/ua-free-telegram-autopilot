from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

from .database import content_hash

LOG = logging.getLogger("telegram_autopilot.rc69")
_INSTALLED = False
_PREV: dict[str, Any] = {}

DIRECTION_UK_TO_UK = "uk_to_uk"
DIRECTION_RU_TO_UK = "ru_to_uk"
MEDIA_ENRICH_OFF = "off"
MEDIA_ENRICH_AUTO = "auto"
MEDIA_ENRICH_VALUES = {MEDIA_ENRICH_OFF, MEDIA_ENRICH_AUTO}
MEDIA_MARKER = "[RC69 VERIFIED MEDIA METADATA]"

_RU_ONLY = re.compile(r"[ыэёъ]", re.I)
_RU_WORD = re.compile(r"[А-Яа-яЁёЫыЭэЪъ’'-]+")
_RU_COMMON = {
    "и", "что", "это", "для", "после", "перед", "при", "или", "но", "уже", "еще", "может", "могут",
    "будет", "будут", "был", "была", "были", "его", "ее", "их", "который", "которая", "которые",
    "также", "из", "от", "до", "над", "под", "про", "как", "когда", "где", "если", "чтобы", "только",
}
_UA_SPECIFIC = re.compile(r"[іїєґ]", re.I)


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _clean(value: Any, limit: int = 4000) -> str:
    return " ".join(str(value or "").split())[:limit]


def looks_russian(text: str) -> bool:
    """Conservative Russian prose detector for explicit RU -> UA channels."""
    sample = str(text or "")[:12000]
    words = [word.casefold().strip("’'-") for word in _RU_WORD.findall(sample)]
    if len(words) < 12:
        return False
    hits = sum(1 for word in words if word in _RU_COMMON)
    ru_only = len(_RU_ONLY.findall(sample))
    ua_specific = len(_UA_SPECIFIC.findall(sample))
    if ua_specific >= max(3, ru_only + 2):
        return False
    return hits >= 3 and (ru_only >= 1 or hits >= 6)


def accepts_input(direction: str, text: str) -> bool:
    from .language import looks_english, looks_ukrainian
    from . import rc45_policy as rc45

    value = str(direction or rc45.DIRECTION_EN_TO_UK).casefold()
    if value == DIRECTION_UK_TO_UK:
        return looks_ukrainian(text)
    if value == DIRECTION_RU_TO_UK:
        return looks_russian(text)
    if value == rc45.DIRECTION_UKRU_TO_EN:
        return rc45.looks_ukrainian_or_russian(text)
    return looks_english(text)


def _media_mode(channel: Any) -> str:
    value = str(getattr(channel, "media_enrichment_mode", MEDIA_ENRICH_AUTO) or MEDIA_ENRICH_AUTO).casefold()
    return value if value in MEDIA_ENRICH_VALUES else MEDIA_ENRICH_AUTO


def _media_first_allowed(channel: Any) -> bool:
    return bool(getattr(channel, "media_first_allowed", True))


def _media_threshold(channel: Any) -> int:
    try:
        return max(120, min(4000, int(getattr(channel, "media_min_text_chars", 500) or 500)))
    except Exception:
        return 500


def _without_media_marker(raw: str) -> str:
    value = str(raw or "")
    marker = "\n\n" + MEDIA_MARKER
    return value.split(marker, 1)[0].rstrip() if marker in value else value.rstrip()


def _walk_media_metadata(value: Any, out: list[str], urls: list[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _walk_media_metadata(item, out, urls)
        return
    if not isinstance(value, dict):
        return
    kind = _clean(value.get("kind") or value.get("type"), 80).casefold()
    url = _clean(value.get("url") or value.get("src") or value.get("featured_video"), 3000)
    if url.startswith(("http://", "https://")):
        urls.append(url)
    for label, key in (("MEDIA CAPTION", "caption"), ("MEDIA ALT", "alt"), ("MEDIA CONTEXT", "context")):
        text = _clean(value.get(key), 900)
        if text and len(text) >= 4:
            out.append(f"{label}: {text}")
    if kind in {"video", "iframe", "image", "media"}:
        out.append(f"MEDIA TYPE: {kind}")
    for child in value.values():
        if isinstance(child, (dict, list)):
            _walk_media_metadata(child, out, urls)


def _normalized_video_url(url: str) -> str:
    value = str(url or "").strip()
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    host = (parts.hostname or "").casefold()
    path = parts.path or ""
    if "youtube" in host and "/embed/" in path:
        video_id = path.split("/embed/", 1)[1].split("/", 1)[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    if "player.vimeo.com" in host and "/video/" in path:
        video_id = path.split("/video/", 1)[1].split("/", 1)[0]
        if video_id:
            return f"https://vimeo.com/{video_id}"
    return value


def _oembed_metadata(url: str) -> list[str]:
    from .network import fetch_url

    normalized = _normalized_video_url(url)
    host = (urlsplit(normalized).hostname or "").casefold()
    if "youtube.com" in host or "youtu.be" in host or "youtube-nocookie.com" in host:
        endpoint = "https://www.youtube.com/oembed?format=json&url=" + quote(normalized, safe="")
    elif "vimeo.com" in host:
        endpoint = "https://vimeo.com/api/oembed.json?url=" + quote(normalized, safe="")
    else:
        return []
    response = fetch_url(
        endpoint,
        timeout=6.0,
        max_bytes=160_000,
        allowed_content_types={"application/json", "text/json"},
    )
    data = response.json()
    if not isinstance(data, dict):
        return []
    lines: list[str] = []
    title = _clean(data.get("title"), 800)
    author = _clean(data.get("author_name"), 300)
    provider = _clean(data.get("provider_name"), 160)
    if title:
        lines.append(f"VIDEO TITLE: {title}")
    if author:
        lines.append(f"VIDEO AUTHOR/CHANNEL: {author}")
    if provider:
        lines.append(f"VIDEO PROVIDER: {provider}")
    return lines


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in lines:
        line = _clean(raw, 1100)
        key = line.casefold()
        if not line or key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def build_media_evidence(db: Any, article: Any) -> tuple[str, dict[str, Any]]:
    """Build verified metadata evidence without interpreting image/video content."""
    lines: list[str] = []
    urls: list[str] = []
    try:
        layout = json.loads(str(_v(article, "article_layout_json", "") or "{}"))
    except Exception:
        layout = {}
    _walk_media_metadata(layout, lines, urls)

    try:
        from .media import decode_media
        for encoded in db.media_urls(article):
            kind, url = decode_media(encoded)
            if url:
                urls.append(url)
            if kind in {"video", "iframe", "image"}:
                lines.append(f"MEDIA TYPE: {kind}")
    except Exception:
        pass

    video_urls: list[str] = []
    for url in urls:
        low = url.casefold()
        if any(host in low for host in ("youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com")):
            normalized = _normalized_video_url(url)
            if normalized not in video_urls:
                video_urls.append(normalized)

    oembed_errors: list[str] = []
    for url in video_urls[:2]:
        try:
            lines.extend(_oembed_metadata(url))
        except Exception as exc:
            oembed_errors.append(str(exc)[:240])

    lines = _dedupe_lines(lines)
    evidence = "\n".join(lines[:18])
    meta = {
        "version": 1,
        "media_urls": len(set(urls)),
        "video_urls": video_urls[:4],
        "evidence_lines": len(lines),
        "oembed_errors": oembed_errors[:2],
    }
    return evidence, meta


def enrich_article_for_media(service: Any, channel: Any, article_id: int) -> None:
    if _media_mode(channel) == MEDIA_ENRICH_OFF:
        return
    row = service.db.get_article(int(article_id))
    if row is None:
        return
    base_text = _without_media_marker(str(_v(row, "raw_text", "") or ""))
    if len(_clean(base_text, 20_000)) >= _media_threshold(channel):
        return

    evidence, meta = build_media_evidence(service.db, row)
    if not evidence:
        # No textual media evidence means we learned nothing factual. Keep the
        # article untouched rather than turning a URL into invented semantics.
        return

    enriched = base_text.rstrip() + "\n\n" + MEDIA_MARKER + "\n" + evidence
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    service.db.update_article(
        int(article_id),
        raw_text=enriched,
        media_enrichment_text=evidence,
        media_enrichment_json=json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
        media_enrichment_checked_at=stamp,
        content_hash=content_hash(str(_v(row, "title", "") or ""), enriched),
    )
    service._audit(
        "rc69_media_enrichment",
        "enriched",
        f"base_chars={len(base_text)}; evidence_lines={meta['evidence_lines']}; videos={len(meta['video_urls'])}",
        channel_id=int(channel.id),
        article_id=int(article_id),
    )
    LOG.info(
        "RC69 MEDIA_ENRICHED channel_id=%s article_id=%s base_chars=%s lines=%s videos=%s",
        int(channel.id), int(article_id), len(base_text), meta["evidence_lines"], len(meta["video_urls"]),
    )


def _channel_fit_prompt_rc69(policy: Any, article: Any, *, channel_id: int) -> str:
    base = _PREV["channel_fit_prompt"](policy, article, channel_id=channel_id)
    from . import rc68_editorial_value as rc68
    channel = rc68._channel(int(channel_id or 0))
    media_allowed = _media_first_allowed(channel) if channel is not None else True
    threshold = _media_threshold(channel) if channel is not None else 500
    note = f"""

RC69 CHANNEL-IDENTITY RULE:
Тематичні слова самі по собі НЕ означають відповідність каналу. Перевіряй також ТИП і ФУНКЦІЮ історії, які описані в CHANNEL POLICY. Наприклад, якщо політика вимагає нових досліджень/технологій/відкриттів, звичайний ремонт конкретного пристрою, DIY, інструкція або одиничний кейс техніки безпеки не стає релевантним лише через технічну лексику. Це універсальне правило: вирішальним є саме текст політики каналу.

RC69 MEDIA-FIRST SETTINGS:
media_first_allowed={str(media_allowed).lower()}; thin_text_threshold={threshold} chars.
Якщо media_first_allowed=true і SOURCE містить блок {MEDIA_MARKER}, короткий текст статті САМ ПО СОБІ не є причиною reject. Оцінюй заголовок разом із перевіреними metadata/caption/alt/video-title. Не вигадуй того, чого metadata не повідомляють.
""".strip()
    return base + "\n\n" + note


def _value_prompt_rc69(article: Any) -> str:
    base = _PREV["value_prompt"](article)
    has_media = bool(_clean(_v(article, "media_enrichment_text", ""), 12000)) or MEDIA_MARKER in str(_v(article, "raw_text", "") or "")
    if not has_media:
        return base
    return base + f"""

RC69 MEDIA-FIRST NOTE:
SOURCE містить блок {MEDIA_MARKER}. Це перевірені метадані медіа, а не опис, вигаданий AI. Не занижуй editorial value лише через коротке тіло статті: title + verified media metadata можуть самі містити повну суть історії. Водночас не приписуй відео/зображенню нічого, чого немає в цих метаданих.
"""


def _editorial_value_allowed_rc69(data: Mapping[str, Any]) -> tuple[bool, str, int]:
    from . import rc68_editorial_value as rc68

    score = rc68.editorial_value_score(data)
    novelty = rc68._score(data.get("novelty"))
    payoff = rc68._score(data.get("reader_payoff"))
    retell = rc68._score(data.get("retellability"))
    # Universal second lane: a genuinely surprising, immediately understandable
    # and retellable story can be worth a post even when it has no huge societal
    # consequence. Channel fit has already decided whether that KIND of story
    # belongs to this particular publication.
    if score >= 55 and novelty >= 72 and payoff >= 60 and retell >= 68:
        return True, "strong_retellable_payoff", score
    return _PREV["editorial_value_allowed"](data)


def _db_init_rc69(db: Any) -> None:
    _PREV["db_init"](db)
    with db.connect() as con:
        for name, decl in (
            ("media_enrichment_mode", "TEXT NOT NULL DEFAULT 'auto'"),
            ("media_first_allowed", "INTEGER NOT NULL DEFAULT 1"),
            ("media_min_text_chars", "INTEGER NOT NULL DEFAULT 500"),
        ):
            db._ensure_column(con, "channels", name, decl)
        for name, decl in (
            ("media_enrichment_text", "TEXT NOT NULL DEFAULT ''"),
            ("media_enrichment_json", "TEXT NOT NULL DEFAULT ''"),
            ("media_enrichment_checked_at", "TEXT"),
        ):
            db._ensure_column(con, "articles", name, decl)


def _set_channel_media_settings(
    db: Any,
    channel_id: int,
    *,
    media_enrichment_mode: str = MEDIA_ENRICH_AUTO,
    media_first_allowed: bool = True,
    media_min_text_chars: int = 500,
) -> None:
    mode = str(media_enrichment_mode or MEDIA_ENRICH_AUTO).casefold()
    if mode not in MEDIA_ENRICH_VALUES:
        mode = MEDIA_ENRICH_AUTO
    threshold = max(120, min(4000, int(media_min_text_chars or 500)))
    with db.connect() as con:
        con.execute(
            "UPDATE channels SET media_enrichment_mode=?,media_first_allowed=?,media_min_text_chars=?,updated_at=datetime('now') WHERE id=?",
            (mode, int(bool(media_first_allowed)), threshold, int(channel_id)),
        )


def _save_channel_rc69(db: Any, **kwargs: Any) -> int:
    channel_id = int(_PREV["save_channel"](db, **kwargs))
    pending = getattr(db, "_rc69_pending_media_settings", None)
    if isinstance(pending, dict):
        _set_channel_media_settings(db, channel_id, **pending)
        try:
            delattr(db, "_rc69_pending_media_settings")
        except AttributeError:
            pass
    return channel_id


def _update_article_rc69(db: Any, article_id: int, **fields: Any) -> None:
    from . import rc45_policy as rc45

    if fields.get("language") == "en":
        direction = rc45._CURRENT_DIRECTION.get()
        if direction == DIRECTION_UK_TO_UK:
            fields["language"] = "uk"
        elif direction == DIRECTION_RU_TO_UK:
            fields["language"] = "ru"
    _PREV["update_article"](db, int(article_id), **fields)


def _core_process_rc69(service: Any, channel: Any) -> Any:
    try:
        from . import rc67_nonblocking_runtime as rc67
        article_id = getattr(rc67._TARGET, "article_id", None)
        if article_id:
            enrich_article_for_media(service, channel, int(article_id))
    except Exception as exc:
        # Enrichment is evidence acquisition, not a new global kill switch.
        LOG.warning("RC69 media enrichment degraded channel_id=%s: %s", getattr(channel, "id", "?"), exc)
        try:
            service._audit("rc69_media_enrichment", "degraded", str(exc), channel_id=int(channel.id))
        except Exception:
            pass
    return _PREV["core_process"](service, channel)


def install_rc69_media_language() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import rc45_policy as rc45
    from . import rc67_nonblocking_runtime as rc67
    from . import rc68_editorial_value as rc68
    from . import service as svc
    from .database import Database

    rc45.DIRECTION_LABELS[DIRECTION_UK_TO_UK] = "Українська → Українська"
    rc45.DIRECTION_LABELS[DIRECTION_RU_TO_UK] = "Російська → Українська"

    _PREV.update(
        db_init=Database._init,
        save_channel=Database.save_channel,
        update_article=Database.update_article,
        input_gate=svc.looks_english,
        core_process=rc67._PREV.get("core_process"),
        channel_fit_prompt=rc68._channel_fit_prompt,
        value_prompt=rc68._value_prompt,
        editorial_value_allowed=rc68.editorial_value_allowed,
    )

    Database._init = _db_init_rc69
    Database.save_channel = _save_channel_rc69
    Database.update_article = _update_article_rc69
    Database.rc69_set_channel_media_settings = _set_channel_media_settings

    def direction_input_gate(text: str) -> bool:
        return accepts_input(rc45._CURRENT_DIRECTION.get(), text)

    svc.looks_english = direction_input_gate
    if _PREV["core_process"] is not None:
        rc67._PREV["core_process"] = _core_process_rc69

    rc68._channel_fit_prompt = _channel_fit_prompt_rc69
    rc68._value_prompt = _value_prompt_rc69
    rc68.editorial_value_allowed = _editorial_value_allowed_rc69
    # Force RC68 cached diagnostics from the old scoring contract to be recalculated.
    rc68._GATE_VERSION = 2

    LOG.info(
        "RC69 installed: config-driven media-first enrichment, strict channel-identity fit, universal retellable-value lane, and EN->UA / UKRU->EN / UK->UK / RU->UK input directions"
    )
    _INSTALLED = True
