from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from . import APP_NAME
from .models import Channel
from .secrets_store import load_secrets, save_secrets
from .telegram import normalize_chat_target, test_bot
from .ui import DEFAULT_PROFILE

_INSTALLED = False
_PREV = {}


def _bind_editing(main, widget) -> None:
    widget.bind("<Control-KeyPress>", main._control_edit_shortcut, add="+")
    widget.bind("<Shift-Insert>", main._paste_shortcut, add="+")
    widget.bind("<Button-3>", main._show_edit_menu, add="+")


def _channel_dialog_rc66(self, ch: Channel | None) -> None:
    win = tk.Toplevel(self.root)
    win.title("Канал · RC66")
    win.transient(self.root)
    win.grab_set()
    win.geometry("840x760")
    win.minsize(760, 680)

    outer = ttk.Frame(win, padding=12)
    outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, highlightthickness=0)
    scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    form = ttk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=form, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    def resize_form(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
        try:
            canvas.itemconfigure(window_id, width=canvas.winfo_width())
        except tk.TclError:
            pass

    form.bind("<Configure>", resize_form)
    canvas.bind("<Configure>", resize_form)
    fields: dict[str, ttk.Entry] = {}

    def entry_row(parent, label: str, value: object = "", *, width: int = 26, show: str = "") -> ttk.Entry:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=32).pack(side="left")
        widget = ttk.Entry(row, width=width, show=show)
        widget.pack(side="left", fill="x", expand=True)
        widget.insert(0, str(value))
        _bind_editing(self, widget)
        return widget

    identity = ttk.LabelFrame(form, text="Канал", padding=10)
    identity.pack(fill="x", pady=(0, 8))
    fields["name"] = entry_row(identity, "Назва каналу", ch.name if ch else "")
    fields["chat"] = entry_row(identity, "Telegram: @username / Chat ID", ch.telegram_chat_id if ch else "")
    secret = load_secrets()
    existing_token = secret.channel_bot_tokens.get(str(ch.id), "") if ch else ""
    fields["token"] = entry_row(identity, "Bot Token (необов'язково)", existing_token, show="•")

    mode_box = ttk.LabelFrame(form, text="Режим / пресет", padding=10)
    mode_box.pack(fill="x", pady=8)
    mode_var = tk.StringVar(value=("Моніторинговий" if str(getattr(ch, "channel_mode", "editorial")) == "monitoring" else "Редакційний"))
    ttk.Label(mode_box, text="Тип каналу", width=32).pack(side="left")
    ttk.Combobox(mode_box, textvariable=mode_var, state="readonly", values=("Редакційний", "Моніторинговий"), width=22).pack(side="left", padx=(0, 10))
    ttk.Label(mode_box, text="Пресет лише виставляє поля нижче. Після цього кожне значення можна змінити вручну.", foreground="#555", wraplength=360, justify="left").pack(side="left", fill="x", expand=True)

    collect = ttk.LabelFrame(form, text="Перевірка джерел", padding=10)
    collect.pack(fill="x", pady=8)
    poll_row = ttk.Frame(collect); poll_row.pack(fill="x")
    ttk.Label(poll_row, text="Інтервал перевірки, хв", width=32).pack(side="left")
    fields["poll"] = ttk.Entry(poll_row, width=10); fields["poll"].pack(side="left")
    fields["poll"].insert(0, str(ch.poll_interval_minutes if ch else 5)); _bind_editing(self, fields["poll"])
    poll_immediate = tk.BooleanVar(value=bool(getattr(ch, "poll_immediate", False)) if ch else False)
    ttk.Checkbutton(poll_row, text="Одразу (технічний цикл ≈15 с)", variable=poll_immediate).pack(side="left", padx=16)
    ttk.Label(collect, text="Для RSS/сайтів «Одразу» означає найчастішу безпечну перевірку в циклі програми; це polling, а не фальшива обіцянка push-доставки.", foreground="#555", wraplength=760, justify="left").pack(anchor="w", pady=(6, 0))

    publish = ttk.LabelFrame(form, text="Публікація", padding=10)
    publish.pack(fill="x", pady=8)
    publish_24h = tk.BooleanVar(value=bool(getattr(ch, "publish_24h", False)) if ch else False)
    ttk.Checkbutton(publish, text="Цілодобово", variable=publish_24h).grid(row=0, column=0, sticky="w", pady=3)
    ttk.Label(publish, text="З").grid(row=0, column=1, sticky="e", padx=(20, 4))
    fields["start"] = ttk.Entry(publish, width=8); fields["start"].insert(0, str(getattr(ch, "publish_start", "07:00") if ch else "07:00")); fields["start"].grid(row=0, column=2, sticky="w")
    ttk.Label(publish, text="до").grid(row=0, column=3, padx=(10, 4))
    fields["end"] = ttk.Entry(publish, width=8); fields["end"].insert(0, str(getattr(ch, "publish_end", "00:00") if ch else "00:00")); fields["end"].grid(row=0, column=4, sticky="w")
    _bind_editing(self, fields["start"]); _bind_editing(self, fields["end"])
    ttk.Label(publish, text="Мін. інтервал між постами, хв").grid(row=1, column=0, sticky="w", pady=6)
    fields["gap"] = ttk.Entry(publish, width=10); fields["gap"].insert(0, str(ch.min_publish_interval_minutes if ch else 10)); fields["gap"].grid(row=1, column=1, columnspan=2, sticky="w", padx=(20, 0)); _bind_editing(self, fields["gap"])
    publish_immediate = tk.BooleanVar(value=bool(getattr(ch, "publish_immediately", False)) if ch else False)
    ttk.Checkbutton(publish, text="Одразу", variable=publish_immediate).grid(row=1, column=3, columnspan=2, sticky="w", padx=(10, 0))

    balance = ttk.LabelFrame(form, text="Редакційний баланс", padding=10)
    balance.pack(fill="x", pady=8)
    balance_enabled = tk.BooleanVar(value=bool(getattr(ch, "topic_balance_enabled", True)) if ch else True)
    ttk.Checkbutton(balance, text="Тримати внутрішньодобовий тематичний баланс", variable=balance_enabled).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
    ttk.Label(balance, text="Макс. матеріалів великої теми за добу", width=38).grid(row=1, column=0, sticky="w", pady=4)
    fields["topic_limit"] = ttk.Entry(balance, width=8); fields["topic_limit"].insert(0, str(getattr(ch, "topic_daily_limit", 2) if ch else 2)); fields["topic_limit"].grid(row=1, column=1, sticky="w")
    ttk.Label(balance, text="Мін. інших постів між близькими історіями", width=38).grid(row=2, column=0, sticky="w", pady=4)
    fields["related_spacing"] = ttk.Entry(balance, width=8); fields["related_spacing"].insert(0, str(getattr(ch, "related_spacing_posts", 5) if ch else 5)); fields["related_spacing"].grid(row=2, column=1, sticky="w")
    _bind_editing(self, fields["topic_limit"]); _bind_editing(self, fields["related_spacing"])
    ttk.Label(balance, text="Різні пацієнти/люди/кейси не стають дублями. Якщо це близькі історії, друга чекає задану кількість інших постів. Добовий ліміт теми обнуляється наступної календарної доби.", wraplength=740, justify="left", foreground="#555").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

    advanced = ttk.LabelFrame(form, text="Інше", padding=10)
    advanced.pack(fill="x", pady=8)
    vals = (
        ("dedupe", "Вікно дедуплікації, год", ch.dedupe_window_hours if ch else 72),
        ("age", "Макс. вік матеріалу, год", ch.max_age_hours if ch else 24),
        ("maxcycle", "Макс. підготовок/публікацій за цикл", ch.max_posts_per_cycle if ch else 3),
    )
    for row_no, (key, label, value) in enumerate(vals):
        ttk.Label(advanced, text=label, width=38).grid(row=row_no, column=0, sticky="w", pady=3)
        e = ttk.Entry(advanced, width=10); e.insert(0, str(value)); e.grid(row=row_no, column=1, sticky="w"); _bind_editing(self, e); fields[key] = e
    enabled = tk.BooleanVar(value=ch.enabled if ch else True)
    ttk.Checkbutton(advanced, text="Канал активний", variable=enabled).grid(row=0, column=2, sticky="w", padx=20)
    ttk.Label(advanced, text="READY-пул зберігає готові матеріали до дозволеного часу публікації.", foreground="#555", wraplength=300).grid(row=1, column=2, rowspan=2, sticky="w", padx=20)

    def apply_preset() -> None:
        monitoring = mode_var.get() == "Моніторинговий"
        if monitoring:
            poll_immediate.set(True); publish_24h.set(True); publish_immediate.set(True); balance_enabled.set(False)
            fields["gap"].delete(0, "end"); fields["gap"].insert(0, "0")
        else:
            poll_immediate.set(False); publish_24h.set(False); publish_immediate.set(False); balance_enabled.set(True)
            fields["start"].delete(0, "end"); fields["start"].insert(0, "07:00")
            fields["end"].delete(0, "end"); fields["end"].insert(0, "00:00")
            fields["topic_limit"].delete(0, "end"); fields["topic_limit"].insert(0, "2")
            fields["related_spacing"].delete(0, "end"); fields["related_spacing"].insert(0, "5")

    ttk.Button(mode_box, text="Застосувати пресет", command=apply_preset).pack(side="right", padx=(10, 0))
    buttons = ttk.Frame(form); buttons.pack(fill="x", pady=(10, 16))

    def save() -> None:
        try:
            name = fields["name"].get().strip()
            if not name:
                raise ValueError("Вкажіть назву каналу.")
            chat = normalize_chat_target(fields["chat"].get())
            profile = ch.editorial_profile if ch and ch.editorial_profile.strip() else DEFAULT_PROFILE
            cid = self.db.save_channel(
                channel_id=ch.id if ch else None, name=name, telegram_chat_id=chat, editorial_profile=profile,
                enabled=enabled.get(), include_source_link=False,
                poll_interval_minutes=max(1, int(fields["poll"].get() or "1")),
                min_publish_interval_minutes=max(0, int(fields["gap"].get() or "0")),
                dedupe_window_hours=max(1, int(fields["dedupe"].get() or "1")),
                max_age_hours=max(1, int(fields["age"].get() or "1")),
                max_posts_per_cycle=max(1, int(fields["maxcycle"].get() or "1")),
            )
            self.db.rc66_save_channel_settings(
                cid, poll_immediate=poll_immediate.get(), publish_24h=publish_24h.get(),
                publish_start=fields["start"].get(), publish_end=fields["end"].get(), publish_immediately=publish_immediate.get(),
                topic_balance_enabled=balance_enabled.get(), topic_daily_limit=max(1, int(fields["topic_limit"].get() or "2")),
                related_spacing_posts=max(0, int(fields["related_spacing"].get() or "5")),
                channel_mode="monitoring" if mode_var.get() == "Моніторинговий" else "editorial",
            )
            sec = load_secrets(); tok = fields["token"].get().strip()
            if tok: sec.channel_bot_tokens[str(cid)] = tok
            else: sec.channel_bot_tokens.pop(str(cid), None)
            save_secrets(sec); self.current_channel_id = cid; win.destroy(); self.refresh_all()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)

    ttk.Button(buttons, text="Зберегти", command=save).pack(side="right")
    ttk.Button(buttons, text="Скасувати", command=win.destroy).pack(side="right", padx=7)
    if ch:
        def test() -> None:
            try:
                tok = fields["token"].get().strip() or load_secrets().default_telegram_bot_token
                display = test_bot(tok, fields["chat"].get())
                messagebox.showinfo(APP_NAME, f"Telegram канал доступний: {display}", parent=win)
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=win)
        ttk.Button(buttons, text="Перевірити Telegram", command=test).pack(side="left")
    fields["name"].focus_set()


def install_rc66_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from .ui import MainWindow
    _PREV["build_dashboard"] = MainWindow._build_dashboard
    _PREV["refresh_stats"] = MainWindow.refresh_stats
    MainWindow._channel_dialog = _channel_dialog_rc66

    def refresh_channels(self) -> None:
        for item in self.channels_tree.get_children(): self.channels_tree.delete(item)
        for channel in self.db.list_channels():
            poll = "Одразу (~15 с)" if bool(getattr(channel, "poll_immediate", False)) else str(channel.poll_interval_minutes)
            gap = "Одразу" if bool(getattr(channel, "publish_immediately", False)) else str(channel.min_publish_interval_minutes)
            self.channels_tree.insert("", "end", iid=str(channel.id), values=(channel.name, channel.telegram_chat_id, "так" if channel.enabled else "ні", poll, gap, channel.dedupe_window_hours, len(self.db.list_sources(channel.id))))

    def build_dashboard(self) -> None:
        _PREV["build_dashboard"](self)
        self.rc66_ready_var = tk.StringVar(value="READY-пул: 0")
        ttk.Label(self.dashboard, textvariable=self.rc66_ready_var, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=4, pady=(0, 4))

    def refresh_stats(self) -> None:
        _PREV["refresh_stats"](self)
        if hasattr(self, "rc66_ready_var"):
            self.rc66_ready_var.set(f"READY-пул: {int(self.db.stats(self.current_channel_id).get('ready', 0))}")

    MainWindow.refresh_channels = refresh_channels
    MainWindow._build_dashboard = build_dashboard
    MainWindow.refresh_stats = refresh_stats
    _INSTALLED = True
