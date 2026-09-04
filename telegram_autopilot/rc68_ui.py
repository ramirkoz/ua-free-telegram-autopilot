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


def _channel_dialog_rc68(self: Any, ch: Any | None) -> None:
    before = set(self.root.winfo_children())
    _PREV_DIALOG(self, ch)
    created = [w for w in self.root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
    top = created[-1] if created else None
    if top is None:
        return
    try:
        top.title("Канал · RC68")
    except tk.TclError:
        pass
    for widget in _walk(top):
        if not isinstance(widget, ttk.Label):
            continue
        try:
            text = str(widget.cget("text") or "")
        except tk.TclError:
            continue
        if text.startswith("Пресет лише виставляє поля нижче"):
            widget.configure(
                text=(
                    "Режим визначає логіку відбору. Редакційний: CHANNEL POLICY + універсальний Editorial Value Gate + баланс. "
                    "Моніторинговий: без оцінки «цікаво/нецікаво» і без тематичного балансу; лишаються exclusions, dedupe/merge/update. "
                    "Кнопка «Застосувати пресет» лише виставляє рекомендовані часові поля."
                ),
                wraplength=430,
            )


def install_rc68_ui() -> None:
    global _INSTALLED, _PREV_DIALOG
    if _INSTALLED:
        return
    from .ui import MainWindow

    _PREV_DIALOG = MainWindow._channel_dialog
    MainWindow._channel_dialog = _channel_dialog_rc68
    _INSTALLED = True
