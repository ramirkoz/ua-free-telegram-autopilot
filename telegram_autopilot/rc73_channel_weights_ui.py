from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from . import APP_NAME
from . import rc42_policy as rc42
from . import rc72_channel_policy_ui as rc72ui

_INSTALLED = False
_PREV_DIALOG = None
_PREV_SAVE_CHANNEL = None


def _copy_weights(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        name = " ".join(str(item.get("name") or "").split()).strip()
        if not name:
            continue
        try:
            weight = max(0.0, min(100.0, float(item.get("weight", 0) or 0)))
        except (TypeError, ValueError):
            continue
        out.append({"name": name[:120], "weight": weight})
    return out


def _weight_dialog(parent: tk.Misc, title: str, *, name: str = "", weight: float = 10.0) -> dict[str, Any] | None:
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    result: dict[str, Any] = {}

    ttk.Label(win, text="Назва редакційної категорії").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 3))
    name_entry = ttk.Entry(win, width=52)
    name_entry.grid(row=1, column=0, sticky="ew", padx=12)
    name_entry.insert(0, name)

    ttk.Label(win, text="Вага (0–100)").grid(row=2, column=0, sticky="w", padx=12, pady=(10, 3))
    weight_entry = ttk.Entry(win, width=16)
    weight_entry.grid(row=3, column=0, sticky="w", padx=12)
    weight_entry.insert(0, f"{float(weight):g}")

    ttk.Label(
        win,
        text="Ваги відносні. Якщо сума не 100, програма нормалізує їх пропорційно. Вага 0 забороняє автоматичні публікації цієї категорії.",
        foreground="#555",
        wraplength=460,
        justify="left",
    ).grid(row=4, column=0, sticky="w", padx=12, pady=(7, 4))

    buttons = ttk.Frame(win)
    buttons.grid(row=5, column=0, sticky="e", padx=12, pady=12)

    def save() -> None:
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
        result.update(name=category[:120], weight=value)
        win.destroy()

    ttk.Button(buttons, text="Скасувати", command=win.destroy).pack(side="right")
    ttk.Button(buttons, text="Зберегти", command=save).pack(side="right", padx=(0, 6))
    name_entry.focus_set()
    parent.wait_window(win)
    return result or None


def _weights_editor(parent: tk.Toplevel, items: list[dict[str, Any]], mode: str) -> list[dict[str, Any]] | None:
    win = tk.Toplevel(parent)
    win.title("Редакційні категорії та ваги цього каналу")
    win.transient(parent)
    win.grab_set()
    win.geometry("780x610")
    win.minsize(680, 520)

    body = ttk.Frame(win, padding=12)
    body.pack(fill="both", expand=True)
    monitoring = str(mode).casefold() == "monitoring"

    if monitoring:
        ttk.Label(
            body,
            text=(
                "Цей канал зараз MONITORING. Редакційні ваги зберігаються як властивість каналу, але в monitoring-режимі НЕ застосовуються: "
                "немає тематичного балансу, інтерес-скорингу або Editorial Value. Якщо канал пізніше стане редакційним, ці ваги знову можуть працювати."
            ),
            foreground="#7a4b00",
            wraplength=730,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
    else:
        ttk.Label(
            body,
            text=(
                "Це ручні цільові частки саме цього редакційного каналу. Порожній список означає: ваговий тематичний баланс не застосовується. "
                "Ці категорії не є універсальними правилами програми."
            ),
            foreground="#555",
            wraplength=730,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

    current = _copy_weights(items)
    cols = ("name", "weight")
    tree = ttk.Treeview(body, columns=cols, show="headings", height=14)
    tree.heading("name", text="Категорія")
    tree.heading("weight", text="Вага")
    tree.column("name", width=540, anchor="w")
    tree.column("weight", width=120, anchor="center")
    tree.pack(fill="both", expand=True)

    total_var = tk.StringVar()

    def refresh() -> None:
        for iid in tree.get_children():
            tree.delete(iid)
        for index, item in enumerate(current):
            tree.insert("", "end", iid=f"w{index}", values=(item["name"], f"{float(item['weight']):g}"))
        total = sum(float(item["weight"]) for item in current)
        total_var.set(f"Сума ваг: {total:g}. Нормалізація автоматична." if current else "Список порожній: ваговий баланс вимкнений.")

    def selected_index() -> int | None:
        selected = tree.selection()
        if not selected:
            return None
        try:
            return int(str(selected[0])[1:])
        except Exception:
            return None

    def add() -> None:
        item = _weight_dialog(win, "Додати редакційну категорію")
        if not item:
            return
        if any(str(existing["name"]).casefold() == str(item["name"]).casefold() for existing in current):
            messagebox.showerror(APP_NAME, "Категорія з такою назвою вже є.", parent=win)
            return
        current.append(item)
        refresh()

    def edit() -> None:
        index = selected_index()
        if index is None or not (0 <= index < len(current)):
            return
        old = current[index]
        item = _weight_dialog(win, "Редагувати редакційну категорію", name=str(old["name"]), weight=float(old["weight"]))
        if not item:
            return
        if any(i != index and str(existing["name"]).casefold() == str(item["name"]).casefold() for i, existing in enumerate(current)):
            messagebox.showerror(APP_NAME, "Категорія з такою назвою вже є.", parent=win)
            return
        current[index] = item
        refresh()

    def delete() -> None:
        index = selected_index()
        if index is None or not (0 <= index < len(current)):
            return
        del current[index]
        refresh()

    bar = ttk.Frame(body)
    bar.pack(fill="x", pady=(8, 0))
    ttk.Button(bar, text="+ Додати", command=add).pack(side="left")
    ttk.Button(bar, text="Редагувати", command=edit).pack(side="left", padx=5)
    ttk.Button(bar, text="Видалити", command=delete).pack(side="left")
    ttk.Label(bar, textvariable=total_var, foreground="#555").pack(side="right")
    tree.bind("<Double-1>", lambda _event: edit())
    refresh()

    result: dict[str, list[dict[str, Any]]] = {}
    bottom = ttk.Frame(body)
    bottom.pack(fill="x", pady=(12, 0))

    def save() -> None:
        result["weights"] = _copy_weights(current)
        win.destroy()

    ttk.Button(bottom, text="Зберегти", command=save).pack(side="right")
    ttk.Button(bottom, text="Скасувати", command=win.destroy).pack(side="right", padx=6)
    parent.wait_window(win)
    return result.get("weights")


def _save_channel_rc73(db: Any, **kwargs: Any) -> int:
    pending = getattr(db, "_rc73_pending_weights", None)
    channel_id = int(_PREV_SAVE_CHANNEL(db, **kwargs))
    if isinstance(pending, list):
        db.set_channel_editorial_weights(channel_id, _copy_weights(pending))
        try:
            delattr(db, "_rc73_pending_weights")
        except AttributeError:
            pass
    return channel_id


def _channel_dialog_rc73(self: Any, ch: Any | None) -> None:
    existing = rc42.parse_editorial_weights(ch) if ch else []
    self.db._rc73_pending_weights = _copy_weights(existing)

    before = set(self.root.winfo_children())
    _PREV_DIALOG(self, ch)
    created = [w for w in self.root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
    win = created[-1] if created else None
    if win is None:
        return
    try:
        win.title("Канал · RC73")
    except tk.TclError:
        pass

    form = None
    for widget in rc72ui._walk(win):
        if isinstance(widget, ttk.LabelFrame):
            try:
                if str(widget.cget("text")) == "Канал":
                    form = widget.master
                    break
            except tk.TclError:
                pass
    if form is None:
        return

    children = list(form.winfo_children())
    buttons = children[-1] if children and isinstance(children[-1], ttk.Frame) else None
    box = ttk.LabelFrame(form, text="Редакційні категорії та ваги цього каналу", padding=10)
    status_var = tk.StringVar()

    def update_status() -> None:
        weights = getattr(self.db, "_rc73_pending_weights", [])
        if not weights:
            status_var.set("Не задані. Для editorial ваговий баланс вимкнений; для monitoring ваги все одно не застосовуються.")
            return
        total = sum(float(item.get("weight", 0) or 0) for item in weights)
        status_var.set(f"Задано категорій: {len(weights)}; сума ваг: {total:g}. У monitoring-режимі вони не застосовуються.")

    ttk.Label(box, textvariable=status_var, wraplength=760, justify="left", foreground="#555").pack(anchor="w", pady=(0, 6))

    def edit_weights() -> None:
        mode = rc72ui._dialog_mode(win, ch)
        current = getattr(self.db, "_rc73_pending_weights", [])
        updated = _weights_editor(win, _copy_weights(current), mode)
        if updated is None:
            return
        self.db._rc73_pending_weights = updated
        update_status()

    ttk.Button(box, text="Редагувати категорії та ваги", command=edit_weights).pack(anchor="w")
    update_status()
    if buttons is not None:
        box.pack(before=buttons, fill="x", pady=8)
    else:
        box.pack(fill="x", pady=8)

    def cleanup(event: tk.Event) -> None:
        if event.widget is not win:
            return
        try:
            delattr(self.db, "_rc73_pending_weights")
        except AttributeError:
            pass

    win.bind("<Destroy>", cleanup, add="+")


def install_rc73_channel_weights_ui() -> None:
    global _INSTALLED, _PREV_DIALOG, _PREV_SAVE_CHANNEL
    if _INSTALLED:
        return
    from .database import Database
    from .ui import MainWindow

    _PREV_DIALOG = MainWindow._channel_dialog
    _PREV_SAVE_CHANNEL = Database.save_channel
    Database.save_channel = _save_channel_rc73
    MainWindow._channel_dialog = _channel_dialog_rc73
    _INSTALLED = True
