from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

_INSTALLED = False
_PREV_DIALOG = None


def _walk(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _channel_dialog_rc70(self: Any, ch: Any | None) -> None:
    before = set(self.root.winfo_children())
    _PREV_DIALOG(self, ch)
    created = [w for w in self.root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
    win = created[-1] if created else None
    if win is None:
        return

    try:
        win.title("Канал · RC70")
    except tk.TclError:
        pass

    # RC45 still injects its historical two-way "Напрям контенту" box before
    # RC69 adds the newer language selector. Keep only the newer selector so the
    # operator does not have two controls writing the same setting.
    for widget in list(_walk(win)):
        if not isinstance(widget, ttk.LabelFrame):
            continue
        try:
            title = str(widget.cget("text"))
        except tk.TclError:
            continue
        if title == "Напрям контенту":
            try:
                widget.destroy()
            except tk.TclError:
                pass
            continue
        if title != "Мова джерел → мова публікації":
            continue

        try:
            widget.configure(text="Мови джерел → мова публікації")
        except tk.TclError:
            pass

        for child in _walk(widget):
            if not isinstance(child, ttk.Label):
                continue
            try:
                text = str(child.cget("text"))
            except tk.TclError:
                continue
            if "Це властивість каналу" not in text:
                continue
            try:
                child.configure(
                    text=(
                        "Налаштування універсальне для будь-якого каналу. Один канал може одночасно читати "
                        "українські й російські джерела. Для такого випадку оберіть «Українська / російська → "
                        "Українська»: мова перевіряється для кожного матеріалу окремо, а публікація виходить "
                        "українською. Окремі UA→UA та RU→UA режими лишаються для каналів, де джерела навмисно "
                        "обмежені однією мовою."
                    ),
                    wraplength=760,
                    justify="left",
                )
            except tk.TclError:
                pass
            break


def install_rc70_ui() -> None:
    global _INSTALLED, _PREV_DIALOG
    if _INSTALLED:
        return

    from .ui import MainWindow

    _PREV_DIALOG = MainWindow._channel_dialog
    MainWindow._channel_dialog = _channel_dialog_rc70
    _INSTALLED = True
