from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from . import APP_NAME
from . import rc59_universal_policy as rc59

_INSTALLED = False
_PREV_DIALOG = None
_PREV_SAVE_CHANNEL = None


def _walk(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _bind_editing(main: Any, widget: tk.Widget) -> None:
    widget.bind("<Control-KeyPress>", main._control_edit_shortcut, add="+")
    widget.bind("<Shift-Insert>", main._paste_shortcut, add="+")
    widget.bind("<Button-3>", main._show_edit_menu, add="+")


def _dialog_mode(win: tk.Toplevel, ch: Any | None) -> str:
    for widget in _walk(win):
        if not isinstance(widget, ttk.Combobox):
            continue
        try:
            values = tuple(str(v) for v in widget.cget("values"))
            value = str(widget.get())
        except tk.TclError:
            continue
        if "Редакційний" in values and "Моніторинговий" in values:
            return "monitoring" if value == "Моніторинговий" else "editorial"
    return "monitoring" if str(getattr(ch, "channel_mode", "editorial") or "editorial").casefold() == "monitoring" else "editorial"


def _mode_labels(mode: str) -> dict[str, str]:
    if str(mode).casefold() == "monitoring":
        return {
            "window": "Тонкі налаштування каналу · моніторинг",
            "selection": "Що включати / що саме моніторити",
            "selection_hint": "Явно опиши сутності, географію, теми, ключові слова або типи подій, які належать цьому моніторинговому каналу. Це налаштування конкретного каналу.",
            "rejection": "Що виключати",
            "rejection_hint": "Явні exclusions цього каналу. Моніторинг не використовує оцінку «цікаво/нецікаво» або Editorial Value.",
            "policy_toggle": "Тонкі правила цього каналу активні",
        }
    return {
        "window": "Тонкі налаштування каналу · редакційний",
        "selection": "Що шукати і пропускати",
        "selection_hint": "Channel Fit перевіряє тільки відповідність цим правилам конкретного каналу. Загальна Editorial Value оцінюється окремим універсальним gate під капотом.",
        "rejection": "Що відхиляти",
        "rejection_hint": "Опиши лише редакційні exclusions саме цього каналу, без універсальних Fact/QA правил.",
        "policy_toggle": "Редакційна політика цього каналу активна",
    }


def _policy_summary(policy: rc59.ChannelPolicy) -> str:
    purpose = " ".join(str(policy.purpose or "").split())
    if not purpose:
        return "Тонкі налаштування ще не описані."
    return purpose[:180] + ("…" if len(purpose) > 180 else "")


def _copy_policy(policy: rc59.ChannelPolicy) -> rc59.ChannelPolicy:
    return rc59.ChannelPolicy(
        channel_id=int(policy.channel_id or 0),
        enabled=bool(policy.enabled),
        purpose=str(policy.purpose or ""),
        audience=str(policy.audience or ""),
        selection_rules=str(policy.selection_rules or ""),
        rejection_rules=str(policy.rejection_rules or ""),
        writing_rules=str(policy.writing_rules or ""),
        style_rules=str(policy.style_rules or ""),
        positive_examples=str(policy.positive_examples or ""),
        negative_examples=str(policy.negative_examples or ""),
        extra_instructions=str(policy.extra_instructions or ""),
        selector_extra_prompt=str(policy.selector_extra_prompt or ""),
        writer_extra_prompt=str(policy.writer_extra_prompt or ""),
        media_policy=str(policy.media_policy or rc59.MEDIA_REQUIRED),
        target_min_chars=int(policy.target_min_chars or 300),
        target_max_chars=int(policy.target_max_chars or 750),
        updated_at=str(policy.updated_at or ""),
    )


def _policy_editor(main: Any, parent: tk.Toplevel, policy: rc59.ChannelPolicy, mode: str) -> rc59.ChannelPolicy | None:
    labels = _mode_labels(mode)
    win = tk.Toplevel(parent)
    win.title(labels["window"])
    win.transient(parent)
    win.grab_set()
    win.geometry("1080x800")
    win.minsize(900, 700)

    tabs = ttk.Notebook(win)
    tabs.pack(fill="both", expand=True, padx=10, pady=10)
    mission = ttk.Frame(tabs, padding=12)
    selection = ttk.Frame(tabs, padding=12)
    writing = ttk.Frame(tabs, padding=12)
    examples = ttk.Frame(tabs, padding=12)
    advanced = ttk.Frame(tabs, padding=12)
    tabs.add(mission, text="Місія")
    tabs.add(selection, text="Відбір")
    tabs.add(writing, text="Написання")
    tabs.add(examples, text="Приклади")
    tabs.add(advanced, text="Розширене")

    ttk.Label(
        mission,
        text=(
            "Це РУЧНІ налаштування тільки цього каналу. Під капотом лишаються лише універсальні механізми програми. "
            "Назва каналу ніколи не використовується як приховане правило."
        ),
        foreground="#555",
        wraplength=980,
        justify="left",
    ).pack(anchor="w", pady=(0, 8))

    fields: dict[str, ScrolledText] = {}

    def text_box(parent_widget: tk.Misc, key: str, label: str, value: str, height: int, hint: str = "") -> None:
        ttk.Label(parent_widget, text=label, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        if hint:
            ttk.Label(parent_widget, text=hint, foreground="#666", wraplength=980, justify="left").pack(anchor="w", pady=(0, 3))
        box = ScrolledText(parent_widget, height=height, wrap="word", undo=True)
        box.pack(fill="both", expand=True, pady=(0, 8))
        box.insert("1.0", str(value or ""))
        _bind_editing(main, box)
        fields[key] = box

    text_box(mission, "purpose", "Про що канал / його місія", policy.purpose, 9, "Саме цей текст, а не назва каналу, задає його призначення.")
    text_box(mission, "audience", "Для кого пишемо", policy.audience, 8, "Аудиторія, рівень підготовки, географія або інші релевантні особливості саме цього каналу.")

    text_box(selection, "selection_rules", labels["selection"], policy.selection_rules, 10, labels["selection_hint"])
    text_box(selection, "rejection_rules", labels["rejection"], policy.rejection_rules, 9, labels["rejection_hint"])
    media_row = ttk.Frame(selection)
    media_row.pack(fill="x", pady=6)
    ttk.Label(media_row, text="Медіа-політика", width=24).pack(side="left")
    media_var = tk.StringVar(value=policy.media_policy if policy.media_policy in rc59.MEDIA_VALUES else rc59.MEDIA_REQUIRED)
    ttk.Combobox(media_row, textvariable=media_var, state="readonly", values=rc59.MEDIA_VALUES, width=18).pack(side="left")
    ttk.Label(
        media_row,
        text="required = без медіа не публікувати · preferred = бажано · optional = не вимагати",
        foreground="#666",
    ).pack(side="left", padx=12)

    text_box(writing, "writing_rules", "Структура і спосіб написання", policy.writing_rules, 9)
    text_box(writing, "style_rules", "Тон і стиль", policy.style_rules, 9)
    length_row = ttk.Frame(writing)
    length_row.pack(fill="x", pady=6)
    ttk.Label(length_row, text="Бажана довжина, символів").pack(side="left")
    min_entry = ttk.Entry(length_row, width=8)
    min_entry.insert(0, str(policy.target_min_chars))
    min_entry.pack(side="left", padx=(10, 4))
    ttk.Label(length_row, text="–").pack(side="left")
    max_entry = ttk.Entry(length_row, width=8)
    max_entry.insert(0, str(policy.target_max_chars))
    max_entry.pack(side="left", padx=4)
    _bind_editing(main, min_entry)
    _bind_editing(main, max_entry)

    text_box(examples, "positive_examples", "Хороші теми / кейси", policy.positive_examples, 10, "Ручні позитивні приклади саме для цього каналу.")
    text_box(examples, "negative_examples", "Небажані теми / кейси", policy.negative_examples, 10, "Ручні негативні приклади саме для цього каналу.")

    text_box(advanced, "extra_instructions", "Додаткові правила каналу", policy.extra_instructions, 6)
    text_box(advanced, "selector_extra_prompt", "Додатковий prompt selector-а", policy.selector_extra_prompt, 6)
    text_box(advanced, "writer_extra_prompt", "Додатковий prompt writer-а", policy.writer_extra_prompt, 6)
    enabled_var = tk.BooleanVar(value=bool(policy.enabled))
    ttk.Checkbutton(advanced, text=labels["policy_toggle"], variable=enabled_var).pack(anchor="w", pady=6)

    result: dict[str, rc59.ChannelPolicy] = {}

    def value(key: str) -> str:
        return fields[key].get("1.0", "end-1c").strip()

    def build_policy() -> rc59.ChannelPolicy:
        try:
            minimum = max(120, int(min_entry.get().strip() or "300"))
            maximum = max(120, int(max_entry.get().strip() or "750"))
        except ValueError as exc:
            raise ValueError("Бажана довжина має бути числом.") from exc
        if maximum < minimum:
            raise ValueError("Максимальна бажана довжина не може бути меншою за мінімальну.")
        return rc59.ChannelPolicy(
            channel_id=int(policy.channel_id or 0),
            enabled=bool(enabled_var.get()),
            purpose=value("purpose"),
            audience=value("audience"),
            selection_rules=value("selection_rules"),
            rejection_rules=value("rejection_rules"),
            writing_rules=value("writing_rules"),
            style_rules=value("style_rules"),
            positive_examples=value("positive_examples"),
            negative_examples=value("negative_examples"),
            extra_instructions=value("extra_instructions"),
            selector_extra_prompt=value("selector_extra_prompt"),
            writer_extra_prompt=value("writer_extra_prompt"),
            media_policy=media_var.get(),
            target_min_chars=minimum,
            target_max_chars=maximum,
        )

    def preview() -> None:
        try:
            current = build_policy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)
            return
        preview_win = tk.Toplevel(win)
        preview_win.title("Фактична політика цього каналу")
        preview_win.geometry("900x700")
        box = ScrolledText(preview_win, wrap="word")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        mode_note = (
            "MONITORING: Editorial Value / цікавість / тематичний баланс не застосовуються.\n\n"
            if str(mode).casefold() == "monitoring"
            else "EDITORIAL: після Channel Fit окремо працює універсальний Editorial Value Gate.\n\n"
        )
        box.insert("1.0", mode_note + rc59.policy_text(current))
        box.configure(state="disabled")

    def save() -> None:
        try:
            result["policy"] = build_policy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=win)
            return
        win.destroy()

    bottom = ttk.Frame(win)
    bottom.pack(fill="x", padx=12, pady=(0, 10))
    ttk.Button(bottom, text="Зберегти тонкі налаштування", command=save).pack(side="right")
    ttk.Button(bottom, text="Скасувати", command=win.destroy).pack(side="right", padx=6)
    ttk.Button(bottom, text="Показати фактичну політику", command=preview).pack(side="left")

    parent.wait_window(win)
    return result.get("policy")


def _save_channel_rc72(db: Any, **kwargs: Any) -> int:
    pending = getattr(db, "_rc72_pending_policy", None)
    if isinstance(pending, rc59.ChannelPolicy):
        kwargs["editorial_profile"] = str(pending.purpose or "").strip() or "Канал із ручною політикою."
    channel_id = int(_PREV_SAVE_CHANNEL(db, **kwargs))
    if isinstance(pending, rc59.ChannelPolicy):
        pending.channel_id = channel_id
        db.rc59_save_channel_policy(pending)
        try:
            delattr(db, "_rc72_pending_policy")
        except AttributeError:
            pass
    return channel_id


def _channel_dialog_rc72(self: Any, ch: Any | None) -> None:
    initial = self.db.rc59_get_channel_policy(int(ch.id)) if ch else rc59.default_policy(None)
    self.db._rc72_pending_policy = _copy_policy(initial)

    before = set(self.root.winfo_children())
    _PREV_DIALOG(self, ch)
    created = [w for w in self.root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)]
    win = created[-1] if created else None
    if win is None:
        return

    try:
        win.title("Канал · RC72")
    except tk.TclError:
        pass

    form = None
    for widget in _walk(win):
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
    policy_box = ttk.LabelFrame(form, text="Тонкі налаштування саме цього каналу", padding=10)
    summary_var = tk.StringVar(value=_policy_summary(self.db._rc72_pending_policy))
    ttk.Label(
        policy_box,
        text=(
            "Місія, аудиторія, inclusion/exclusion, стиль, структура, приклади та додаткові prompts задаються вручну тут. "
            "Універсальна механіка програми не повинна містити особливостей конкретних каналів."
        ),
        foreground="#555",
        wraplength=760,
        justify="left",
    ).pack(anchor="w")
    ttk.Label(policy_box, textvariable=summary_var, wraplength=760, justify="left").pack(anchor="w", pady=(6, 6))

    def edit_policy() -> None:
        current = getattr(self.db, "_rc72_pending_policy", initial)
        updated = _policy_editor(self, win, _copy_policy(current), _dialog_mode(win, ch))
        if updated is None:
            return
        self.db._rc72_pending_policy = updated
        summary_var.set(_policy_summary(updated))

    ttk.Button(policy_box, text="Редагувати тонкі налаштування каналу", command=edit_policy).pack(anchor="w")
    if buttons is not None:
        policy_box.pack(before=buttons, fill="x", pady=8)
    else:
        policy_box.pack(fill="x", pady=8)

    def cleanup(event: tk.Event) -> None:
        if event.widget is not win:
            return
        try:
            delattr(self.db, "_rc72_pending_policy")
        except AttributeError:
            pass

    win.bind("<Destroy>", cleanup, add="+")


def install_rc72_channel_policy_ui() -> None:
    global _INSTALLED, _PREV_DIALOG, _PREV_SAVE_CHANNEL
    if _INSTALLED:
        return
    from .database import Database
    from .ui import MainWindow

    _PREV_DIALOG = MainWindow._channel_dialog
    _PREV_SAVE_CHANNEL = Database.save_channel
    Database.save_channel = _save_channel_rc72
    MainWindow._channel_dialog = _channel_dialog_rc72
    _INSTALLED = True
