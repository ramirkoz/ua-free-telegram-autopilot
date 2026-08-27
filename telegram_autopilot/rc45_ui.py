from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .rc45_policy import (
    DIRECTION_EN_TO_UK,
    DIRECTION_LABELS,
    content_direction,
)

_INSTALLED = False


def _descendants(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def install_rc45_ui() -> None:
    """Add per-channel language direction without replacing the proven RC42 editor."""
    global _INSTALLED
    if _INSTALLED:
        return

    from .database import Database
    from .ui import MainWindow

    original_dialog = MainWindow._channel_dialog
    original_save_channel = Database.save_channel

    def save_channel_with_direction(self: Database, **kwargs):
        channel_id = original_save_channel(self, **kwargs)
        direction = str(getattr(self, "_rc45_pending_direction", "") or "").strip()
        if direction in DIRECTION_LABELS:
            self.set_channel_content_direction(channel_id, direction)
        else:
            # Existing channels keep the migrated value; genuinely new channels
            # default to the established English -> Ukrainian behavior.
            with self.connect() as con:
                row = con.execute("SELECT content_direction FROM channels WHERE id=?", (channel_id,)).fetchone()
                current = str(row[0] or "") if row else ""
            if current not in DIRECTION_LABELS:
                self.set_channel_content_direction(channel_id, DIRECTION_EN_TO_UK)
        try:
            delattr(self, "_rc45_pending_direction")
        except AttributeError:
            pass
        return channel_id

    Database.save_channel = save_channel_with_direction

    def channel_dialog(self: MainWindow, ch):
        # Save() in the RC42 dialog runs later, after this wrapper returns. Keep
        # the selected value on the Database instance so the save wrapper can
        # persist it atomically with the rest of the channel settings.
        initial = content_direction(ch) if ch else DIRECTION_EN_TO_UK
        self.db._rc45_pending_direction = initial

        before = {str(widget) for widget in self.root.winfo_children()}
        original_dialog(self, ch)
        candidates = [
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel) and str(widget) not in before and widget.winfo_exists()
        ]
        if not candidates:
            return
        win = candidates[-1]

        body = None
        profile_box = None
        for child in win.winfo_children():
            if isinstance(child, ttk.Frame):
                body = child
                break
        if body is None:
            return
        for child in body.winfo_children():
            if isinstance(child, ttk.LabelFrame):
                try:
                    if str(child.cget("text")) == "Редакційний профіль цього каналу":
                        profile_box = child
                        break
                except tk.TclError:
                    pass

        direction_box = ttk.LabelFrame(body, text="Напрям контенту", padding=8)
        label_to_value = {label: value for value, label in DIRECTION_LABELS.items()}
        direction_var = tk.StringVar(value=DIRECTION_LABELS[initial])
        combo = ttk.Combobox(
            direction_box,
            textvariable=direction_var,
            values=list(label_to_value.keys()),
            state="readonly",
            width=44,
        )
        combo.pack(anchor="w")
        ttk.Label(
            direction_box,
            text=(
                "Вибір належить тільки цьому каналу. Перший режим бере англомовні джерела й пише українською; "
                "другий бере українські/російські джерела й робить нативний англомовний рерайт."
            ),
            foreground="#555",
            wraplength=820,
        ).pack(anchor="w", pady=(5, 0))

        if profile_box is not None:
            direction_box.pack(fill="x", pady=(8, 4), before=profile_box)
        else:
            direction_box.pack(fill="x", pady=(8, 4))

        def remember_direction(_event=None):
            self.db._rc45_pending_direction = label_to_value.get(
                direction_var.get(), DIRECTION_EN_TO_UK
            )

        combo.bind("<<ComboboxSelected>>", remember_direction, add="+")
        remember_direction()

        def clear_pending(event):
            if event.widget is not win:
                return
            # If Save already consumed it this attribute no longer exists. On
            # Cancel/X we must not leak the abandoned choice into the next dialog.
            try:
                delattr(self.db, "_rc45_pending_direction")
            except AttributeError:
                pass

        win.bind("<Destroy>", clear_pending, add="+")

    MainWindow._channel_dialog = channel_dialog
    _INSTALLED = True
