from __future__ import annotations

import tkinter as tk
from tkinter import ttk

_INSTALLED = False


def _target_dialog_size(screen_w: int, screen_h: int, req_w: int, req_h: int) -> tuple[int, int]:
    """Choose a screen-safe size large enough for the channel editor when possible."""
    available_w = max(760, int(screen_w) - 80)
    available_h = max(600, int(screen_h) - 100)
    width = min(available_w, max(900, int(req_w) + 24))
    height = min(available_h, max(820, int(req_h) + 24))
    return width, height


def _descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _fit_channel_dialog(win: tk.Toplevel) -> None:
    """Make RC42's channel form usable without the resize-the-window ritual."""
    win.update_idletasks()
    screen_w = int(win.winfo_screenwidth() or 900)
    screen_h = int(win.winfo_screenheight() or 700)
    available_h = max(600, screen_h - 100)

    # If Windows scaling makes the requested form taller than the screen, shrink
    # only the two flexible editors. Fixed fields and the Save/Cancel row remain.
    if int(win.winfo_reqheight()) + 24 > available_h:
        for child in _descendants(win):
            if isinstance(child, ttk.Treeview):
                try:
                    child.configure(height=4)
                except tk.TclError:
                    pass
            elif isinstance(child, tk.Text):
                try:
                    child.configure(height=4)
                except tk.TclError:
                    pass
        win.update_idletasks()

    width, height = _target_dialog_size(
        screen_w,
        screen_h,
        int(win.winfo_reqwidth()),
        int(win.winfo_reqheight()),
    )
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2 - 10)
    win.geometry(f"{width}x{height}+{x}+{y}")
    win.minsize(min(820, width), min(600, height))

    # Ctrl+S is a second, explicit save path. It is useful on unusually small
    # displays even if a third-party Tk theme still consumes more vertical room.
    def invoke_save(_event=None):
        for child in _descendants(win):
            if isinstance(child, ttk.Button):
                try:
                    if str(child.cget("text")).strip().casefold() == "зберегти":
                        child.invoke()
                        return "break"
                except tk.TclError:
                    continue
        return None

    win.bind("<Control-s>", invoke_save, add="+")
    win.bind("<Control-S>", invoke_save, add="+")
    win.lift()


def install_rc43_ui() -> None:
    """Wrap the RC42 channel editor with a screen-aware layout correction."""
    global _INSTALLED
    if _INSTALLED:
        return

    from .ui import MainWindow

    original = MainWindow._channel_dialog

    def channel_dialog(self: MainWindow, ch):
        before = {str(widget) for widget in self.root.winfo_children()}
        original(self, ch)
        candidates = [
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel) and str(widget) not in before and widget.winfo_exists()
        ]
        if candidates:
            _fit_channel_dialog(candidates[-1])

    MainWindow._channel_dialog = channel_dialog
    _INSTALLED = True
