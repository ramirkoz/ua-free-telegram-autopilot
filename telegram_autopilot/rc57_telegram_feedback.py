from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Callable
from typing import Any

from .rc53_hardening import reaction_health
from .rc57_feedback_model import (
    MAX_AUTO_POSTS,
    MAX_MANUAL_POSTS,
    MAX_REACTOR_SCAN,
    MESSAGE_CHUNK_SIZE,
    REACTION_PAGE_SIZE,
    REQUEST_TIMEOUT_SECONDS,
    TOTAL_TIMEOUT_SECONDS,
    build_snapshot,
    display_user,
    normalize_emoji,
    operator_choices,
    reaction_count_map,
)
from .secrets_store import load_secrets

LOG = logging.getLogger("telegram_autopilot.rc57")


def _peer_id(peer: Any, utils_module: Any) -> int:
    try:
        return int(utils_module.get_peer_id(peer))
    except Exception:
        for key in ("user_id", "channel_id", "chat_id"):
            value = getattr(peer, key, None)
            if value:
                return int(value)
    return 0


async def _bounded(awaitable, timeout: float = REQUEST_TIMEOUT_SECONDS):
    return await asyncio.wait_for(awaitable, timeout=max(0.5, float(timeout)))


async def scan_admin_reactors(
    client: Any,
    *,
    input_peer: Any,
    message_id: int,
    admin_ids: set[int],
    channel_peer_id: int,
    max_scan: int = MAX_REACTOR_SCAN,
) -> tuple[dict[int, set[str]], int, bool]:
    from telethon import functions, utils

    found: dict[int, set[str]] = {}
    offset: str | None = None
    scanned = 0
    complete = False
    while scanned < max_scan:
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
        for reaction_row in rows:
            scanned += 1
            actor = _peer_id(getattr(reaction_row, "peer_id", None), utils)
            if actor in admin_ids or (channel_peer_id and actor == channel_peer_id):
                emoji = normalize_emoji(getattr(reaction_row, "reaction", None))
                if emoji:
                    found.setdefault(actor, set()).add(emoji)
        next_offset = str(getattr(result, "next_offset", "") or "").strip()
        if not next_offset or not rows:
            complete = True
            break
        offset = next_offset
    return found, scanned, complete


async def fetch_snapshots_async(
    *,
    session: str,
    api_id: int,
    api_hash: str,
    target: Any,
    rows: list[dict[str, Any]],
    progress: Callable[[str], None] | None,
):
    try:
        from telethon import TelegramClient, types, utils
        from telethon.sessions import StringSession
    except Exception as exc:
        raise RuntimeError("Не встановлено Telethon для Telegram Analytics.") from exc

    def report(text: str) -> None:
        if progress:
            try:
                progress(text)
            except Exception:
                pass

    client = TelegramClient(
        StringSession(str(session or "")),
        int(api_id),
        str(api_hash or "").strip(),
        connection_retries=0,
        request_retries=1,
        retry_delay=0,
        auto_reconnect=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
        receive_updates=False,
    )
    meta: dict[str, Any] = {
        "editor_coverage": "unknown",
        "admin_count": 0,
        "reactor_scanned": 0,
        "warning": "",
    }
    try:
        report("підключаюсь до Telegram…")
        await _bounded(client.connect())
        if not await _bounded(client.is_user_authorized(), timeout=4):
            raise RuntimeError("Telegram Analytics session не авторизована.")

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
            admins = await _bounded(
                client.get_participants(entity, limit=200, filter=types.ChannelParticipantsAdmins),
                timeout=8,
            )
            for user in list(admins or []):
                uid = int(getattr(user, "id", 0) or 0)
                if uid:
                    admin_ids.add(uid)
                    admin_names[uid] = display_user(user)
            if admin_ids:
                meta["editor_coverage"] = "all_admins"
            else:
                meta["editor_coverage"] = "operator_only_fallback"
                if self_id:
                    admin_ids.add(self_id)
                    admin_names[self_id] = display_user(me)
                meta["warning"] = "Telegram не повернув список адмінів; редакторський сигнал тимчасово обмежений підключеним акаунтом."
        except Exception as exc:
            meta["editor_coverage"] = "operator_only_fallback"
            if self_id:
                admin_ids.add(self_id)
                admin_names[self_id] = display_user(me)
            meta["warning"] = f"Не вдалося отримати повний список адмінів: {type(exc).__name__}."
        meta["admin_count"] = len(admin_ids)

        ids: list[int] = []
        by_id: dict[int, dict[str, Any]] = {}
        for row in rows:
            try:
                mid = int(str(row.get("telegram_message_id") or ""))
            except Exception:
                continue
            ids.append(mid)
            by_id[mid] = row

        messages: list[Any] = []
        for offset in range(0, len(ids), MESSAGE_CHUNK_SIZE):
            chunk = ids[offset : offset + MESSAGE_CHUNK_SIZE]
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

        snapshots = []
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
                    editor_reactions, scanned, scan_complete = await scan_admin_reactors(
                        client,
                        input_peer=input_peer,
                        message_id=mid,
                        admin_ids=admin_ids,
                        channel_peer_id=channel_peer_id,
                    )
                except Exception as exc:
                    scan_complete = False
                    if not meta.get("warning"):
                        meta["warning"] = f"Частину реакторів Telegram не дозволив прочитати: {type(exc).__name__}."

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
            snapshots.append(
                build_snapshot(
                    row=row,
                    message=message,
                    editor_reactions=editor_reactions,
                    admin_names=admin_names,
                    admin_count=int(meta.get("admin_count") or 0),
                    coverage=coverage,
                    scan_complete=scan_complete,
                    scanned=scanned,
                )
            )
            meta["reactor_scanned"] = int(meta.get("reactor_scanned") or 0) + scanned
        return snapshots, meta
    finally:
        try:
            result = client.disconnect()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=2)
        except Exception:
            pass


def _run_fetch(**kwargs):
    async def runner():
        return await asyncio.wait_for(fetch_snapshots_async(**kwargs), timeout=TOTAL_TIMEOUT_SECONDS)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(runner())
    raise RuntimeError("Telegram feedback refresh має виконуватися у фоновому потоці.")


def refresh_feedback_metrics_rc57(db, channel, *, force: bool = False, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    channel_id = int(getattr(channel, "id", 0) or 0)
    channel_name = str(getattr(channel, "name", "") or channel_id)
    LOG.info("feedback refresh START channel_id=%s channel=%s force=%s", channel_id, channel_name, int(force))

    health = reaction_health()
    if not health.ready:
        LOG.warning("feedback refresh BLOCKED channel_id=%s state=%s detail=%s", channel_id, health.state, health.message)
        return {"configured": False, "checked": 0, "saved": 0, "error": health.message, "elapsed": 0.0}

    rows = db.rc51_feedback_candidates(channel_id, limit=MAX_MANUAL_POSTS if force else MAX_AUTO_POSTS)
    if not rows:
        return {"configured": True, "checked": 0, "saved": 0, "error": "", "elapsed": time.monotonic() - started}

    from .rc51_feedback import _normalize_chat_target
    target = _normalize_chat_target(str(getattr(channel, "telegram_chat_id", "") or ""))
    if not target:
        return {"configured": True, "checked": 0, "saved": 0, "error": "Порожній Telegram target каналу.", "elapsed": time.monotonic() - started}

    secrets = load_secrets()
    try:
        snapshots, meta = _run_fetch(
            session=str(getattr(secrets, "telegram_user_session", "") or ""),
            api_id=int(getattr(secrets, "telegram_api_id", 0) or 0),
            api_hash=str(getattr(secrets, "telegram_api_hash", "") or ""),
            target=target,
            rows=rows,
            progress=progress,
        )
        if progress:
            progress("зберігаю editor + audience статистику…")
        db.rc57_save_snapshot_batch(channel_id, snapshots)
        elapsed = time.monotonic() - started
        summary = {
            "configured": True,
            "checked": len(snapshots),
            "saved": len(snapshots),
            "error": "",
            "elapsed": elapsed,
            "admin_count": int(meta.get("admin_count") or 0),
            "editor_coverage": str(meta.get("editor_coverage") or "unknown"),
            "reactor_scanned": int(meta.get("reactor_scanned") or 0),
            "warning": str(meta.get("warning") or ""),
        }
        LOG.info(
            "feedback refresh PASS channel_id=%s channel=%s posts=%s admins=%s coverage=%s reactors=%s elapsed=%.2fs warning=%s",
            channel_id, channel_name, len(snapshots), summary["admin_count"], summary["editor_coverage"],
            summary["reactor_scanned"], elapsed, summary["warning"],
        )
        return summary
    except (TimeoutError, asyncio.TimeoutError):
        elapsed = time.monotonic() - started
        text = f"Telegram feedback не завершився за {TOTAL_TIMEOUT_SECONDS} с. Операцію завершено без зависання UI."
        LOG.error("feedback refresh TIMEOUT channel_id=%s channel=%s elapsed=%.2fs", channel_id, channel_name, elapsed)
        return {"configured": True, "checked": 0, "saved": 0, "error": text, "elapsed": elapsed}
    except sqlite3.OperationalError as exc:
        elapsed = time.monotonic() - started
        text = f"SQLite зайнята під час збереження feedback: {exc}"
        LOG.error("feedback refresh DB_FAIL channel_id=%s elapsed=%.2fs error=%s", channel_id, elapsed, exc)
        return {"configured": True, "checked": 0, "saved": 0, "error": text, "elapsed": elapsed}
    except Exception as exc:
        elapsed = time.monotonic() - started
        LOG.exception("feedback refresh FAIL channel_id=%s channel=%s elapsed=%.2fs", channel_id, channel_name, elapsed)
        return {"configured": True, "checked": 0, "saved": 0, "error": str(exc)[:1000] or type(exc).__name__, "elapsed": elapsed}
