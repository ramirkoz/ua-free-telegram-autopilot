from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from contextlib import contextmanager
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Iterator

from . import APP_NAME
from .secrets_store import load_secrets, save_secrets

_INSTALLED = False


@contextmanager
def _sync_client(
    *,
    session: str,
    api_id: int,
    api_hash: str,
    timeout: int = 15,
) -> Iterator[Any]:
    """Blocking Telethon client with a real event loop in worker threads."""
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
    except Exception as exc:
        raise RuntimeError("Не встановлено модуль Telethon для Telegram Analytics.") from exc

    owned_loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed():
        owned_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(owned_loop)
        loop = owned_loop
    if loop.is_running():
        raise RuntimeError("MTProto sync-клієнт запущено всередині активного asyncio loop.")

    client = TelegramClient(
        StringSession(str(session or "")),
        int(api_id),
        str(api_hash or "").strip(),
        connection_retries=1,
        request_retries=1,
        timeout=max(1, int(timeout)),
    )
    try:
        client.connect()
        yield client
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


def authorize_telegram_analytics_rc54(
    *,
    api_id: int,
    api_hash: str,
    phone: str,
    existing_session: str = "",
    code_callback,
    password_callback,
) -> tuple[str, str]:
    try:
        from telethon.errors import SessionPasswordNeededError
    except Exception as exc:
        raise RuntimeError("Не встановлено модуль Telethon для Telegram Analytics.") from exc

    api_id = int(api_id)
    api_hash = str(api_hash or "").strip()
    phone = str(phone or "").strip()
    if api_id <= 0 or not api_hash:
        raise ValueError("Вкажіть коректні Telegram API ID та API Hash.")
    if not phone:
        raise ValueError("Вкажіть номер телефону Telegram-акаунта.")

    with _sync_client(
        session=str(existing_session or ""),
        api_id=api_id,
        api_hash=api_hash,
        timeout=15,
    ) as client:
        if not client.is_user_authorized():
            sent = client.send_code_request(phone)
            code = str(code_callback() or "").strip()
            if not code:
                raise RuntimeError("Авторизацію скасовано: код Telegram не введено.")
            try:
                client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = str(password_callback() or "")
                if not password:
                    raise RuntimeError("Для акаунта увімкнено 2FA, але пароль не введено.")
                client.sign_in(password=password)

        if not client.is_user_authorized():
            raise RuntimeError("Telegram не підтвердив авторизацію user-session.")
        session = str(client.session.save() or "").strip()
        if not session:
            raise RuntimeError("Telegram авторизував акаунт, але StringSession не була створена.")
        me = client.get_me()
        display = ""
        if me is not None:
            display = " ".join(
                part
                for part in (
                    str(getattr(me, "first_name", "") or ""),
                    str(getattr(me, "last_name", "") or ""),
                )
                if part
            ).strip()
            username = str(getattr(me, "username", "") or "").strip()
            if username:
                display = (display + f" (@{username})").strip()
        return session, display or "Telegram-акаунт"


def refresh_feedback_metrics_rc54(db, channel, *, force: bool = False) -> dict[str, object]:
    from . import rc51_feedback as rc51
    from .rc53_hardening import operator_reaction_breakdown

    secrets = load_secrets()
    if not (
        int(getattr(secrets, "telegram_api_id", 0) or 0)
        and str(getattr(secrets, "telegram_api_hash", "") or "").strip()
        and str(getattr(secrets, "telegram_user_session", "") or "").strip()
    ):
        return {
            "configured": False, "checked": 0, "saved": 0,
            "error": "Telegram user-session не авторизована.", "policy_warning": "",
        }

    rows = db.rc51_feedback_candidates(int(channel.id), limit=180 if force else 120)
    if not rows:
        return {"configured": True, "checked": 0, "saved": 0, "error": "", "policy_warning": ""}

    target = rc51._normalize_chat_target(str(getattr(channel, "telegram_chat_id", "") or ""))
    if not target:
        return {
            "configured": True, "checked": 0, "saved": 0,
            "error": "Порожній Telegram target каналу.", "policy_warning": "",
        }

    checked = saved = 0
    policy_warning = ""
    try:
        with _sync_client(
            session=str(secrets.telegram_user_session),
            api_id=int(secrets.telegram_api_id),
            api_hash=str(secrets.telegram_api_hash),
            timeout=12,
        ) as client:
            if not client.is_user_authorized():
                return {
                    "configured": True, "checked": 0, "saved": 0,
                    "error": "Telegram Analytics session не авторизована.", "policy_warning": "",
                }
            entity = client.get_entity(target)
            if force or int(channel.id) not in rc51._REACTION_POLICY_LAST:
                policy_warning = rc51._try_limit_channel_reactions(client, entity, int(channel.id))

            by_id: dict[int, dict[str, object]] = {}
            ids: list[int] = []
            for row in rows:
                try:
                    message_id = int(str(row["telegram_message_id"]))
                except Exception:
                    continue
                ids.append(message_id)
                by_id[message_id] = row

            messages = client.get_messages(entity, ids=ids) if ids else []
            if messages is None:
                messages = []
            if not isinstance(messages, (list, tuple)):
                try:
                    messages = list(messages)
                except TypeError:
                    messages = [messages]

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
            "configured": True, "checked": checked, "saved": saved,
            "error": "", "policy_warning": policy_warning,
        }
    except Exception as exc:
        return {
            "configured": True, "checked": checked, "saved": saved,
            "error": str(exc)[:1000], "policy_warning": policy_warning,
        }


def _analytics_dialog_rc54(parent, main_window) -> None:
    from .rc53_hardening import reaction_health

    win = tk.Toplevel(parent)
    win.title("Telegram reactions · RC54")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    secret = load_secrets()
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text=(
            "RC54 читає тільки реакції, які вибрав підключений Telegram-акаунт. "
            "👍/👎 керують темою, 🔥 — стилем; Premium-комбінації зберігаються незалежно."
        ),
        wraplength=660,
        justify="left",
        foreground="#444",
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

    ttk.Label(frame, text="Telegram API ID").grid(row=1, column=0, sticky="w", pady=4)
    api_id = ttk.Entry(frame, width=42)
    api_id.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)
    if int(getattr(secret, "telegram_api_id", 0) or 0):
        api_id.insert(0, str(secret.telegram_api_id))

    ttk.Label(frame, text="Telegram API Hash").grid(row=2, column=0, sticky="w", pady=4)
    api_hash = ttk.Entry(frame, width=42, show="•")
    api_hash.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=4)
    api_hash.insert(0, str(getattr(secret, "telegram_api_hash", "") or ""))

    ttk.Label(frame, text="Телефон акаунта").grid(row=3, column=0, sticky="w", pady=4)
    phone = ttk.Entry(frame, width=42)
    phone.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=4)
    phone.insert(0, str(getattr(secret, "telegram_phone", "") or ""))

    health = reaction_health()
    status = tk.StringVar(value=("✅ " if health.ready else "❌ ") + health.message)
    ttk.Label(frame, textvariable=status, wraplength=660, justify="left").grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(10, 5)
    )
    ttk.Label(
        frame,
        text=(
            "Після натискання «Авторизувати Telegram» тут одразу з'явиться стан підключення. "
            "Потім Telegram надішле код, і програма відкриє окреме вікно для його введення."
        ),
        wraplength=660,
        justify="left",
        foreground="#666",
    ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(3, 10))

    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))

    def save_values(session: str | None = None) -> None:
        current = load_secrets()
        current.telegram_api_id = int(api_id.get().strip() or "0")
        current.telegram_api_hash = api_hash.get().strip()
        current.telegram_phone = phone.get().strip()
        if session is not None:
            current.telegram_user_session = session
        save_secrets(current)

    def prompt_from_worker(prompt: str, *, password: bool = False) -> str:
        event = threading.Event()
        result = {"value": ""}

        def ask() -> None:
            try:
                status.set("📨 Telegram надіслав код. Введіть його у відкритому вікні.")
                kwargs = {"parent": win}
                if password:
                    kwargs["show"] = "•"
                result["value"] = simpledialog.askstring(APP_NAME, prompt, **kwargs) or ""
            finally:
                event.set()

        try:
            win.after(0, ask)
        except tk.TclError:
            return ""
        if not event.wait(timeout=300):
            return ""
        return str(result["value"] or "")

    def refresh_after_auth() -> None:
        channel_id = int(getattr(main_window, "current_channel_id", 0) or 0)
        if not channel_id:
            status.set("✅ MTProto OK. Оберіть канал і натисніть «Оновити реакції зараз».")
            return
        channel = main_window.db.get_channel(channel_id)
        if channel is None:
            status.set("✅ MTProto OK. Поточний канал не знайдено.")
            return
        status.set("✅ MTProto OK. Читаю ваші 👍 / 👎 / 🔥…")

        def worker() -> None:
            summary = refresh_feedback_metrics_rc54(main_window.db, channel, force=True)

            def finish() -> None:
                try:
                    main_window._rc48_refresh_memory()
                except Exception:
                    pass
                if summary.get("error"):
                    status.set("❌ " + str(summary["error"]))
                else:
                    status.set(
                        "✅ Реакційний контур працює. "
                        f"Перевірено постів: {summary.get('checked', 0)}; "
                        f"збережено міток: {summary.get('saved', 0)}."
                    )

            try:
                win.after(0, finish)
            except tk.TclError:
                pass

        threading.Thread(target=worker, name="RC54ReactionBootstrap", daemon=True).start()

    def save_only() -> None:
        try:
            save_values()
            health_now = reaction_health()
            status.set(("✅ " if health_now.ready else "❌ ") + health_now.message)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)

    def authorize() -> None:
        try:
            parsed_id = int(api_id.get().strip() or "0")
        except ValueError:
            messagebox.showerror(APP_NAME, "Telegram API ID має бути цілим числом.", parent=win)
            return
        hash_value = api_hash.get().strip()
        phone_value = phone.get().strip()
        if parsed_id <= 0 or not hash_value or not phone_value:
            messagebox.showerror(APP_NAME, "Заповніть API ID, API Hash і телефон.", parent=win)
            return

        existing_session = str(getattr(load_secrets(), "telegram_user_session", "") or "")
        status.set("⏳ Підключаюсь до Telegram…")
        auth_button.configure(state="disabled")
        save_button.configure(state="disabled")

        def worker() -> None:
            try:
                session, display = authorize_telegram_analytics_rc54(
                    api_id=parsed_id,
                    api_hash=hash_value,
                    phone=phone_value,
                    existing_session=existing_session,
                    code_callback=lambda: prompt_from_worker(
                        "Введіть код, який Telegram щойно надіслав цьому акаунту:"
                    ),
                    password_callback=lambda: prompt_from_worker(
                        "Увімкнено 2FA. Введіть пароль Telegram:", password=True
                    ),
                )
                def ok() -> None:
                    try:
                        save_values(session=session)
                        status.set(f"✅ Авторизовано: {display}. Перевіряю реакції…")
                        refresh_after_auth()
                    except Exception as exc:
                        status.set("❌ Не вдалося зберегти user-session.")
                        messagebox.showerror(APP_NAME, str(exc), parent=win)
                    finally:
                        auth_button.configure(state="normal")
                        save_button.configure(state="normal")
                win.after(0, ok)
            except Exception as exc:
                text = str(exc) or exc.__class__.__name__
                def fail() -> None:
                    status.set("❌ Авторизація не завершена: " + text[:220])
                    auth_button.configure(state="normal")
                    save_button.configure(state="normal")
                    messagebox.showerror(APP_NAME, text, parent=win)
                try:
                    win.after(0, fail)
                except tk.TclError:
                    pass

        threading.Thread(target=worker, name="RC54TelegramAuthorization", daemon=True).start()

    save_button = ttk.Button(buttons, text="Зберегти", command=save_only)
    save_button.pack(side="right")
    auth_button = ttk.Button(buttons, text="Авторизувати Telegram", command=authorize)
    auth_button.pack(side="right", padx=(0, 7))
    ttk.Button(buttons, text="Закрити", command=win.destroy).pack(side="right", padx=(0, 7))


def install_rc54_mtproto() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import rc48_learning as rc48
    from . import rc48_ui, rc51_feedback as rc51, rc51_ui, rc52_ui, rc53_ui

    rc48.authorize_telegram_analytics = authorize_telegram_analytics_rc54
    rc48.refresh_channel_metrics = refresh_feedback_metrics_rc54
    rc51.refresh_feedback_metrics = refresh_feedback_metrics_rc54

    rc53_ui.authorize_telegram_analytics = authorize_telegram_analytics_rc54
    rc53_ui._analytics_dialog_rc53 = _analytics_dialog_rc54
    rc48_ui._analytics_dialog = _analytics_dialog_rc54
    rc51_ui._analytics_dialog = _analytics_dialog_rc54
    rc52_ui._analytics_dialog = _analytics_dialog_rc54

    _INSTALLED = True
