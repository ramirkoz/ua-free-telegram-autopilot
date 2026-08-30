from __future__ import annotations

import asyncio
import inspect
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any

from . import APP_NAME
from .rc53_hardening import operator_reaction_breakdown
from .secrets_store import load_secrets

_INSTALLED = False
_INFLIGHT_ATTR = "_rc56_reaction_refresh_inflight"
TOTAL_TIMEOUT_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 8
MESSAGE_CHUNK_SIZE = 40


def _normalize_target(value: str):
    from .rc51_feedback import _normalize_chat_target
    return _normalize_chat_target(value)


async def _await_bounded(awaitable, *, timeout: int = REQUEST_TIMEOUT_SECONDS):
    return await asyncio.wait_for(awaitable, timeout=max(1, int(timeout)))


async def _fetch_messages_async(
    *,
    session: str,
    api_id: int,
    api_hash: str,
    target: Any,
    ids: list[int],
    progress: Callable[[str], None] | None = None,
) -> list[Any]:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except Exception as exc:
        raise RuntimeError("Не встановлено модуль Telethon для Telegram Analytics.") from exc

    def report(text: str) -> None:
        if progress is not None:
            try:
                progress(text)
            except Exception:
                pass

    client = TelegramClient(
        StringSession(str(session or "")),
        int(api_id),
        str(api_hash or "").strip(),
        connection_retries=1,
        request_retries=1,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        report("підключаюсь до Telegram…")
        await _await_bounded(client.connect())
        if not await _await_bounded(client.is_user_authorized(), timeout=5):
            raise RuntimeError("Telegram Analytics session не авторизована.")

        report("Telegram OK · відкриваю канал…")
        entity = await _await_bounded(client.get_entity(target))

        messages: list[Any] = []
        total = len(ids)
        for offset in range(0, total, MESSAGE_CHUNK_SIZE):
            chunk = ids[offset : offset + MESSAGE_CHUNK_SIZE]
            report(f"читаю реакції {min(offset + len(chunk), total)}/{total}…")
            part = await _await_bounded(client.get_messages(entity, ids=chunk))
            if part is None:
                continue
            if isinstance(part, (list, tuple)):
                messages.extend(part)
            else:
                try:
                    messages.extend(list(part))
                except TypeError:
                    messages.append(part)
        return messages
    finally:
        try:
            result = client.disconnect()
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=3)
        except Exception:
            pass


def _run_fetch(**kwargs) -> list[Any]:
    async def bounded():
        return await asyncio.wait_for(
            _fetch_messages_async(**kwargs), timeout=TOTAL_TIMEOUT_SECONDS
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(bounded())
    raise RuntimeError("Telegram refresh має виконуватися у фоновому потоці без активного asyncio loop.")


def refresh_feedback_metrics_rc56(
    db,
    channel,
    *,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    secrets = load_secrets()
    if not (
        int(getattr(secrets, "telegram_api_id", 0) or 0)
        and str(getattr(secrets, "telegram_api_hash", "") or "").strip()
        and str(getattr(secrets, "telegram_user_session", "") or "").strip()
    ):
        return {
            "configured": False,
            "checked": 0,
            "saved": 0,
            "error": "Telegram user-session не авторизована.",
            "policy_warning": "",
        }

    rows = db.rc51_feedback_candidates(int(channel.id), limit=120 if force else 80)
    if not rows:
        return {
            "configured": True,
            "checked": 0,
            "saved": 0,
            "error": "",
            "policy_warning": "",
        }

    target = _normalize_target(str(getattr(channel, "telegram_chat_id", "") or ""))
    if not target:
        return {
            "configured": True,
            "checked": 0,
            "saved": 0,
            "error": "Порожній Telegram target каналу.",
            "policy_warning": "",
        }

    ids: list[int] = []
    by_id: dict[int, dict[str, object]] = {}
    for row in rows:
        try:
            message_id = int(str(row["telegram_message_id"]))
        except Exception:
            continue
        ids.append(message_id)
        by_id[message_id] = row

    if not ids:
        return {
            "configured": True,
            "checked": 0,
            "saved": 0,
            "error": "",
            "policy_warning": "",
        }

    try:
        messages = _run_fetch(
            session=str(secrets.telegram_user_session),
            api_id=int(secrets.telegram_api_id),
            api_hash=str(secrets.telegram_api_hash),
            target=target,
            ids=ids,
            progress=progress,
        )
    except TimeoutError:
        return {
            "configured": True,
            "checked": 0,
            "saved": 0,
            "error": (
                f"Telegram не завершив читання реакцій за {TOTAL_TIMEOUT_SECONDS} с. "
                "Операцію зупинено; інтерфейс розблоковано."
            ),
            "policy_warning": "",
        }
    except asyncio.TimeoutError:
        return {
            "configured": True,
            "checked": 0,
            "saved": 0,
            "error": (
                f"Telegram не завершив читання реакцій за {TOTAL_TIMEOUT_SECONDS} с. "
                "Операцію зупинено; інтерфейс розблоковано."
            ),
            "policy_warning": "",
        }
    except Exception as exc:
        return {
            "configured": True,
            "checked": 0,
            "saved": 0,
            "error": str(exc)[:1000] or exc.__class__.__name__,
            "policy_warning": "",
        }

    checked = 0
    saved = 0
    for message in messages:
        if message is None:
            continue
        message_id = int(getattr(message, "id", 0) or 0)
        row = by_id.get(message_id)
        if row is None:
            continue
        checked += 1
        views, forwards, replies, likes, dislikes, fires, other = operator_reaction_breakdown(message)
        db.rc51_save_feedback(
            channel_id=int(channel.id),
            article_id=int(row["article_id"]),
            telegram_message_id=str(message_id),
            published_at=str(row.get("published_at") or ""),
            views=views,
            forwards=forwards,
            replies=replies,
            likes=likes,
            dislikes=dislikes,
            fires=fires,
            other_reactions=other,
        )
        saved += 1

    return {
        "configured": True,
        "checked": checked,
        "saved": saved,
        "error": "",
        "policy_warning": "",
    }


def _status_var(main_window):
    return getattr(main_window, "rc51_feedback_status", None) or getattr(
        main_window, "rc48_memory_status", None
    )


def _queue_status(main_window, channel_name: str, text: str) -> None:
    def apply() -> None:
        status = _status_var(main_window)
        if status is not None:
            status.set(f"{channel_name}: {text}")

    try:
        main_window._ui_queue.put(apply)
    except Exception:
        pass


def refresh_metrics_now_rc56(main_window) -> None:
    channel_id = int(getattr(main_window, "current_channel_id", 0) or 0)
    if not channel_id:
        messagebox.showwarning(APP_NAME, "Спочатку оберіть канал.", parent=main_window.root)
        return
    channel = main_window.db.get_channel(channel_id)
    if channel is None:
        return

    status = _status_var(main_window)
    if bool(getattr(main_window, _INFLIGHT_ATTR, False)):
        if status is not None:
            status.set(
                f"{channel.name}: попереднє читання реакцій ще виконується; "
                f"максимальний час — {TOTAL_TIMEOUT_SECONDS} с."
            )
        return

    setattr(main_window, _INFLIGHT_ATTR, True)
    if status is not None:
        status.set(
            f"{channel.name}: підключаюсь до Telegram · максимум {TOTAL_TIMEOUT_SECONDS} с…"
        )

    def worker() -> None:
        try:
            summary = refresh_feedback_metrics_rc56(
                main_window.db,
                channel,
                force=True,
                progress=lambda text: _queue_status(main_window, channel.name, text),
            )
        except Exception as exc:
            summary = {
                "configured": True,
                "checked": 0,
                "saved": 0,
                "error": str(exc) or exc.__class__.__name__,
                "policy_warning": "",
            }

        def finish() -> None:
            setattr(main_window, _INFLIGHT_ATTR, False)
            try:
                main_window._rc48_refresh_memory()
            except Exception:
                pass

            current_status = _status_var(main_window)
            if summary.get("error"):
                if current_status is not None:
                    current_status.set(f"{channel.name}: ❌ {summary.get('error')}")
                messagebox.showwarning(
                    APP_NAME,
                    "Telegram Analytics: " + str(summary.get("error")),
                    parent=main_window.root,
                )
                return

            checked = int(summary.get("checked", 0) or 0)
            saved = int(summary.get("saved", 0) or 0)
            if current_status is not None:
                current_status.set(
                    f"{channel.name}: ✅ реакції оновлено · перевірено {checked} · записано {saved}"
                )
            messagebox.showinfo(
                APP_NAME,
                f"Реакції оновлено. Перевірено постів: {checked}; оновлено записів: {saved}.",
                parent=main_window.root,
            )

        try:
            main_window._ui_queue.put(finish)
        except Exception:
            setattr(main_window, _INFLIGHT_ATTR, False)

    threading.Thread(target=worker, name="RC56ReactionRefresh", daemon=True).start()


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for child in children:
        yield from _walk(child)


def _clean_memory_copy(tab) -> None:
    main_explainer = (
        "👍 = цікава тема: схожі матеріали отримують пріоритет. "
        "👎 = тема/сюжет нецікаві: дуже схожі матеріали тимчасово знижуються або пропускаються. "
        "🔥 = текст добре написаний: пост стає прикладом стилю для автора. "
        "На один пост можна ставити дві реакції, тому 👍+🔥 означає «і тема, і текст», "
        "а 👎+🔥 — «тема не потрібна, але написано добре». Відсутність реакції нейтральна. "
        "Вікно навчання — 7 днів."
    )
    memory_note = (
        "Реакційне навчання використовує тільки реакції, вибрані підключеним Telegram-акаунтом, "
        "а не загальний лічильник аудиторії. MTProto user-session має бути авторизована."
    )
    for widget in _walk(tab):
        if not isinstance(widget, ttk.Label):
            continue
        try:
            text = str(widget.cget("text") or "")
        except Exception:
            continue
        if text.startswith("RC52 розділяє два незалежні сигнали"):
            widget.configure(text=main_explainer)
        elif text.startswith("RC53: реакційне навчання"):
            widget.configure(text=memory_note)


def _analytics_dialog_rc56(parent, main_window) -> None:
    from . import rc54_mtproto

    before = {str(w) for w in parent.winfo_children()}
    rc54_mtproto._analytics_dialog_rc54(parent, main_window)
    candidates = [
        w for w in parent.winfo_children()
        if isinstance(w, tk.Toplevel) and str(w) not in before and w.winfo_exists()
    ]
    if not candidates:
        return
    win = candidates[-1]
    try:
        win.title("Telegram reactions")
    except Exception:
        pass
    for widget in _walk(win):
        if not isinstance(widget, ttk.Label):
            continue
        try:
            text = str(widget.cget("text") or "")
        except Exception:
            continue
        if text.startswith("RC54 читає тільки реакції"):
            widget.configure(
                text=(
                    "Програма читає тільки реакції, які вибрав підключений Telegram-акаунт. "
                    "👍/👎 керують темою, 🔥 — стилем; Premium-комбінації зберігаються незалежно."
                )
            )


def install_rc56_reaction_runtime() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import rc48_learning, rc48_ui, rc51_feedback, rc51_ui, rc52_ui, rc53_ui, rc54_mtproto
    from .ui import MainWindow

    # Refresh transport: one bounded, read-only implementation everywhere.
    rc48_learning.refresh_channel_metrics = refresh_feedback_metrics_rc56
    rc51_feedback.refresh_feedback_metrics = refresh_feedback_metrics_rc56
    rc48_ui.refresh_channel_metrics = refresh_feedback_metrics_rc56
    rc51_ui.refresh_feedback_metrics = refresh_feedback_metrics_rc56
    rc54_mtproto.refresh_feedback_metrics_rc54 = refresh_feedback_metrics_rc56
    MainWindow._rc48_refresh_metrics_now = refresh_metrics_now_rc56

    # Version-neutral UI copy. Historical module names remain internal only.
    old_build = MainWindow._build

    def build_rc56(self):
        old_build(self)
        tab = getattr(self, "memory_tab", None)
        if tab is not None:
            _clean_memory_copy(tab)
        for widget in _walk(tab) if tab is not None else []:
            if isinstance(widget, ttk.Button):
                try:
                    text = str(widget.cget("text") or "")
                except Exception:
                    continue
                if "Налаштувати Telegram Analytics" in text:
                    widget.configure(command=lambda: _analytics_dialog_rc56(self.root, self))

    rc48_ui._analytics_dialog = _analytics_dialog_rc56
    rc51_ui._analytics_dialog = _analytics_dialog_rc56
    rc52_ui._analytics_dialog = _analytics_dialog_rc56
    rc53_ui._analytics_dialog_rc53 = _analytics_dialog_rc56
    MainWindow._build = build_rc56

    _INSTALLED = True
