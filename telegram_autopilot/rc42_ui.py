from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import APP_NAME
from .rc42_policy import parse_editorial_weights
from .secrets_store import load_secrets, save_secrets
from .telegram import normalize_chat_target, test_bot

_INSTALLED = False

_NEUTRAL_PROFILE = (
    "Публікуй матеріали відповідно до тематики, джерел і редакційних ваг саме цього каналу. "
    "Не переносити тематику або частки з інших каналів. Відбирай самостійні новини й корисні матеріали, "
    "які відповідають аудиторії цього каналу; сумнівні факти не домислюй."
)


def _weight_dialog(parent: tk.Misc, title: str, *, name: str = "", weight: float = 0.0):
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    result: dict[str, object] = {}

    ttk.Label(win, text="Назва редакційної категорії").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 3))
    name_entry = ttk.Entry(win, width=48)
    name_entry.grid(row=1, column=0, sticky="ew", padx=12)
    name_entry.insert(0, name)

    ttk.Label(win, text="Вага (0–100)").grid(row=2, column=0, sticky="w", padx=12, pady=(10, 3))
    weight_entry = ttk.Entry(win, width=16)
    weight_entry.grid(row=3, column=0, sticky="w", padx=12)
    weight_entry.insert(0, f"{float(weight):g}")

    ttk.Label(
        win,
        text="Ваги відносні: якщо сума не 100, програма сама нормалізує їх у частки.",
        foreground="#555",
        wraplength=430,
    ).grid(row=4, column=0, sticky="w", padx=12, pady=(7, 4))

    buttons = ttk.Frame(win)
    buttons.grid(row=5, column=0, sticky="e", padx=12, pady=12)

    def save():
        category = " ".join(name_entry.get().split()).strip()
        if not category:
            messagebox.showerror(APP_NAME, "Вкажіть назву категорії.", parent=win)
            return
        try:
            value = float(weight_entry.get().replace(",", "."))
        except ValueError:
            messagebox.showerror(APP_NAME, "Вага має бути числом від 0 до 100.", parent=win)
            return
        if value < 0 or value > 100:
            messagebox.showerror(APP_NAME, "Вага має бути від 0 до 100.", parent=win)
            return
        result["name"] = category
        result["weight"] = value
        win.destroy()

    ttk.Button(buttons, text="Скасувати", command=win.destroy).pack(side="right")
    ttk.Button(buttons, text="Зберегти", command=save).pack(side="right", padx=(0, 6))
    name_entry.focus_set()
    parent.wait_window(win)
    return result or None


def install_rc42_ui() -> None:
    """Replace only the channel editor; the rest of the established UI stays intact."""
    global _INSTALLED
    if _INSTALLED:
        return

    from .models import Channel
    from .ui import MainWindow

    def channel_dialog(self: MainWindow, ch: Channel | None):
        win = tk.Toplevel(self.root)
        win.title("Канал · редакційний профіль")
        win.transient(self.root)
        win.grab_set()
        win.geometry("900x760")
        win.minsize(820, 680)

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        fields: dict[str, ttk.Entry] = {}

        def entry(label: str, value: str = "", show: str = ""):
            frame = ttk.Frame(body)
            frame.pack(fill="x", pady=4)
            ttk.Label(frame, text=label, width=31).pack(side="left")
            widget = ttk.Entry(frame, show=show)
            widget.pack(side="left", fill="x", expand=True)
            widget.insert(0, str(value))
            widget.bind("<Control-KeyPress>", self._control_edit_shortcut, add="+")
            widget.bind("<Shift-Insert>", self._paste_shortcut, add="+")
            widget.bind("<Button-3>", self._show_edit_menu, add="+")
            return widget

        fields["name"] = entry("Назва каналу", ch.name if ch else "")
        fields["chat"] = entry("Telegram: посилання / @username / Chat ID", ch.telegram_chat_id if ch else "")
        secret = load_secrets()
        existing = secret.channel_bot_tokens.get(str(ch.id), "") if ch else ""
        fields["token"] = entry("Bot Token (необов'язково)", existing, show="•")

        profile_box = ttk.LabelFrame(body, text="Редакційний профіль цього каналу", padding=8)
        profile_box.pack(fill="x", pady=(8, 6))
        ttk.Label(
            profile_box,
            text="Опиши тематику, аудиторію, що публікувати/не публікувати і бажаний стиль. Це налаштування належить тільки цьому каналу.",
            foreground="#555",
            wraplength=820,
        ).pack(anchor="w", pady=(0, 5))
        profile = tk.Text(profile_box, height=6, wrap="word")
        profile.pack(fill="x", expand=False)
        profile.insert("1.0", (ch.editorial_profile if ch and ch.editorial_profile.strip() else _NEUTRAL_PROFILE))
        profile.bind("<Control-KeyPress>", self._control_edit_shortcut, add="+")
        profile.bind("<Shift-Insert>", self._paste_shortcut, add="+")
        profile.bind("<Button-3>", self._show_edit_menu, add="+")

        weights_box = ttk.LabelFrame(body, text="Редакційні ваги цього каналу", padding=8)
        weights_box.pack(fill="both", expand=True, pady=6)
        ttk.Label(
            weights_box,
            text=(
                "Додавай назви категорій і ваги вручну. Вага 0 забороняє автоматичні публікації цієї категорії. "
                "Якщо список порожній, тематичний баланс для каналу взагалі не застосовується."
            ),
            foreground="#555",
            wraplength=820,
        ).pack(anchor="w", pady=(0, 6))

        columns = ("name", "weight")
        tree = ttk.Treeview(weights_box, columns=columns, show="headings", height=8)
        tree.heading("name", text="Назва категорії")
        tree.heading("weight", text="Вага")
        tree.column("name", width=580, anchor="w")
        tree.column("weight", width=120, anchor="center")
        tree.pack(fill="both", expand=True)

        weights: list[dict[str, object]] = [dict(item) for item in parse_editorial_weights(ch)] if ch else []

        total_var = tk.StringVar()

        def refresh_weights():
            for iid in tree.get_children():
                tree.delete(iid)
            for index, item in enumerate(weights):
                tree.insert("", "end", iid=f"w{index}", values=(item["name"], f"{float(item['weight']):g}"))
            total = sum(float(item["weight"]) for item in weights)
            total_var.set(f"Сума ваг: {total:g}. Програма нормалізує їх пропорційно.")

        def selected_index():
            selected = tree.selection()
            if not selected:
                return None
            try:
                return int(str(selected[0])[1:])
            except Exception:
                return None

        def add_weight():
            item = _weight_dialog(win, "Додати редакційну вагу", weight=10)
            if not item:
                return
            if any(str(existing["name"]).casefold() == str(item["name"]).casefold() for existing in weights):
                messagebox.showerror(APP_NAME, "Категорія з такою назвою вже є.", parent=win)
                return
            weights.append(item)
            refresh_weights()

        def edit_weight():
            index = selected_index()
            if index is None or not (0 <= index < len(weights)):
                return
            old = weights[index]
            item = _weight_dialog(win, "Редагувати редакційну вагу", name=str(old["name"]), weight=float(old["weight"]))
            if not item:
                return
            if any(i != index and str(existing["name"]).casefold() == str(item["name"]).casefold() for i, existing in enumerate(weights)):
                messagebox.showerror(APP_NAME, "Категорія з такою назвою вже є.", parent=win)
                return
            weights[index] = item
            refresh_weights()

        def delete_weight():
            index = selected_index()
            if index is None or not (0 <= index < len(weights)):
                return
            del weights[index]
            refresh_weights()

        weights_bar = ttk.Frame(weights_box)
        weights_bar.pack(fill="x", pady=(6, 0))
        ttk.Button(weights_bar, text="+ Додати вагу", command=add_weight).pack(side="left")
        ttk.Button(weights_bar, text="Редагувати", command=edit_weight).pack(side="left", padx=5)
        ttk.Button(weights_bar, text="Видалити", command=delete_weight).pack(side="left")
        ttk.Label(weights_bar, textvariable=total_var, foreground="#555").pack(side="right")
        tree.bind("<Double-1>", lambda _event: edit_weight())
        refresh_weights()

        nums = ttk.LabelFrame(body, text="Автоматизація", padding=8)
        nums.pack(fill="x", pady=6)
        values = [
            ("poll", "Перевірка джерел, хв", ch.poll_interval_minutes if ch else 5),
            ("gap", "Мін. пауза між постами, хв", ch.min_publish_interval_minutes if ch else 10),
            ("dedupe", "Вікно дедуплікації, год", ch.dedupe_window_hours if ch else 72),
            ("age", "Макс. вік матеріалу, год", ch.max_age_hours if ch else 24),
            ("maxcycle", "Макс. постів за цикл", ch.max_posts_per_cycle if ch else 3),
        ]
        for row, (key, label, value) in enumerate(values):
            ttk.Label(nums, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget = ttk.Entry(nums, width=12)
            widget.insert(0, str(value))
            widget.grid(row=row, column=1, sticky="w", padx=8)
            fields[key] = widget
        enabled = tk.BooleanVar(value=ch.enabled if ch else True)
        ttk.Checkbutton(nums, text="Канал активний", variable=enabled).grid(row=0, column=2, sticky="w", padx=20)

        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(8, 0))

        def save():
            try:
                name = fields["name"].get().strip()
                if not name:
                    raise ValueError("Вкажіть назву каналу.")
                chat = normalize_chat_target(fields["chat"].get())
                editorial_profile = profile.get("1.0", "end-1c").strip() or _NEUTRAL_PROFILE
                cid = self.db.save_channel(
                    channel_id=ch.id if ch else None,
                    name=name,
                    telegram_chat_id=chat,
                    editorial_profile=editorial_profile,
                    enabled=enabled.get(),
                    include_source_link=False,
                    poll_interval_minutes=int(fields["poll"].get()),
                    min_publish_interval_minutes=int(fields["gap"].get()),
                    dedupe_window_hours=int(fields["dedupe"].get()),
                    max_age_hours=int(fields["age"].get()),
                    max_posts_per_cycle=int(fields["maxcycle"].get()),
                )
                self.db.set_channel_editorial_weights(cid, weights)
                sec = load_secrets()
                token = fields["token"].get().strip()
                if token:
                    sec.channel_bot_tokens[str(cid)] = token
                else:
                    sec.channel_bot_tokens.pop(str(cid), None)
                save_secrets(sec)
                self.current_channel_id = cid
                win.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=win)

        ttk.Button(bottom, text="Зберегти", command=save).pack(side="right")
        ttk.Button(bottom, text="Скасувати", command=win.destroy).pack(side="right", padx=6)

        if ch:
            def test():
                try:
                    token = fields["token"].get().strip() or load_secrets().default_telegram_bot_token
                    name = test_bot(token, fields["chat"].get())
                    messagebox.showinfo(APP_NAME, f"Telegram канал доступний: {name}", parent=win)
                except Exception as exc:
                    messagebox.showerror(APP_NAME, str(exc), parent=win)
            ttk.Button(bottom, text="Перевірити Telegram", command=test).pack(side="left")

    MainWindow._channel_dialog = channel_dialog
    _INSTALLED = True
