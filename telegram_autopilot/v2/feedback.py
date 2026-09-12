from __future__ import annotations

import asyncio
import json
import sqlite3
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ..secrets_store import SecretConfig, load_secrets, save_secrets
from .loghub import event
from .storage import V2Store, now_iso

FEEDBACK_WINDOW_DAYS = 7
AUTO_REFRESH_SECONDS = 15 * 60
TOTAL_TIMEOUT_SECONDS = 40
REQUEST_TIMEOUT_SECONDS = 6
MESSAGE_CHUNK_SIZE = 40
MAX_AUTO_POSTS = 40
MAX_MANUAL_POSTS = 180
MAX_REACTOR_SCAN = 1200
REACTION_PAGE_SIZE = 100

_POSITIVE_EMOJI = {"👍", "🔥", "❤", "❤️", "👏", "🎉", "💯", "🤩", "😍", "🥳", "⚡", "🏆"}
_NEGATIVE_EMOJI = {"👎", "🤡", "🤮", "💩"}


def _v(row: Mapping[str, Any] | Any, key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except Exception:
        value = getattr(row, key, default)
    return default if value is None else value


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return default


def normalize_target(value: str) -> Any:
    text = str(value or "").strip()
    for prefix in ("https://t.me/", "http://t.me/"):
        if text.startswith(prefix):
            text = text.split(prefix, 1)[1].split("?", 1)[0].strip("/")
            if "/" in text:
                text = text.split("/", 1)[0]
    if text.startswith("@"):
        return text[1:]
    if text.lstrip("-").isdigit():
        try:
            return int(text)
        except ValueError:
            pass
    return text


def normalize_emoji(value: Any) -> str:
    emoticon = str(getattr(value, "emoticon", "") or "")
    if not emoticon and isinstance(value, str):
        emoticon = value
    return emoticon.replace("\ufe0f", "").strip()


def reaction_count_map(message: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    box = getattr(message, "reactions", None)
    for item in (getattr(box, "results", None) or []):
        emoji = normalize_emoji(getattr(item, "reaction", None))
        if not emoji:
            continue
        count = _int(getattr(item, "count", 0))
        result[emoji] = result.get(emoji, 0) + count
    return result


def operator_choices(message: Any) -> set[str]:
    """Reactions explicitly chosen by the connected Telegram user account."""
    out: set[str] = set()
    box = getattr(message, "reactions", None)
    for item in (getattr(box, "results", None) or []):
        chosen_order = getattr(item, "chosen_order", None)
        chosen = bool(getattr(item, "chosen", False)) or chosen_order is not None
        if not chosen:
            continue
        emoji = normalize_emoji(getattr(item, "reaction", None))
        if emoji:
            out.add(emoji)
    return out


def display_user(user: Any) -> str:
    name = " ".join(
        part for part in (
            str(getattr(user, "first_name", "") or "").strip(),
            str(getattr(user, "last_name", "") or "").strip(),
        ) if part
    ).strip()
    username = str(getattr(user, "username", "") or "").strip()
    if username:
        return (name + f" (@{username})").strip()
    return name or f"admin {int(getattr(user, 'id', 0) or 0)}"


@dataclass(slots=True)
class FeedbackSnapshot:
    article_id: int
    telegram_message_id: str
    published_at: str
    views: int
    forwards: int
    replies: int
    editor_admin_count: int
    editor_reacted_count: int
    editor_likes: int
    editor_dislikes: int
    editor_fires: int
    editor_other: int
    editor_coverage: str
    reactor_scan_complete: bool
    reactor_scanned: int
    audience_counts: dict[str, int]
    audience_total: int
    audience_positive: int
    audience_negative: int
    audience_fires: int
    audience_other: int
    editor_rows: list[dict[str, Any]]


def build_snapshot(
    *,
    row: Mapping[str, Any],
    message: Any,
    editor_reactions: dict[int, set[str]],
    admin_names: dict[int, str],
    admin_count: int,
    coverage: str,
    scan_complete: bool,
    scanned: int,
) -> FeedbackSnapshot:
    views = _int(getattr(message, "views", 0))
    forwards = _int(getattr(message, "forwards", 0))
    replies_box = getattr(message, "replies", None)
    replies = _int(getattr(replies_box, "replies", 0))
    aggregate = reaction_count_map(message)

    editor_rows: list[dict[str, Any]] = []
    editor_likes = editor_dislikes = editor_fires = editor_other = 0
    editor_emoji_counts: dict[str, int] = {}
    for actor, choices in editor_reactions.items():
        clean_choices = {normalize_emoji(item) for item in choices if normalize_emoji(item)}
        if not clean_choices:
            continue
        for emoji in clean_choices:
            editor_emoji_counts[emoji] = editor_emoji_counts.get(emoji, 0) + 1
        editor_likes += int("👍" in clean_choices)
        editor_dislikes += int("👎" in clean_choices)
        editor_fires += int("🔥" in clean_choices)
        other = {emoji: 1 for emoji in sorted(clean_choices) if emoji not in {"👍", "👎", "🔥"}}
        editor_other += len(other)
        editor_rows.append(
            {
                "admin_peer_id": str(actor),
                "admin_name": admin_names.get(actor, f"admin {actor}"),
                "likes": int("👍" in clean_choices),
                "dislikes": int("👎" in clean_choices),
                "fires": int("🔥" in clean_choices),
                "other": other,
            }
        )

    audience_counts: dict[str, int] = {}
    for emoji, total_count in aggregate.items():
        audience_counts[emoji] = max(0, int(total_count) - int(editor_emoji_counts.get(emoji, 0)))
    audience_counts = {emoji: count for emoji, count in audience_counts.items() if count > 0}
    audience_total = sum(audience_counts.values())
    audience_positive = sum(count for emoji, count in audience_counts.items() if emoji in _POSITIVE_EMOJI)
    audience_negative = sum(count for emoji, count in audience_counts.items() if emoji in _NEGATIVE_EMOJI)
    audience_fires = int(audience_counts.get("🔥", 0))
    audience_other = max(0, audience_total - audience_positive - audience_negative)

    return FeedbackSnapshot(
        article_id=int(_v(row, "article_id", 0) or 0),
        telegram_message_id=str(_v(row, "telegram_message_id", "") or ""),
        published_at=str(_v(row, "published_at", "") or ""),
        views=views,
        forwards=forwards,
        replies=replies,
        editor_admin_count=int(admin_count),
        editor_reacted_count=len(editor_reactions),
        editor_likes=editor_likes,
        editor_dislikes=editor_dislikes,
        editor_fires=editor_fires,
        editor_other=editor_other,
        editor_coverage=coverage,
        reactor_scan_complete=scan_complete,
        reactor_scanned=scanned,
        audience_counts=audience_counts,
        audience_total=audience_total,
        audience_positive=audience_positive,
        audience_negative=audience_negative,
        audience_fires=audience_fires,
        audience_other=audience_other,
        editor_rows=editor_rows,
    )


def _combine_publication_snapshots(snapshots: list[FeedbackSnapshot], primary_by_article: dict[int, str]) -> list[FeedbackSnapshot]:
    """Aggregate album/text message parts back into one logical publication unit.

    Views/forwards/replies use max rather than sum because Telegram can expose the
    same delivery reach on multiple album items. Reactions are summed across parts;
    administrator topic/style choices are de-duplicated per administrator.
    """
    groups: dict[int, list[FeedbackSnapshot]] = {}
    for snap in snapshots:
        groups.setdefault(int(snap.article_id), []).append(snap)
    out: list[FeedbackSnapshot] = []
    for article_id, parts in groups.items():
        if len(parts) == 1:
            one = parts[0]
            one.telegram_message_id = primary_by_article.get(article_id, one.telegram_message_id)
            out.append(one)
            continue
        audience: dict[str, int] = {}
        editors: dict[str, dict[str, Any]] = {}
        for part in parts:
            for emoji, count in part.audience_counts.items():
                audience[emoji] = audience.get(emoji, 0) + _int(count)
            for row in part.editor_rows:
                key = str(row.get("admin_peer_id") or "")
                if not key:
                    continue
                target = editors.setdefault(key, {"admin_peer_id": key, "admin_name": str(row.get("admin_name") or ""), "likes": 0, "dislikes": 0, "fires": 0, "other": {}})
                target["likes"] = max(_int(target.get("likes")), _int(row.get("likes")))
                target["dislikes"] = max(_int(target.get("dislikes")), _int(row.get("dislikes")))
                target["fires"] = max(_int(target.get("fires")), _int(row.get("fires")))
                other = row.get("other") if isinstance(row.get("other"), dict) else {}
                merged = target.get("other") if isinstance(target.get("other"), dict) else {}
                for emoji, count in other.items():
                    merged[str(emoji)] = max(_int(merged.get(str(emoji))), _int(count))
                target["other"] = merged
        editor_rows = list(editors.values())
        editor_likes = sum(_int(row.get("likes")) for row in editor_rows)
        editor_dislikes = sum(_int(row.get("dislikes")) for row in editor_rows)
        editor_fires = sum(_int(row.get("fires")) for row in editor_rows)
        editor_other = sum(sum(_int(v) for v in (row.get("other") or {}).values()) for row in editor_rows)
        audience_total = sum(audience.values())
        audience_positive = sum(count for emoji, count in audience.items() if emoji in _POSITIVE_EMOJI)
        audience_negative = sum(count for emoji, count in audience.items() if emoji in _NEGATIVE_EMOJI)
        audience_fires = _int(audience.get("🔥"))
        base = parts[0]
        coverage = "all_admins" if all(p.editor_coverage == "all_admins" for p in parts) else next((p.editor_coverage for p in parts if p.editor_coverage != "all_admins"), base.editor_coverage)
        out.append(FeedbackSnapshot(
            article_id=article_id, telegram_message_id=primary_by_article.get(article_id, base.telegram_message_id), published_at=base.published_at,
            views=max((p.views for p in parts), default=0), forwards=max((p.forwards for p in parts), default=0), replies=max((p.replies for p in parts), default=0),
            editor_admin_count=max((p.editor_admin_count for p in parts), default=0), editor_reacted_count=len(editor_rows),
            editor_likes=editor_likes, editor_dislikes=editor_dislikes, editor_fires=editor_fires, editor_other=editor_other,
            editor_coverage=coverage, reactor_scan_complete=all(p.reactor_scan_complete for p in parts), reactor_scanned=sum(p.reactor_scanned for p in parts),
            audience_counts=audience, audience_total=audience_total, audience_positive=audience_positive, audience_negative=audience_negative,
            audience_fires=audience_fires, audience_other=max(0, audience_total-audience_positive-audience_negative), editor_rows=editor_rows,
        ))
    return out


def analytics_configured() -> tuple[bool, str]:
    try:
        secrets = load_secrets()
    except Exception as exc:
        return False, f"Секрети недоступні: {exc}"
    if not int(getattr(secrets, "telegram_api_id", 0) or 0):
        return False, "Telegram API ID не налаштовано"
    if not str(getattr(secrets, "telegram_api_hash", "") or "").strip():
        return False, "Telegram API Hash не налаштовано"
    if not str(getattr(secrets, "telegram_user_session", "") or "").strip():
        return False, "Telegram Analytics user-session не авторизована"
    return True, "Telegram Analytics налаштовано"


def save_analytics_credentials(*, api_id: int, api_hash: str, phone: str, session: str | None = None) -> None:
    cfg = load_secrets()
    cfg.telegram_api_id = max(0, int(api_id or 0))
    cfg.telegram_api_hash = str(api_hash or "").strip()
    cfg.telegram_phone = str(phone or "").strip()
    if session is not None:
        cfg.telegram_user_session = str(session or "").strip()
    save_secrets(cfg)


def authorize_telegram_analytics(
    *,
    api_id: int,
    api_hash: str,
    phone: str,
    existing_session: str = "",
    code_callback: Callable[[], str],
    password_callback: Callable[[], str],
) -> tuple[str, str]:
    try:
        from telethon.errors import SessionPasswordNeededError
        from telethon.sessions import StringSession
        from telethon.sync import TelegramClient
    except Exception as exc:
        raise RuntimeError("Не встановлено Telethon для Telegram Analytics") from exc

    api_id = int(api_id)
    api_hash = str(api_hash or "").strip()
    phone = str(phone or "").strip()
    if api_id <= 0 or not api_hash or not phone:
        raise ValueError("Потрібні Telegram API ID, API Hash і телефон")

    owned_loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed():
        owned_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(owned_loop)
    client = TelegramClient(
        StringSession(str(existing_session or "")), api_id, api_hash,
        connection_retries=1, request_retries=1, timeout=15,
    )
    try:
        client.connect()
        if not client.is_user_authorized():
            sent = client.send_code_request(phone)
            code = str(code_callback() or "").strip()
            if not code:
                raise RuntimeError("Код Telegram не введено")
            try:
                client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = str(password_callback() or "")
                if not password:
                    raise RuntimeError("Увімкнено 2FA, але пароль не введено")
                client.sign_in(password=password)
        if not client.is_user_authorized():
            raise RuntimeError("Telegram не підтвердив user-session")
        session = str(client.session.save() or "").strip()
        if not session:
            raise RuntimeError("Telegram не повернув StringSession")
        me = client.get_me()
        return session, display_user(me) if me is not None else "Telegram-акаунт"
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        if owned_loop is not None:
            try:
                owned_loop.close()
            finally:
                asyncio.set_event_loop(None)


def _peer_id(peer: Any, utils_module: Any) -> int:
    try:
        return int(utils_module.get_peer_id(peer))
    except Exception:
        for key in ("user_id", "channel_id", "chat_id"):
            value = getattr(peer, key, None)
            if value:
                return int(value)
    return 0


async def _bounded(awaitable: Any, timeout: float = REQUEST_TIMEOUT_SECONDS) -> Any:
    return await asyncio.wait_for(awaitable, timeout=max(0.5, float(timeout)))


async def _scan_admin_reactors(
    client: Any,
    *,
    input_peer: Any,
    message_id: int,
    admin_ids: set[int],
    channel_peer_id: int,
) -> tuple[dict[int, set[str]], int, bool]:
    from telethon import functions, utils

    found: dict[int, set[str]] = {}
    offset: str | None = None
    scanned = 0
    complete = False
    while scanned < MAX_REACTOR_SCAN:
        result = await _bounded(
            client(
                functions.messages.GetMessageReactionsListRequest(
                    peer=input_peer,
                    id=int(message_id),
                    limit=REACTION_PAGE_SIZE,
                    reaction=None,
                    offset=offset,
                )
            )
        )
        rows = list(getattr(result, "reactions", None) or [])
        for item in rows:
            scanned += 1
            actor = _peer_id(getattr(item, "peer_id", None), utils)
            if actor in admin_ids or (channel_peer_id and actor == channel_peer_id):
                emoji = normalize_emoji(getattr(item, "reaction", None))
                if emoji:
                    found.setdefault(actor, set()).add(emoji)
        next_offset = str(getattr(result, "next_offset", "") or "").strip()
        if not next_offset or not rows:
            complete = True
            break
        offset = next_offset
    return found, scanned, complete


async def _fetch_snapshots_async(
    *,
    session: str,
    api_id: int,
    api_hash: str,
    target: Any,
    rows: list[dict[str, Any]],
    progress: Callable[[str], None] | None,
) -> tuple[list[FeedbackSnapshot], dict[str, Any]]:
    try:
        from telethon import TelegramClient, types, utils
        from telethon.sessions import StringSession
    except Exception as exc:
        raise RuntimeError("Не встановлено Telethon для Telegram Analytics") from exc

    def report(text: str) -> None:
        if progress:
            try:
                progress(text)
            except Exception:
                pass

    client = TelegramClient(
        StringSession(str(session or "")), int(api_id), str(api_hash or "").strip(),
        connection_retries=0, request_retries=1, retry_delay=0, auto_reconnect=False,
        timeout=REQUEST_TIMEOUT_SECONDS, receive_updates=False,
    )
    meta: dict[str, Any] = {"editor_coverage": "unknown", "admin_count": 0, "reactor_scanned": 0, "warning": ""}
    try:
        report("підключаюсь до Telegram…")
        await _bounded(client.connect())
        if not await _bounded(client.is_user_authorized(), timeout=4):
            raise RuntimeError("Telegram Analytics session не авторизована")
        report("Telegram OK · відкриваю канал…")
        entity = await _bounded(client.get_entity(target))
        input_peer = await _bounded(client.get_input_entity(entity))
        me = await _bounded(client.get_me(), timeout=4)
        self_id = int(getattr(me, "id", 0) or 0)
        channel_peer_id = _peer_id(entity, utils)

        admin_ids: set[int] = set()
        admin_names: dict[int, str] = {}
        try:
            report("читаю список адміністраторів…")
            admins = await _bounded(client.get_participants(entity, limit=200, filter=types.ChannelParticipantsAdmins), timeout=8)
            for user in list(admins or []):
                uid = int(getattr(user, "id", 0) or 0)
                if uid:
                    admin_ids.add(uid)
                    admin_names[uid] = display_user(user)
            if admin_ids:
                meta["editor_coverage"] = "all_admins"
            else:
                raise RuntimeError("admin list empty")
        except Exception as exc:
            meta["editor_coverage"] = "operator_only_fallback"
            if self_id:
                admin_ids.add(self_id)
                admin_names[self_id] = display_user(me)
            meta["warning"] = f"Повний список адмінів недоступний: {type(exc).__name__}"
        meta["admin_count"] = len(admin_ids)

        ids: list[int] = []
        by_id: dict[int, dict[str, Any]] = {}
        primary_by_article: dict[int, str] = {}
        for row in rows:
            article_id = _int(row.get("article_id"))
            primary = str(row.get("telegram_message_id") or "")
            primary_by_article[article_id] = primary
            candidates = row.get("telegram_message_ids")
            mids = list(candidates) if isinstance(candidates, list) else [primary]
            for raw_mid in mids:
                try:
                    mid = int(str(raw_mid or ""))
                except Exception:
                    continue
                if mid <= 0 or mid in by_id:
                    continue
                copy = dict(row); copy["telegram_message_id"] = str(mid)
                ids.append(mid)
                by_id[mid] = copy

        messages: list[Any] = []
        for offset in range(0, len(ids), MESSAGE_CHUNK_SIZE):
            chunk = ids[offset:offset + MESSAGE_CHUNK_SIZE]
            report(f"читаю пости {min(offset + len(chunk), len(ids))}/{len(ids)}…")
            part = await _bounded(client.get_messages(entity, ids=chunk))
            if part is None:
                continue
            if isinstance(part, (list, tuple)):
                messages.extend(part)
            else:
                try:
                    messages.extend(list(part))
                except TypeError:
                    messages.append(part)

        snapshots: list[FeedbackSnapshot] = []
        for index, message in enumerate(messages, start=1):
            if message is None:
                continue
            mid = int(getattr(message, "id", 0) or 0)
            row = by_id.get(mid)
            if row is None:
                continue
            aggregate = reaction_count_map(message)
            editor_reactions: dict[int, set[str]] = {}
            scanned = 0
            scan_complete = True
            if sum(aggregate.values()) > 0:
                report(f"адмін-реакції {index}/{len(messages)}…")
                try:
                    editor_reactions, scanned, scan_complete = await _scan_admin_reactors(
                        client, input_peer=input_peer, message_id=mid,
                        admin_ids=admin_ids, channel_peer_id=channel_peer_id,
                    )
                except Exception as exc:
                    scan_complete = False
                    if not meta.get("warning"):
                        meta["warning"] = f"Частину реакторів не прочитано: {type(exc).__name__}"
            own = operator_choices(message)
            if own and self_id and self_id in admin_ids:
                editor_reactions.setdefault(self_id, set()).update(own)
            if channel_peer_id in editor_reactions:
                admin_names[channel_peer_id] = "Канал (анонімний адмін)"
            coverage = str(meta.get("editor_coverage") or "unknown")
            if coverage == "all_admins" and not scan_complete:
                coverage = "partial_reactor_scan"
            row = dict(row)
            row["telegram_message_id"] = str(mid)
            snapshots.append(build_snapshot(
                row=row, message=message, editor_reactions=editor_reactions,
                admin_names=admin_names, admin_count=int(meta.get("admin_count") or 0),
                coverage=coverage, scan_complete=scan_complete, scanned=scanned,
            ))
            meta["reactor_scanned"] = int(meta.get("reactor_scanned") or 0) + scanned
        return _combine_publication_snapshots(snapshots, primary_by_article), meta
    finally:
        try:
            result = client.disconnect()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=2)
        except Exception:
            pass


def _run_fetch(**kwargs: Any) -> tuple[list[FeedbackSnapshot], dict[str, Any]]:
    async def runner() -> tuple[list[FeedbackSnapshot], dict[str, Any]]:
        return await asyncio.wait_for(_fetch_snapshots_async(**kwargs), timeout=TOTAL_TIMEOUT_SECONDS)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(runner())
    raise RuntimeError("Telegram feedback refresh має виконуватися у фоновому потоці")


class FeedbackService:
    """Telegram metrics acquisition and persistence only.

    This module does not decide what to publish and does not generate copy. Learning logic
    lives in v2.learning, so analytics failures can never stop the editorial runtime.
    """

    def __init__(self, store: V2Store):
        self.store = store

    def ensure_schema(self) -> dict[str, int]:
        additions = (
            ("editor_admin_count", "INTEGER NOT NULL DEFAULT 0"),
            ("editor_reacted_count", "INTEGER NOT NULL DEFAULT 0"),
            ("editor_coverage", "TEXT NOT NULL DEFAULT 'legacy'"),
            ("reactor_scan_complete", "INTEGER NOT NULL DEFAULT 0"),
            ("reactor_scanned", "INTEGER NOT NULL DEFAULT 0"),
            ("audience_reactions_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("audience_total", "INTEGER NOT NULL DEFAULT 0"),
            ("audience_positive", "INTEGER NOT NULL DEFAULT 0"),
            ("audience_negative", "INTEGER NOT NULL DEFAULT 0"),
            ("audience_fires", "INTEGER NOT NULL DEFAULT 0"),
            ("audience_other", "INTEGER NOT NULL DEFAULT 0"),
        )
        changed = 0
        with self.store.transaction() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                columns = {str(row[1]) for row in con.execute("PRAGMA table_info(feedback)").fetchall()}
                for name, decl in additions:
                    if name not in columns:
                        con.execute(f"ALTER TABLE feedback ADD COLUMN {name} {decl}")
                        changed += 1
                con.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS feedback_editor_reactions (
                        article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                        channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                        telegram_message_id TEXT NOT NULL,
                        admin_peer_id TEXT NOT NULL,
                        admin_name TEXT NOT NULL DEFAULT '',
                        checked_at TEXT NOT NULL,
                        likes INTEGER NOT NULL DEFAULT 0,
                        dislikes INTEGER NOT NULL DEFAULT 0,
                        fires INTEGER NOT NULL DEFAULT 0,
                        other_reactions_json TEXT NOT NULL DEFAULT '{}',
                        PRIMARY KEY(article_id, admin_peer_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_feedback_editor_channel_checked
                        ON feedback_editor_reactions(channel_id, checked_at DESC);
                    """
                )
                con.commit()
            except Exception:
                con.rollback()
                raise
        return {"feedback_columns_added": changed}

    def candidates(self, channel_id: int, *, days: int = FEEDBACK_WINDOW_DAYS, limit: int = MAX_AUTO_POSTS, article_id: int | None = None) -> list[dict[str, Any]]:
        where = "a.channel_id=? AND a.stage='PUBLISHED' AND a.telegram_message_id<>'' AND a.published_at<>''"
        args: list[Any] = [int(channel_id)]
        if article_id is not None:
            where += " AND a.id=?"
            args.append(int(article_id))
        else:
            where += " AND datetime(a.published_at)>=datetime('now',?)"
            args.append(f"-{max(1, int(days))} days")
        args.append(max(1, min(500, int(limit))))
        with self.store.connect() as con:
            rows = con.execute(
                f"""SELECT a.id AS article_id,a.channel_id,a.telegram_message_id,a.published_at,a.title,a.article_layout_json
                    FROM articles a WHERE {where}
                    ORDER BY datetime(a.published_at) DESC LIMIT ?""", args
            ).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            mids: list[str] = []
            try:
                layout = json.loads(str(row.get("article_layout_json") or "{}"))
            except Exception:
                layout = {}
            if isinstance(layout, dict):
                delivery = layout.get("telegram_delivery")
                if isinstance(delivery, dict) and isinstance(delivery.get("message_ids"), list):
                    mids = [str(x) for x in delivery.get("message_ids") if str(x).strip()]
            primary = str(row.get("telegram_message_id") or "")
            if primary and primary not in mids:
                mids.append(primary)
            row["telegram_message_ids"] = mids
            result.append(row)
        return result

    def feedback_rows(self, channel_id: int, *, days: int = FEEDBACK_WINDOW_DAYS, limit: int = 180) -> list[dict[str, Any]]:
        with self.store.connect() as con:
            rows = con.execute(
                """SELECT f.*,a.source_id,a.title,a.raw_text,a.event_summary,a.final_text,a.canonical_source_url
                   FROM feedback f JOIN articles a ON a.id=f.article_id
                   WHERE f.channel_id=? AND datetime(f.published_at)>=datetime('now',?)
                   ORDER BY datetime(f.published_at) DESC LIMIT ?""",
                (int(channel_id), f"-{max(1, int(days))} days", max(1, min(500, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self, channel_id: int) -> dict[str, Any]:
        with self.store.connect() as con:
            row = con.execute(
                """SELECT COUNT(*) tracked,
                          SUM(CASE WHEN likes>0 OR dislikes>0 OR fires>0 THEN 1 ELSE 0 END) editor_rated_posts,
                          COALESCE(SUM(likes),0) likes,COALESCE(SUM(dislikes),0) dislikes,COALESCE(SUM(fires),0) fires,
                          SUM(CASE WHEN audience_total>0 OR forwards>0 OR replies>0 THEN 1 ELSE 0 END) audience_rated_posts,
                          COALESCE(SUM(audience_total),0) audience_total,COALESCE(SUM(audience_positive),0) audience_positive,
                          COALESCE(SUM(audience_negative),0) audience_negative,COALESCE(SUM(views),0) views,
                          COALESCE(SUM(forwards),0) forwards,COALESCE(SUM(replies),0) replies,
                          COALESCE(MAX(editor_admin_count),0) admin_count,
                          MAX(checked_at) last_checked
                   FROM feedback
                   WHERE channel_id=? AND datetime(published_at)>=datetime('now','-7 days')""",
                (int(channel_id),),
            ).fetchone()
        if not row:
            return {}
        result = {key: row[key] for key in row.keys()}
        for key in list(result):
            if key != "last_checked":
                result[key] = _int(result[key])
        return result

    def _save_snapshots(self, channel_id: int, snapshots: list[FeedbackSnapshot]) -> None:
        if not snapshots:
            return
        stamp = now_iso()
        con = sqlite3.connect(self.store.path, timeout=5.0)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=5000")
            con.execute("BEGIN IMMEDIATE")
            for snap in snapshots:
                con.execute(
                    """INSERT INTO feedback(
                           article_id,channel_id,telegram_message_id,checked_at,published_at,
                           views,forwards,replies,likes,dislikes,fires,other_reactions,
                           editor_admin_count,editor_reacted_count,editor_coverage,reactor_scan_complete,reactor_scanned,
                           audience_reactions_json,audience_total,audience_positive,audience_negative,audience_fires,audience_other,
                           legacy_config_json
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(article_id) DO UPDATE SET
                           telegram_message_id=excluded.telegram_message_id,checked_at=excluded.checked_at,published_at=excluded.published_at,
                           views=excluded.views,forwards=excluded.forwards,replies=excluded.replies,
                           likes=excluded.likes,dislikes=excluded.dislikes,fires=excluded.fires,other_reactions=excluded.other_reactions,
                           editor_admin_count=excluded.editor_admin_count,editor_reacted_count=excluded.editor_reacted_count,
                           editor_coverage=excluded.editor_coverage,reactor_scan_complete=excluded.reactor_scan_complete,
                           reactor_scanned=excluded.reactor_scanned,audience_reactions_json=excluded.audience_reactions_json,
                           audience_total=excluded.audience_total,audience_positive=excluded.audience_positive,
                           audience_negative=excluded.audience_negative,audience_fires=excluded.audience_fires,audience_other=excluded.audience_other""",
                    (
                        snap.article_id, int(channel_id), snap.telegram_message_id, stamp, snap.published_at,
                        snap.views, snap.forwards, snap.replies, snap.editor_likes, snap.editor_dislikes, snap.editor_fires, snap.editor_other,
                        snap.editor_admin_count, snap.editor_reacted_count, snap.editor_coverage, int(snap.reactor_scan_complete), snap.reactor_scanned,
                        json.dumps(snap.audience_counts, ensure_ascii=False, sort_keys=True), snap.audience_total,
                        snap.audience_positive, snap.audience_negative, snap.audience_fires, snap.audience_other, "{}",
                    ),
                )
                con.execute("DELETE FROM feedback_editor_reactions WHERE article_id=?", (snap.article_id,))
                for editor in snap.editor_rows:
                    con.execute(
                        """INSERT INTO feedback_editor_reactions(
                               article_id,channel_id,telegram_message_id,admin_peer_id,admin_name,checked_at,
                               likes,dislikes,fires,other_reactions_json
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            snap.article_id, int(channel_id), snap.telegram_message_id,
                            str(editor.get("admin_peer_id") or ""), str(editor.get("admin_name") or "")[:300], stamp,
                            _int(editor.get("likes")), _int(editor.get("dislikes")), _int(editor.get("fires")),
                            json.dumps(editor.get("other") or {}, ensure_ascii=False, sort_keys=True),
                        ),
                    )
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def refresh_channel(
        self,
        channel_id: int,
        *,
        force: bool = False,
        article_id: int | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        configured, detail = analytics_configured()
        if not configured:
            return {"configured": False, "checked": 0, "saved": 0, "error": detail, "elapsed": 0.0}
        channel = self.store.get_channel(int(channel_id))
        if channel is None:
            return {"configured": True, "checked": 0, "saved": 0, "error": "Канал не знайдено", "elapsed": 0.0}
        rows = self.candidates(
            int(channel_id), limit=(MAX_MANUAL_POSTS if force else MAX_AUTO_POSTS), article_id=article_id
        )
        if not rows:
            return {"configured": True, "checked": 0, "saved": 0, "error": "", "elapsed": time.monotonic() - started}
        target = normalize_target(channel.telegram_chat_id)
        if not target:
            return {"configured": True, "checked": 0, "saved": 0, "error": "Порожній Telegram target каналу", "elapsed": time.monotonic() - started}
        secrets = load_secrets()
        try:
            snapshots, meta = _run_fetch(
                session=str(secrets.telegram_user_session or ""), api_id=int(secrets.telegram_api_id or 0),
                api_hash=str(secrets.telegram_api_hash or ""), target=target, rows=rows, progress=progress,
            )
            if progress:
                progress("зберігаю editor + audience статистику…")
            self._save_snapshots(int(channel_id), snapshots)
            elapsed = time.monotonic() - started
            event(
                "feedback", "refresh complete", channel_id=int(channel_id), checked=len(snapshots),
                admin_count=int(meta.get("admin_count") or 0), coverage=str(meta.get("editor_coverage") or ""),
                elapsed_seconds=round(elapsed, 2), warning=str(meta.get("warning") or "")[:500],
            )
            return {
                "configured": True, "checked": len(snapshots), "saved": len(snapshots), "error": "",
                "elapsed": elapsed, "admin_count": int(meta.get("admin_count") or 0),
                "editor_coverage": str(meta.get("editor_coverage") or "unknown"),
                "reactor_scanned": int(meta.get("reactor_scanned") or 0), "warning": str(meta.get("warning") or ""),
            }
        except (TimeoutError, asyncio.TimeoutError):
            elapsed = time.monotonic() - started
            text = f"Telegram Analytics не завершився за {TOTAL_TIMEOUT_SECONDS} с"
            event("feedback", "refresh timeout", level=30, channel_id=int(channel_id), elapsed_seconds=round(elapsed, 2))
            return {"configured": True, "checked": 0, "saved": 0, "error": text, "elapsed": elapsed}
        except Exception as exc:
            elapsed = time.monotonic() - started
            event("feedback", "refresh failed", level=30, channel_id=int(channel_id), detail=str(exc)[:1000], elapsed_seconds=round(elapsed, 2))
            return {"configured": True, "checked": 0, "saved": 0, "error": str(exc)[:1000], "elapsed": elapsed}


class FeedbackRuntime:
    """Independent periodic analytics worker. It never blocks RuntimeEngine."""

    def __init__(self, service: FeedbackService, store: V2Store, *, interval_seconds: int = AUTO_REFRESH_SECONDS):
        import threading
        self.service = service
        self.store = store
        self.interval_seconds = max(300, int(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict[int, float] = {}

    def start(self) -> None:
        import threading
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="V2-Feedback-Runtime")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _loop(self) -> None:
        # Leave startup, collection and AI probes alone for the first minute.
        if self._stop.wait(60.0):
            return
        while not self._stop.is_set():
            configured, _ = analytics_configured()
            if not configured:
                self._stop.wait(60.0)
                continue
            now = time.monotonic()
            for row in self.store.list_channels(enabled_only=True):
                if self._stop.is_set():
                    return
                cid = int(row["id"])
                if now - float(self._last.get(cid, 0.0)) < self.interval_seconds:
                    continue
                self._last[cid] = time.monotonic()
                summary = self.service.refresh_channel(cid, force=False)
                if summary.get("error"):
                    event("feedback", "auto refresh degraded", level=30, channel_id=cid, detail=str(summary.get("error"))[:600])
            self._stop.wait(30.0)
