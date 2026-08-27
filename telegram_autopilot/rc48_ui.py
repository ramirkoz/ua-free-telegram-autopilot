from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import APP_NAME
from .rc48_learning import authorize_telegram_analytics, refresh_channel_metrics
from .secrets_store import load_secrets, save_secrets

_INSTALLED = False


def _analytics_dialog(parent, main_window) -> None:
    win = tk.Toplevel(parent)
    win.title("Telegram Analytics · редакційна пам'ять")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    secret = load_secrets()

    frame = ttk.Frame(win, padding=14)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text=(
            "Це окреме READ-ONLY підключення Telegram через MTProto. "
            "Bot Token як і раніше тільки публікує. User-session читає перегляди, "
            "реакції, пересилання та replies опублікованих постів."
        ),
        wraplength=620,
        foreground="#555",
        justify="left",
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    ttk.Label(frame, text="Telegram API ID").grid(row=1, column=0, sticky="w", pady=4)
    api_id = ttk.Entry(frame, width=38)
    api_id.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)
    if int(getattr(secret, "telegram_api_id", 0) or 0):
        api_id.insert(0, str(secret.telegram_api_id))

    ttk.Label(frame, text="Telegram API Hash").grid(row=2, column=0, sticky="w", pady=4)
    api_hash = ttk.Entry(frame, width=38, show="•")
    api_hash.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=4)
    api_hash.insert(0, str(getattr(secret, "telegram_api_hash", "") or ""))

    ttk.Label(frame, text="Телефон акаунта").grid(row=3, column=0, sticky="w", pady=4)
    phone = ttk.Entry(frame, width=38)
    phone.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=4)
    phone.insert(0, str(getattr(secret, "telegram_phone", "") or ""))

    status = tk.StringVar(
        value=(
            "Сесія авторизована."
            if str(getattr(secret, "telegram_user_session", "") or "").strip()
            else "Сесія ще не авторизована."
        )
    )
    ttk.Label(frame, textvariable=status, wraplength=620).grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(10, 4)
    )

    ttk.Label(
        frame,
        text=(
            "API ID / API Hash створюються у Telegram для власного акаунта. "
            "Сесія та API Hash зберігаються у вже наявному AES-GCM сховищі секретів програми."
        ),
        foreground="#666",
        wraplength=620,
        justify="left",
    ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 10))

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

    def save_only() -> None:
        try:
            save_fields()
            status.set("Налаштування збережено.")
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
                    parent=win,
                    show="•",
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
            status.set(f"Авторизовано: {display}")
            messagebox.showinfo(
                APP_NAME,
                "Telegram Analytics підключено. Публікація ботом не змінена.",
                parent=win,
            )
            try:
                main_window._rc48_refresh_memory()
            except Exception:
                pass
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)

    ttk.Button(buttons, text="Зберегти", command=save_only).pack(side="right")
    ttk.Button(buttons, text="Авторизувати Telegram", command=authorize).pack(
        side="right", padx=(0, 7)
    )
    ttk.Button(buttons, text="Закрити", command=win.destroy).pack(
        side="right", padx=(0, 7)
    )


def install_rc48_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from .ui import MainWindow

    old_build = MainWindow._build
    old_refresh_all = MainWindow.refresh_all

    def build_rc48(self):
        old_build(self)

        self.memory_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.memory_tab, text="Редакційна пам'ять")

        top = ttk.Frame(self.memory_tab)
        top.pack(fill="x", pady=(0, 8))

        self.rc48_memory_status = tk.StringVar(value="Редакційна пам'ять: очікує статистику.")
        ttk.Label(top, textvariable=self.rc48_memory_status, font=("Segoe UI", 10, "bold")).pack(
            side="left"
        )
        ttk.Button(
            top,
            text="Налаштувати Telegram Analytics",
            command=lambda: _analytics_dialog(self.root, self),
        ).pack(side="right", padx=4)
        ttk.Button(
            top,
            text="Оновити статистику зараз",
            command=self._rc48_refresh_metrics_now,
        ).pack(side="right", padx=4)

        ttk.Label(
            self.memory_tab,
            text=(
                "Autopilot збирає метрики у контрольні точки 2 / 8 / 24 / 72 / 168 год. "
                "Для еталонів використовуються пости одного каналу з однаковою контрольною точкою. "
                "TOP формується за фактичною кількістю реакцій + пересилань + replies; "
                "при рівності вище стоять пересилання, потім перегляди. "
                "Редакційний профіль та ваги завжди мають вищий пріоритет за пам'ять."
            ),
            wraplength=1080,
            foreground="#555",
            justify="left",
        ).pack(anchor="w", pady=(0, 9))

        cols = ("rank", "title", "checkpoint", "views", "reactions", "forwards", "replies")
        self.rc48_memory_tree = ttk.Treeview(
            self.memory_tab, columns=cols, show="headings", height=18
        )
        heads = (
            "#", "Еталонний пост", "Зріз", "Перегляди", "Реакції", "Пересилання", "Replies"
        )
        widths = (45, 570, 80, 100, 90, 100, 80)
        for col, head, width in zip(cols, heads, widths):
            self.rc48_memory_tree.heading(col, text=head)
            self.rc48_memory_tree.column(
                col, width=width, anchor="w" if col == "title" else "center"
            )
        self.rc48_memory_tree.pack(fill="both", expand=True)

        self.rc48_memory_note = tk.StringVar(value="")
        ttk.Label(
            self.memory_tab,
            textvariable=self.rc48_memory_note,
            foreground="#666",
            wraplength=1080,
        ).pack(anchor="w", pady=(8, 0))

    def refresh_memory(self):
        tree = getattr(self, "rc48_memory_tree", None)
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)

        channel_id = int(self.current_channel_id or 0)
        if not channel_id:
            self.rc48_memory_status.set("Редакційна пам'ять: оберіть канал.")
            self.rc48_memory_note.set("")
            return
        try:
            channel = self.db.get_channel(channel_id)
            snapshot = self.db.rc48_memory_snapshot(channel_id, limit=30)
            stats = self.db.rc48_memory_stats(channel_id)
        except Exception as exc:
            self.rc48_memory_status.set(f"Редакційна пам'ять: {exc}")
            return

        active = bool(stats.get("active"))
        checkpoint = int(stats.get("checkpoint_hours") or 0)
        comparable = int(stats.get("comparable_posts") or 0)
        minimum = int(stats.get("minimum") or 10)
        total = int(stats.get("posts_with_metrics") or 0)
        state = "АКТИВНА" if active else "НАКОПИЧУЄ ДАНІ"
        name = str(getattr(channel, "name", "") or "") if channel else ""
        self.rc48_memory_status.set(
            f"{name}: {state} · постів з метриками {total} · "
            f"порівнюваних на ~{checkpoint} год {comparable}/{minimum}"
        )

        for rank, row in enumerate(snapshot.get("rows") or [], start=1):
            title = str(row.get("teaser_text") or row.get("title") or "").replace("\n", " ")
            title = " ".join(title.split())
            if len(title) > 115:
                title = title[:112].rstrip() + "…"
            tree.insert(
                "", "end",
                values=(
                    rank,
                    title,
                    f"{int(row.get('checkpoint_hours') or 0)} год",
                    int(row.get("views") or 0),
                    int(row.get("reactions") or 0),
                    int(row.get("forwards") or 0),
                    int(row.get("replies") or 0),
                ),
            )

        if active:
            self.rc48_memory_note.set(
                "Пам'ять уже підмішує до відбору та редакторських промптів до 4 "
                "релевантних еталонних постів із TOP-30 цього каналу."
            )
        else:
            self.rc48_memory_note.set(
                "До порогу пам'ять нічого не змінює у відборі чи написанні. "
                "Жодних штучних навчальних прикладів програма не вигадує."
            )

    def refresh_metrics_now(self):
        channel_id = int(self.current_channel_id or 0)
        if not channel_id:
            messagebox.showwarning(APP_NAME, "Спочатку оберіть канал.", parent=self.root)
            return
        channel = self.db.get_channel(channel_id)
        if channel is None:
            return

        self.rc48_memory_status.set(f"{channel.name}: читаю Telegram-метрики…")

        def worker():
            summary = refresh_channel_metrics(self.db, channel, force=True)

            def finish():
                self._rc48_refresh_memory()
                if summary.get("error"):
                    messagebox.showwarning(
                        APP_NAME,
                        "Telegram Analytics: " + str(summary.get("error")),
                        parent=self.root,
                    )
                elif not summary.get("configured"):
                    messagebox.showinfo(
                        APP_NAME,
                        "Telegram Analytics ще не налаштовано.",
                        parent=self.root,
                    )
                else:
                    messagebox.showinfo(
                        APP_NAME,
                        f"Перевірено: {summary.get('checked', 0)}; "
                        f"збережено зрізів: {summary.get('saved', 0)}.",
                        parent=self.root,
                    )

            try:
                self._ui_queue.put(finish)
            except Exception:
                pass

        threading.Thread(target=worker, name="RC48Metrics", daemon=True).start()

    def refresh_all_rc48(self):
        result = old_refresh_all(self)
        try:
            self._rc48_refresh_memory()
        except Exception:
            pass
        return result

    MainWindow._build = build_rc48
    MainWindow._rc48_refresh_memory = refresh_memory
    MainWindow._rc48_refresh_metrics_now = refresh_metrics_now
    MainWindow.refresh_all = refresh_all_rc48
    _INSTALLED = True
