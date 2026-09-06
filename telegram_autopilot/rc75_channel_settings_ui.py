from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import APP_NAME, __version__
from . import rc59_universal_policy as rc59
from . import rc72_channel_policy_ui as rc72ui
from . import rc73_channel_weights_ui as rc73ui

_INSTALLED = False
_PREV_DIALOG: Callable[..., Any] | None = None
_PREV_POLICY_EDITOR: Callable[..., Any] | None = None
_PREV_WEIGHTS_EDITOR: Callable[..., Any] | None = None
_PREV_WEIGHT_DIALOG: Callable[..., Any] | None = None


def _walk(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _policy_signature(policy: Any) -> tuple[Any, ...]:
    if not isinstance(policy, rc59.ChannelPolicy):
        return ()
    return (
        bool(policy.enabled),
        str(policy.purpose or ""),
        str(policy.audience or ""),
        str(policy.selection_rules or ""),
        str(policy.rejection_rules or ""),
        str(policy.writing_rules or ""),
        str(policy.style_rules or ""),
        str(policy.positive_examples or ""),
        str(policy.negative_examples or ""),
        str(policy.extra_instructions or ""),
        str(policy.selector_extra_prompt or ""),
        str(policy.writer_extra_prompt or ""),
        str(policy.media_policy or ""),
        int(policy.target_min_chars or 0),
        int(policy.target_max_chars or 0),
    )


def _weights_signature(items: Any) -> tuple[tuple[str, float], ...]:
    if not isinstance(items, list):
        return ()
    clean: list[tuple[str, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split()).strip()
        if not name:
            continue
        try:
            weight = float(item.get("weight", 0) or 0)
        except (TypeError, ValueError):
            continue
        clean.append((name, round(weight, 6)))
    return tuple(clean)


def _widget_signature(win: tk.Toplevel) -> tuple[tuple[str, str, str], ...]:
    """Return editable values from the *main* channel dialog.

    Fine-policy and category subdialogs are separate Toplevels, so they are not
    included here. Their pending objects are appended separately by
    ``_draft_signature``. This keeps the unsaved-change guard deterministic and
    independent of the channel name or policy contents.
    """
    values: list[tuple[str, str, str]] = []
    for widget in _walk(win):
        key = str(widget)
        try:
            if isinstance(widget, (ttk.Entry, ttk.Combobox, tk.Entry)):
                values.append((key, "value", str(widget.get())))
                continue
            if isinstance(widget, (ttk.Checkbutton, tk.Checkbutton)):
                var_name = str(widget.cget("variable") or "")
                if var_name:
                    values.append((key, "check", str(win.getvar(var_name))))
        except (tk.TclError, AttributeError):
            continue
    return tuple(values)


def _draft_signature(db: Any, win: tk.Toplevel) -> tuple[Any, ...]:
    return (
        _widget_signature(win),
        _policy_signature(getattr(db, "_rc72_pending_policy", None)),
        _weights_signature(getattr(db, "_rc73_pending_weights", None)),
    )


def _new_toplevel(parent: tk.Misc, before: set[tk.Misc]) -> tk.Toplevel | None:
    candidates = [
        child for child in parent.winfo_children()
        if child not in before and isinstance(child, tk.Toplevel)
    ]
    return candidates[-1] if candidates else None


def _replace_button_text(win: tk.Toplevel, old: str, new: str) -> bool:
    for widget in _walk(win):
        if not isinstance(widget, ttk.Button):
            continue
        try:
            if str(widget.cget("text")) == old:
                widget.configure(text=new)
                return True
        except tk.TclError:
            continue
    return False


def _schedule_modal_button_relabel(parent: tk.Misc, before: set[tk.Misc], old: str, new: str) -> None:
    def apply() -> None:
        try:
            win = _new_toplevel(parent, before)
            if win is not None:
                _replace_button_text(win, old, new)
        except tk.TclError:
            return
    parent.after_idle(apply)


def _policy_editor_rc75(main: Any, parent: tk.Toplevel, policy: rc59.ChannelPolicy, mode: str):
    before = set(parent.winfo_children())
    _schedule_modal_button_relabel(parent, before, "Зберегти тонкі налаштування", "Застосувати до форми каналу")
    return _PREV_POLICY_EDITOR(main, parent, policy, mode)


def _weights_editor_rc75(parent: tk.Toplevel, items: list[dict[str, Any]], mode: str):
    before = set(parent.winfo_children())
    _schedule_modal_button_relabel(parent, before, "Зберегти", "Застосувати до форми каналу")
    return _PREV_WEIGHTS_EDITOR(parent, items, mode)


def _weight_dialog_rc75(parent: tk.Misc, title: str, *, name: str = "", weight: float = 10.0):
    before = set(parent.winfo_children())
    label = "Застосувати зміну" if name else "Додати до списку"
    _schedule_modal_button_relabel(parent, before, "Зберегти", label)
    return _PREV_WEIGHT_DIALOG(parent, title, name=name, weight=weight)


def _find_outer_save_button(win: tk.Toplevel) -> ttk.Button | None:
    candidates: list[ttk.Button] = []
    for widget in _walk(win):
        if not isinstance(widget, ttk.Button):
            continue
        try:
            text = str(widget.cget("text"))
        except tk.TclError:
            continue
        if text in {"Зберегти", "Зберегти канал"}:
            candidates.append(widget)
    return candidates[-1] if candidates else None


def _channel_dialog_rc75(self: Any, ch: Any | None) -> None:
    before = set(self.root.winfo_children())
    _PREV_DIALOG(self, ch)
    created = [
        widget for widget in self.root.winfo_children()
        if widget not in before and isinstance(widget, tk.Toplevel)
    ]
    win = created[-1] if created else None
    if win is None:
        return

    try:
        win.title(f"Канал · {__version__}")
    except tk.TclError:
        pass

    save_button = _find_outer_save_button(win)
    if save_button is not None:
        try:
            save_button.configure(text="Зберегти канал")
        except tk.TclError:
            pass

    # All nested editors now explicitly say "Apply to channel form". One outer
    # button is the single persistence boundary. Capture the complete draft only
    # after every older UI layer has decorated the window.
    try:
        win.update_idletasks()
    except tk.TclError:
        return
    initial_signature = _draft_signature(self.db, win)

    def has_unsaved_changes() -> bool:
        try:
            return _draft_signature(self.db, win) != initial_signature
        except tk.TclError:
            return False

    def request_close() -> None:
        if not has_unsaved_changes():
            win.destroy()
            return
        choice = messagebox.askyesnocancel(
            APP_NAME,
            "У каналі є незбережені зміни.\n\n"
            "Так — зберегти весь канал одним записом.\n"
            "Ні — закрити й відкинути зміни.\n"
            "Скасувати — повернутися до редагування.",
            parent=win,
        )
        if choice is None:
            return
        if choice:
            if save_button is None:
                messagebox.showerror(APP_NAME, "Не знайдено кнопку «Зберегти канал».", parent=win)
                return
            save_button.invoke()
            return
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", request_close)


def install_rc75_channel_settings_ui() -> None:
    """Make per-channel editing one explicit, loss-resistant transaction.

    RC75 is channel-neutral. It does not know any channel names, subjects,
    languages, timings, prompts or weights. Those remain operator-owned channel
    configuration. The patch only fixes UI persistence semantics.
    """
    global _INSTALLED, _PREV_DIALOG, _PREV_POLICY_EDITOR, _PREV_WEIGHTS_EDITOR, _PREV_WEIGHT_DIALOG
    if _INSTALLED:
        return

    from .ui import MainWindow

    _PREV_DIALOG = MainWindow._channel_dialog
    _PREV_POLICY_EDITOR = rc72ui._policy_editor
    _PREV_WEIGHTS_EDITOR = rc73ui._weights_editor
    _PREV_WEIGHT_DIALOG = rc73ui._weight_dialog

    rc72ui._policy_editor = _policy_editor_rc75
    rc73ui._weights_editor = _weights_editor_rc75
    rc73ui._weight_dialog = _weight_dialog_rc75
    MainWindow._channel_dialog = _channel_dialog_rc75
    _INSTALLED = True
