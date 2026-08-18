from __future__ import annotations

from tkinter import ttk


_DIRECT_DESCRIPTION = (
    "Кожен Telegram-канал має власний список джерел. Нове джерело спочатку проходить baseline: "
    "поточні матеріали запам'ятовуються, але не публікуються. Далі нові англомовні матеріали проходять "
    "перевірку віку, мови, дублів і локальний editorial gate. AI створює один професійний український "
    "научпоп/техножурналістський пост. Якщо є надійне релевантне медіа, заголовок і текст разом мають "
    "жорсткий ліміт 900 символів і додається максимум один медіафайл. Якщо медіа немає, публікується "
    "одне текстове повідомлення до 4096 символів. Незавершений AI-текст не обрізається, а відхиляється "
    "і переписується. Публікація йде безпосередньо в Telegram, без проміжних сторінок."
)


def _scrub_widget_tree(widget) -> None:
    for child in list(widget.winfo_children()):
        _scrub_widget_tree(child)
        try:
            text = str(child.cget("text") or "")
        except Exception:
            continue
        if text == "Тест Telegraph" or text.startswith("Telegraph access token"):
            try:
                child.destroy()
            except Exception:
                pass
            continue
        if "Формат: медіа + анонс ≤900 + Telegraph" in text or "Формат: 1 медіа + професійний пост ≤900" in text:
            try:
                child.configure(text="Формат: 1 медіа + ≤900 / без медіа ≤4096")
            except Exception:
                pass
        elif "повний український матеріал для Telegraph" in text or ("Telegraph отримує" in text and len(text) > 180):
            try:
                child.configure(text=_DIRECT_DESCRIPTION)
            except Exception:
                pass


def apply_direct_format_ui(app) -> None:
    """Hide legacy Telegraph UI while preserving historical Data columns on disk."""
    _scrub_widget_tree(app.root)
    tree = getattr(app, "history_tree", None)
    if isinstance(tree, ttk.Treeview):
        try:
            tree.configure(displaycolumns=tuple(c for c in tree["columns"] if c != "telegraph"))
        except Exception:
            pass

    original = app._channel_dialog

    def wrapped(channel):
        result = original(channel)
        try:
            app.root.after_idle(lambda: _scrub_widget_tree(app.root))
        except Exception:
            pass
        return result

    app._channel_dialog = wrapped
