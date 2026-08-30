from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import APP_NAME
from . import rc51_feedback as rc51
from .rc48_learning import authorize_telegram_analytics
from .rc53_hardening import reaction_health
from .secrets_store import load_secrets, save_secrets

_INSTALLED = False


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for child in children:
        yield from _walk(child)


def _analytics_dialog_rc53(parent, main_window) -> None:
    win = tk.Toplevel(parent)
    win.title("Telegram reactions · RC53")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    secret = load_secrets()
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text=(
            "RC53 читає саме реакції, ВИБРАНІ підключеним Telegram-акаунтом. "
            "Сумарні реакції аудиторії не навчають автопілот. 👍/👎 керують темою, 🔥 — стилем. "
            "Telegram Premium дозволяє поставити на один пост кілька реакцій, тому 👍+🔥 і 👎+🔥 "
            "зберігаються як два незалежні сигнали."
        ),
        wraplength=660, justify="left", foreground="#444",
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
            "Bot Token як і раніше лише публікує. Для читання ваших реакцій потрібна окрема "
            "MTProto user-session. API Hash і user-session зберігаються в AES-GCM сховищі Data."
        ),
        wraplength=660, justify="left", foreground="#666",
    ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(3, 10))

    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))

    def save_fields(*, session: str | None = None) -> None:
        current = load_secrets()
        try:
            parsed_id = int(api_id.get().strip() or "0")
        except ValueError as exc:
            raise ValueError("Telegram API ID має бути цілим числом.") from exc
        current.telegram_api_id = parsed_id
        current.telegram_api_hash = api_hash.get().strip()
        current.telegram_phone = phone.get().strip()
        if session is not None:
            current.telegram_user_session = session
        save_secrets(current)

    def refresh_after_auth() -> None:
        channel_id = int(getattr(main_window, "current_channel_id", 0) or 0)
        if not channel_id:
            status.set("✅ User-session авторизована. Оберіть канал і натисніть «Оновити реакції зараз».")
            try:
                main_window._rc48_refresh_memory()
            except Exception:
                pass
            return
        channel = main_window.db.get_channel(channel_id)
        if channel is None:
            return
        status.set("✅ Сесію збережено. Читаю ваші 👍 / 👎 / 🔥 з поточного каналу…")

        def worker():
            summary = rc51.refresh_feedback_metrics(main_window.db, channel, force=True)

            def finish():
                try:
                    main_window._rc48_refresh_memory()
                except Exception:
                    pass
                if summary.get("error"):
                    status.set("❌ " + str(summary.get("error")))
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

        threading.Thread(target=worker, name="RC53ReactionBootstrap", daemon=True).start()

    def save_only() -> None:
        try:
            save_fields()
            health_now = reaction_health()
            status.set(("✅ " if health_now.ready else "❌ ") + health_now.message)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)

    def authorize() -> None:
        try:
            parsed_id = int(api_id.get().strip() or "0")
            hash_value = api_hash.get().strip()
            phone_value = phone.get().strip()
            current = load_secrets()

            def code_callback():
                return simpledialog.askstring(
                    APP_NAME,
                    "Введіть код, який Telegram щойно надіслав цьому акаунту:",
                    parent=win,
                ) or ""

            def password_callback():
                return simpledialog.askstring(
                    APP_NAME,
                    "Увімкнено двоетапну перевірку. Введіть пароль Telegram:",
                    parent=win, show="•",
                ) or ""

            session, display = authorize_telegram_analytics(
                api_id=parsed_id,
                api_hash=hash_value,
                phone=phone_value,
                existing_session=str(getattr(current, "telegram_user_session", "") or ""),
                code_callback=code_callback,
                password_callback=password_callback,
            )
            save_fields(session=session)
            status.set(f"✅ Авторизовано: {display}. Перевіряю реакції…")
            refresh_after_auth()
        except Exception as exc:
            status.set("❌ Авторизація не завершена.")
            messagebox.showerror(APP_NAME, str(exc), parent=win)

    ttk.Button(buttons, text="Зберегти", command=save_only).pack(side="right")
    ttk.Button(buttons, text="Авторизувати Telegram", command=authorize).pack(side="right", padx=(0, 7))
    ttk.Button(buttons, text="Закрити", command=win.destroy).pack(side="right", padx=(0, 7))


def install_rc53_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from .ui import MainWindow
    from . import rc48_ui, rc51_ui, rc52_ui

    old_build = MainWindow._build
    old_refresh_memory = MainWindow._rc48_refresh_memory

    def build_rc53(self):
        old_build(self)
        tab = getattr(self, "memory_tab", None)
        if tab is None:
            return
        for widget in _walk(tab):
            if isinstance(widget, ttk.Button):
                try:
                    text = str(widget.cget("text") or "")
                except Exception:
                    continue
                if "Налаштувати Telegram Analytics" in text:
                    widget.configure(command=lambda: _analytics_dialog_rc53(self.root, self))
        ttk.Label(
            tab,
            text=(
                "RC53: реакційне навчання використовує тільки ваші вибрані реакції, а не загальний лічильник аудиторії. "
                "Якщо MTProto user-session не авторизована, інтерфейс показує це як помилку, а не як «нейтральне навчання»."
            ),
            wraplength=1080, justify="left", foreground="#555",
        ).pack(anchor="w", pady=(8, 0))

    def refresh_memory_rc53(self):
        old_refresh_memory(self)
        health = reaction_health()
        if health.ready:
            current = str(self.rc51_feedback_status.get() or "")
            if "MTProto OK" not in current:
                self.rc51_feedback_status.set("MTProto OK · " + current)
            return
        channel = self.db.get_channel(int(self.current_channel_id or 0)) if self.current_channel_id else None
        prefix = (str(getattr(channel, "name", "") or "") + ": ") if channel else ""
        self.rc51_feedback_status.set(prefix + "❌ НАВЧАННЯ НЕ ПРАЦЮЄ · " + health.message)
        self.rc51_feedback_note.set(
            "Відкрийте «Налаштувати Telegram Analytics» і завершіть авторизацію user-session. "
            "До цього 👍/👎/🔥 не можуть впливати на відбір або стиль."
        )

    def refresh_metrics_now_rc53(self):
        channel_id = int(self.current_channel_id or 0)
        if not channel_id:
            messagebox.showwarning(APP_NAME, "Спочатку оберіть канал.", parent=self.root)
            return
        health = reaction_health()
        if not health.ready:
            _analytics_dialog_rc53(self.root, self)
            return
        channel = self.db.get_channel(channel_id)
        if channel is None:
            return
        self.rc51_feedback_status.set(f"{channel.name}: читаю ваші 👍 / 👎 / 🔥 з Telegram…")

        def worker():
            summary = rc51.refresh_feedback_metrics(self.db, channel, force=True)

            def finish():
                self._rc48_refresh_memory()
                if summary.get("error"):
                    messagebox.showwarning(APP_NAME, "Telegram reactions: " + str(summary.get("error")), parent=self.root)
                else:
                    text = (
                        f"Перевірено постів: {summary.get('checked', 0)}; "
                        f"оновлено операторських реакцій: {summary.get('saved', 0)}."
                    )
                    if summary.get("policy_warning"):
                        text += (
                            "\n\nРеакції прочитані, але Telegram не дозволив автоматично "
                            "обмежити меню каналу до 👍 👎 🔥: " + str(summary.get("policy_warning"))
                        )
                    messagebox.showinfo(APP_NAME, text, parent=self.root)

            try:
                self._ui_queue.put(finish)
            except Exception:
                pass

        threading.Thread(target=worker, name="RC53Feedback", daemon=True).start()

    rc48_ui._analytics_dialog = _analytics_dialog_rc53
    rc51_ui._analytics_dialog = _analytics_dialog_rc53
    rc52_ui._analytics_dialog = _analytics_dialog_rc53
    MainWindow._build = build_rc53
    MainWindow._rc48_refresh_memory = refresh_memory_rc53
    MainWindow._rc48_refresh_metrics_now = refresh_metrics_now_rc53
    _INSTALLED = True
