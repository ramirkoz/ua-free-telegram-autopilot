from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from . import rc45_policy as rc45
from .rc69_media_language import (
    DIRECTION_RU_TO_UK,
    DIRECTION_UK_TO_UK,
    MEDIA_ENRICH_AUTO,
    MEDIA_ENRICH_OFF,
)

_INSTALLED = False
_PREV_DIALOG = None


def _walk(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _bind_editing(main: Any, widget: tk.Widget) -> None:
    widget.bind("<Control-KeyPress>", main._control_edit_shortcut, add="+")
    widget.bind("<Shift-Insert>", main._paste_shortcut, add="+")
    widget.bind("<Button-3>", main._show_edit_menu, add="+")


def _channel_dialog_rc69(self: Any, ch: Any | None) -> None:
    initial_direction = rc45.content_direction(ch) if ch else rc45.DIRECTION_EN_TO_UK
    if initial_direction not in rc45.DIRECTION_LABELS:
        initial_direction = rc45.DIRECTION_EN_TO_UK
    self.db._rc45_pending_direction = initial_direction
    self.db._rc69_pending_media_settings = {
        "media_enrichment_mode": str(getattr(ch, "media_enrichment_mode", MEDIA_ENRICH_AUTO) if ch else MEDIA_ENRICH_AUTO),
        "media_first_allowed": bool(getattr(ch, "media_first_allowed", True) if ch else True),
        "media_min_text_chars": int(getattr(ch, "media_min_text_chars", 500) if ch else 500),
    }

    before = set(self.root.winfo_children())
    _PREV_DIALOG(self, ch)
    created = [w for w in self.root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
    win = created[-1] if created else None
    if win is None:
        return
    try:
        win.title("Канал · RC69")
    except tk.TclError:
        pass

    form = None
    for widget in _walk(win):
        if not isinstance(widget, ttk.LabelFrame):
            continue
        try:
            if str(widget.cget("text")) == "Канал":
                form = widget.master
                break
        except tk.TclError:
            continue
    if form is None:
        return

    children = list(form.winfo_children())
    buttons = children[-1] if children and isinstance(children[-1], ttk.Frame) else None

    language_box = ttk.LabelFrame(form, text="Мова джерел → мова публікації", padding=10)
    label_to_value = {label: value for value, label in rc45.DIRECTION_LABELS.items()}
    direction_var = tk.StringVar(value=rc45.DIRECTION_LABELS.get(initial_direction, rc45.DIRECTION_LABELS[rc45.DIRECTION_EN_TO_UK]))
    row = ttk.Frame(language_box); row.pack(fill="x")
    ttk.Label(row, text="Напрям", width=32).pack(side="left")
    direction_combo = ttk.Combobox(
        row,
        textvariable=direction_var,
        state="readonly",
        values=list(label_to_value.keys()),
        width=42,
    )
    direction_combo.pack(side="left", fill="x", expand=True)
    ttk.Label(
        language_box,
        text=(
            "Це властивість каналу, а не його режиму. EN→UA і UA/RU→EN лишаються; додано UA→UA та RU→UA. "
            "Для моніторингового каналу оберіть фактичну мову його джерел: українські джерела → UA→UA, російські → RU→UA."
        ),
        foreground="#555",
        wraplength=760,
        justify="left",
    ).pack(anchor="w", pady=(6, 0))

    media_box = ttk.LabelFrame(form, text="Media-first / короткі джерела", padding=10)
    media_mode_labels = {
        "Автоматично збагачувати короткий матеріал": MEDIA_ENRICH_AUTO,
        "Вимкнути збагачення медіа": MEDIA_ENRICH_OFF,
    }
    current_mode = str(getattr(ch, "media_enrichment_mode", MEDIA_ENRICH_AUTO) if ch else MEDIA_ENRICH_AUTO)
    current_mode_label = next((label for label, value in media_mode_labels.items() if value == current_mode), next(iter(media_mode_labels)))
    mode_var = tk.StringVar(value=current_mode_label)
    mode_row = ttk.Frame(media_box); mode_row.pack(fill="x", pady=2)
    ttk.Label(mode_row, text="Збагачення", width=32).pack(side="left")
    ttk.Combobox(mode_row, textvariable=mode_var, state="readonly", values=list(media_mode_labels), width=42).pack(side="left", fill="x", expand=True)

    media_first_var = tk.BooleanVar(value=bool(getattr(ch, "media_first_allowed", True) if ch else True))
    ttk.Checkbutton(
        media_box,
        text="Дозволяти оцінку за заголовком + перевіреними даними відео/зображення, якщо текст статті короткий",
        variable=media_first_var,
    ).pack(anchor="w", pady=(6, 4))

    threshold_row = ttk.Frame(media_box); threshold_row.pack(fill="x", pady=2)
    ttk.Label(threshold_row, text="Короткий текст, менше символів", width=32).pack(side="left")
    threshold = ttk.Entry(threshold_row, width=10)
    threshold.insert(0, str(getattr(ch, "media_min_text_chars", 500) if ch else 500))
    threshold.pack(side="left")
    _bind_editing(self, threshold)
    ttk.Label(
        media_box,
        text=(
            "Якщо тексту замало, програма спочатку бере наявні caption/alt/context і метадані YouTube/Vimeo, а вже потім запускає selector. "
            "Відсутність великої статті більше не дорівнює «поганий матеріал». Програма не домислює зміст кадрів, якого не бачить у метаданих."
        ),
        foreground="#555",
        wraplength=760,
        justify="left",
    ).pack(anchor="w", pady=(6, 0))

    pack_kwargs = {"fill": "x", "pady": 8}
    if buttons is not None:
        language_box.pack(before=buttons, **pack_kwargs)
        media_box.pack(before=buttons, **pack_kwargs)
    else:
        language_box.pack(**pack_kwargs)
        media_box.pack(**pack_kwargs)

    def remember(_event=None) -> None:
        self.db._rc45_pending_direction = label_to_value.get(direction_var.get(), rc45.DIRECTION_EN_TO_UK)
        try:
            threshold_value = max(120, min(4000, int(threshold.get().strip() or "500")))
        except ValueError:
            threshold_value = 500
        self.db._rc69_pending_media_settings = {
            "media_enrichment_mode": media_mode_labels.get(mode_var.get(), MEDIA_ENRICH_AUTO),
            "media_first_allowed": bool(media_first_var.get()),
            "media_min_text_chars": threshold_value,
        }

    direction_combo.bind("<<ComboboxSelected>>", remember, add="+")
    for widget in media_box.winfo_children():
        if isinstance(widget, ttk.Combobox):
            widget.bind("<<ComboboxSelected>>", remember, add="+")
    media_first_var.trace_add("write", lambda *_args: remember())
    threshold.bind("<FocusOut>", remember, add="+")
    remember()

    def cleanup(event) -> None:
        if event.widget is not win:
            return
        for attr in ("_rc45_pending_direction", "_rc69_pending_media_settings"):
            try:
                delattr(self.db, attr)
            except AttributeError:
                pass

    win.bind("<Destroy>", cleanup, add="+")


def install_rc69_ui() -> None:
    global _INSTALLED, _PREV_DIALOG
    if _INSTALLED:
        return
    from .ui import MainWindow

    _PREV_DIALOG = MainWindow._channel_dialog
    MainWindow._channel_dialog = _channel_dialog_rc69
    _INSTALLED = True
