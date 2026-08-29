from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .rc51_feedback import FEEDBACK_WINDOW_DAYS
from .rc51_ui import _age_label
from .rc48_ui import _analytics_dialog
from .rc52_feedback import style_feedback_signal, topic_feedback_signal

_INSTALLED = False


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for child in children:
        yield from _walk(child)


def install_rc52_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from .ui import MainWindow

    old_build = MainWindow._build
    old_channel_dialog = MainWindow._channel_dialog

    def build_rc52(self):
        old_build(self)
        tab = getattr(self, "memory_tab", None)
        if tab is None:
            return
        for child in tab.winfo_children():
            child.destroy()

        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 8))
        self.rc51_feedback_status = tk.StringVar(value="Навчання: очікує Telegram-реакції.")
        ttk.Label(top, textvariable=self.rc51_feedback_status, font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(top, text="Налаштувати Telegram Analytics", command=lambda: _analytics_dialog(self.root, self)).pack(side="right", padx=4)
        ttk.Button(top, text="Оновити реакції зараз", command=self._rc48_refresh_metrics_now).pack(side="right", padx=4)

        ttk.Label(
            tab,
            text=(
                "RC52 розділяє два незалежні сигнали. 👍 = цікава тема, тому схожі матеріали отримують пріоритет. "
                "👎 = тема/сюжет нецікаві, тому дуже схожі матеріали тимчасово знижуються або пропускаються. "
                "🔥 = текст добре написаний: тільки такі пости стають прикладами стилю для автора. "
                "На один пост можна ставити дві реакції, тому 👍+🔥 означає «і тема, і текст», а 👎+🔥 — «тема не потрібна, але написано добре». "
                "Відсутність реакції нейтральна. Вікно навчання — 7 днів."
            ),
            wraplength=1080,
            foreground="#555",
            justify="left",
        ).pack(anchor="w", pady=(0, 9))

        cols = ("post", "age", "like", "dislike", "fire", "topic", "style")
        self.rc51_feedback_tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        heads = ("Пост", "Вік", "👍", "👎", "🔥", "Тема", "Стиль")
        widths = (625, 70, 55, 55, 55, 75, 90)
        for col, head, width in zip(cols, heads, widths):
            self.rc51_feedback_tree.heading(col, text=head)
            self.rc51_feedback_tree.column(col, width=width, anchor="w" if col == "post" else "center")
        self.rc51_feedback_tree.pack(fill="both", expand=True)

        self.rc51_feedback_note = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.rc51_feedback_note, foreground="#666", wraplength=1080).pack(anchor="w", pady=(8, 0))

    def refresh_feedback_rc52(self):
        tree = getattr(self, "rc51_feedback_tree", None)
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)
        channel_id = int(self.current_channel_id or 0)
        if not channel_id:
            self.rc51_feedback_status.set("Навчання: оберіть канал.")
            self.rc51_feedback_note.set("")
            return
        try:
            channel = self.db.get_channel(channel_id)
            stats = self.db.rc51_feedback_stats(channel_id)
            rows = self.db.rc51_feedback_rows(channel_id, days=FEEDBACK_WINDOW_DAYS, limit=120)
        except Exception as exc:
            self.rc51_feedback_status.set(f"Навчання: {exc}")
            return

        topic_posts = sum(1 for row in rows if int(row.get("likes") or 0) or int(row.get("dislikes") or 0))
        style_posts = sum(1 for row in rows if int(row.get("fires") or 0))
        tracked = int(stats.get("tracked") or 0)
        likes = int(stats.get("likes") or 0)
        dislikes = int(stats.get("dislikes") or 0)
        fires = int(stats.get("fires") or 0)
        name = str(getattr(channel, "name", "") or "") if channel else ""
        state = "АКТИВНЕ" if (topic_posts or style_posts) else "ЧЕКАЄ ПЕРШОЇ РЕАКЦІЇ"
        self.rc51_feedback_status.set(
            f"{name}: {state} · постів {tracked} · тема {topic_posts} · стиль {style_posts} · 👍 {likes} · 👎 {dislikes} · 🔥 {fires}"
        )

        def importance(row):
            return abs(topic_feedback_signal(row)) + 1.5 * style_feedback_signal(row)

        rows = sorted(rows, key=lambda row: (importance(row), str(row.get("published_at") or "")), reverse=True)
        for row in rows:
            text = " ".join(str(row.get("teaser_text") or row.get("title") or "").replace("\n", " ").split())
            if len(text) > 122:
                text = text[:119].rstrip() + "…"
            topic = topic_feedback_signal(row)
            style = style_feedback_signal(row)
            topic_label = "—" if topic == 0 else f"{topic:+.0f}"
            style_label = "еталон" if style > 0 else "—"
            tree.insert(
                "", "end",
                values=(
                    text,
                    _age_label(str(row.get("published_at") or "")),
                    int(row.get("likes") or 0),
                    int(row.get("dislikes") or 0),
                    int(row.get("fires") or 0),
                    topic_label,
                    style_label,
                ),
            )

        self.rc51_feedback_note.set(
            "👍/👎 навчають тільки відбору тем. 🔥 навчає тільки написанню. Комбінації реакцій не змішують ці два контури."
        )

    def channel_dialog_rc52(self, ch):
        old_channel_dialog(self, ch)
        for widget in _walk(self.root):
            if not isinstance(widget, ttk.Label):
                continue
            try:
                text = str(widget.cget("text") or "")
            except Exception:
                continue
            if "Відбір матеріалів RC51" in text or "👍 / 👎 / 🔥" in text:
                try:
                    widget.configure(text="Теми навчаються на 👍/👎. Стиль написання навчається окремо тільки на 🔥.")
                except Exception:
                    pass

    MainWindow._build = build_rc52
    MainWindow._rc48_refresh_memory = refresh_feedback_rc52
    MainWindow._channel_dialog = channel_dialog_rc52
    _INSTALLED = True
