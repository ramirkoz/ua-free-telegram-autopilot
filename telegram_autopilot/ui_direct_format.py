from __future__ import annotations

from tkinter import ttk


_DIRECT_DESCRIPTION = (
    "Кожен Telegram-канал має власний список джерел. Нове джерело спочатку проходить baseline: "
    "поточні матеріали запам'ятовуються, але не публікуються. Далі нові англомовні матеріали проходять "
    "перевірку віку, мови, дублів і локальний editorial gate. AI створює один професійний український "
    "научпоп/техножурналістський пост: заголовок і текст разом мають жорсткий ліміт 900 символів. "
    "До поста додається максимум один перевірений релевантний медіафайл; якщо нормального медіа немає, "
    "пост виходить без нього. Публікація йде безпосередньо в Telegram, без проміжних сторінок."
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
        if "Формат: медіа + анонс ≤900 + Telegraph" in text:
            try:
                child.configure(text="Формат: 1 медіа + професійний пост ≤900")
            except Exception:
                pass
        elif "повний український матеріал для Telegraph" in text or ("Telegraph отримує" in text and len(text) > 180):
            try:
                child.configure(text=_DIRECT_DESCRIPTION)
            except Exception:
                pass


def apply_direct_format_ui(app) -> None:
    """Remove legacy Telegraph controls without touching historical Data columns."""
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
