from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk

from . import APP_NAME
from .rc48_ui import _analytics_dialog
from .rc51_feedback import refresh_feedback_metrics

_INSTALLED = False


def _age_label(value: str) -> str:
    text = str(value or "").strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
    except Exception:
        return ""
    if hours < 1:
        return f"{max(1, int(hours * 60))} хв"
    if hours < 24:
        return f"{int(hours)} год"
    return f"{int(hours // 24)} д"


def install_rc51_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from .ui import MainWindow

    old_build = MainWindow._build
    old_channel_dialog = MainWindow._channel_dialog

    def build_rc51(self):
        old_build(self)
        tab = getattr(self, "memory_tab", None)
        if tab is None:
            return
        for child in tab.winfo_children():
            child.destroy()

        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 8))
        self.rc51_feedback_status = tk.StringVar(value="Реакційна пам'ять: очікує Telegram-дані.")
        ttk.Label(top, textvariable=self.rc51_feedback_status, font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(
            top,
            text="Налаштувати Telegram Analytics",
            command=lambda: _analytics_dialog(self.root, self),
        ).pack(side="right", padx=4)
        ttk.Button(
            top,
            text="Оновити реакції зараз",
            command=self._rc48_refresh_metrics_now,
        ).pack(side="right", padx=4)

        ttk.Label(
            tab,
            text=(
                "RC51 навчається окремо для кожного каналу тільки на трьох реакціях: "
                "👍 = подобається, 🔥 = сильний позитивний сигнал, 👎 = тимчасово менше схожого. "
                "Відсутність реакції нейтральна. Старі сигнали слабшають і після 7 днів не впливають на відбір. "
                "Ручні тематичні категорії та відсоткові ваги більше не беруть участі у публікації."
            ),
            wraplength=1080,
            foreground="#555",
            justify="left",
        ).pack(anchor="w", pady=(0, 9))

        cols = ("post", "age", "like", "dislike", "fire", "signal")
        self.rc51_feedback_tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        heads = ("Пост", "Вік", "👍", "👎", "🔥", "Сигнал")
        widths = (690, 75, 65, 65, 65, 85)
        for col, head, width in zip(cols, heads, widths):
            self.rc51_feedback_tree.heading(col, text=head)
            self.rc51_feedback_tree.column(col, width=width, anchor="w" if col == "post" else "center")
        self.rc51_feedback_tree.pack(fill="both", expand=True)

        self.rc51_feedback_note = tk.StringVar(value="")
        ttk.Label(
            tab,
            textvariable=self.rc51_feedback_note,
            foreground="#666",
            wraplength=1080,
        ).pack(anchor="w", pady=(8, 0))

    def refresh_feedback(self):
        tree = getattr(self, "rc51_feedback_tree", None)
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)

        channel_id = int(self.current_channel_id or 0)
        if not channel_id:
            self.rc51_feedback_status.set("Реакційна пам'ять: оберіть канал.")
            self.rc51_feedback_note.set("")
            return
        try:
            channel = self.db.get_channel(channel_id)
            stats = self.db.rc51_feedback_stats(channel_id)
            rows = self.db.rc51_feedback_rows(channel_id, days=7, limit=120)
        except Exception as exc:
            self.rc51_feedback_status.set(f"Реакційна пам'ять: {exc}")
            return

        rated = int(stats.get("rated") or 0)
        tracked = int(stats.get("tracked") or 0)
        likes = int(stats.get("likes") or 0)
        dislikes = int(stats.get("dislikes") or 0)
        fires = int(stats.get("fires") or 0)
        name = str(getattr(channel, "name", "") or "") if channel else ""
        state = "АКТИВНА" if rated else "ЧЕКАЄ ПЕРШОЇ РЕАКЦІЇ"
        self.rc51_feedback_status.set(
            f"{name}: {state} · постів у 7-денному вікні {tracked} · оцінених {rated} · 👍 {likes} · 👎 {dislikes} · 🔥 {fires}"
        )

        def signal(row):
            return int(row.get("likes") or 0) + 2 * int(row.get("fires") or 0) - 2 * int(row.get("dislikes") or 0)

        rows = sorted(rows, key=lambda row: (-abs(signal(row)), -int(row.get("fires") or 0), str(row.get("published_at") or "")), reverse=False)
        for row in rows:
            text = " ".join(str(row.get("teaser_text") or row.get("title") or "").replace("\n", " ").split())
            if len(text) > 135:
                text = text[:132].rstrip() + "…"
            value = signal(row)
            tree.insert(
                "", "end",
                values=(
                    text,
                    _age_label(str(row.get("published_at") or "")),
                    int(row.get("likes") or 0),
                    int(row.get("dislikes") or 0),
                    int(row.get("fires") or 0),
                    f"{value:+d}",
                ),
            )

        if rated:
            self.rc51_feedback_note.set(
                "Позитивні реакції піднімають схожі матеріали й дають автору стильові приклади. "
                "Свіжий 👎 може тимчасово відсікти дуже схожу історію; його вплив автоматично слабшає."
            )
        else:
            self.rc51_feedback_note.set(
                "Поки немає 👍 / 👎 / 🔥, Autopilot працює нейтрально й продовжує досліджувати нові теми."
            )

    def refresh_metrics_now(self):
        channel_id = int(self.current_channel_id or 0)
        if not channel_id:
            messagebox.showwarning(APP_NAME, "Спочатку оберіть канал.", parent=self.root)
            return
        channel = self.db.get_channel(channel_id)
        if channel is None:
            return
        self.rc51_feedback_status.set(f"{channel.name}: читаю 👍 / 👎 / 🔥 з Telegram…")

        def worker():
            summary = refresh_feedback_metrics(self.db, channel, force=True)

            def finish():
                self._rc48_refresh_memory()
                if summary.get("error"):
                    messagebox.showwarning(APP_NAME, "Telegram Analytics: " + str(summary.get("error")), parent=self.root)
                elif not summary.get("configured"):
                    messagebox.showinfo(APP_NAME, "Telegram Analytics ще не налаштовано.", parent=self.root)
                else:
                    text = f"Перевірено постів: {summary.get('checked', 0)}; оновлено реакцій: {summary.get('saved', 0)}."
                    if summary.get("policy_warning"):
                        text += "\n\nРеакції прочитані, але Telegram не дозволив автоматично обмежити меню до 👍 👎 🔥: " + str(summary.get("policy_warning"))
                    messagebox.showinfo(APP_NAME, text, parent=self.root)

            try:
                self._ui_queue.put(finish)
            except Exception:
                pass

        threading.Thread(target=worker, name="RC51Feedback", daemon=True).start()

    def channel_dialog_rc51(self, ch):
        before = {str(widget) for widget in self.root.winfo_children()}
        old_channel_dialog(self, ch)
        candidates = [
            widget for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel) and str(widget) not in before and widget.winfo_exists()
        ]
        if not candidates:
            return
        win = candidates[-1]
        try:
            win.title("Канал · реакційне навчання")
            win.geometry("900x650")
        except tk.TclError:
            pass

        body = None
        for child in win.winfo_children():
            if isinstance(child, ttk.Frame):
                body = child
                break
        if body is None:
            return
        for child in list(body.winfo_children()):
            if not isinstance(child, ttk.LabelFrame):
                continue
            try:
                text = str(child.cget("text"))
            except tk.TclError:
                continue
            if text == "Редакційні ваги цього каналу":
                child.destroy()
            elif text == "Редакційний профіль цього каналу":
                try:
                    child.configure(text="Базовий опис / тон каналу")
                    labels = [w for w in child.winfo_children() if isinstance(w, ttk.Label)]
                    if labels:
                        labels[0].configure(
                            text=(
                                "Це довідковий опис тону, а не тематичний фільтр. Відбір матеріалів RC51 навчається на 👍 / 👎 / 🔥."
                            )
                        )
                except tk.TclError:
                    pass

    MainWindow._build = build_rc51
    MainWindow._rc48_refresh_memory = refresh_feedback
    MainWindow._rc48_refresh_metrics_now = refresh_metrics_now
    MainWindow._channel_dialog = channel_dialog_rc51
    _INSTALLED = True
