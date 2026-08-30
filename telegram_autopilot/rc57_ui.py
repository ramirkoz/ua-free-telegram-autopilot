from __future__ import annotations

import logging
import queue
import statistics
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import APP_NAME
from .rc53_hardening import reaction_health
from .rc57_feedback_model import (
    FEEDBACK_WINDOW_DAYS,
    TOTAL_TIMEOUT_SECONDS,
    age_label,
    audience_performance_score,
    audience_raw_rate,
    coverage_label,
    row_int,
    row_value,
)
from .rc57_telegram_feedback import refresh_feedback_metrics_rc57

LOG = logging.getLogger("telegram_autopilot.rc57")
_INFLIGHT_ATTR = "_rc57_feedback_refresh_inflight"


def _walk(widget):
    if widget is None:
        return
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for child in children:
        yield from _walk(child)


def install_fault_tolerant_ui_queue() -> None:
    from .ui import MainWindow, _LOG

    def drain_rc57(self):
        if self._closing:
            return
        started = time.perf_counter()
        processed = 0
        while processed < 60 and (time.perf_counter() - started) < 0.010:
            try:
                item = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if callable(item):
                    callback, args, kwargs = item, (), {}
                    _LOG.warning("UI queue accepted legacy bare callback; caller should use _post_ui")
                elif isinstance(item, tuple) and len(item) == 3 and callable(item[0]):
                    callback, args, kwargs = item
                else:
                    _LOG.error("UI queue dropped malformed item type=%s", type(item).__name__)
                    processed += 1
                    continue
                callback(*args, **kwargs)
            except tk.TclError:
                if not self._closing:
                    _LOG.debug("UI callback TclError", exc_info=True)
            except Exception:
                _LOG.exception("UI callback failed but queue pump stays alive")
            processed += 1
        if not self._closing:
            self.root.after(50 if not self._ui_queue.empty() else 100, self._drain_ui_queue)

    MainWindow._drain_ui_queue = drain_rc57


def _status_var(main_window):
    return getattr(main_window, "rc57_feedback_status", None) or getattr(main_window, "rc51_feedback_status", None)


def _post_status(main_window, text: str) -> None:
    def apply():
        status = _status_var(main_window)
        if status is not None:
            status.set(text)
    main_window._post_ui(apply)


def refresh_metrics_now_rc57(main_window) -> None:
    channel_id = int(getattr(main_window, "current_channel_id", 0) or 0)
    if not channel_id:
        messagebox.showwarning(APP_NAME, "Спочатку оберіть канал.", parent=main_window.root)
        return
    channel = main_window.db.get_channel(channel_id)
    if channel is None:
        return
    status = _status_var(main_window)
    if bool(getattr(main_window, _INFLIGHT_ATTR, False)):
        if status is not None:
            status.set(f"{channel.name}: попереднє оновлення ще виконується · максимум {TOTAL_TIMEOUT_SECONDS} с.")
        return

    setattr(main_window, _INFLIGHT_ATTR, True)
    if status is not None:
        status.set(f"{channel.name}: підключаюсь до Telegram · максимум {TOTAL_TIMEOUT_SECONDS} с…")

    def worker() -> None:
        summary = refresh_feedback_metrics_rc57(
            main_window.db,
            channel,
            force=True,
            progress=lambda text: _post_status(main_window, f"{channel.name}: {text}"),
        )

        def finish() -> None:
            setattr(main_window, _INFLIGHT_ATTR, False)
            try:
                main_window._rc48_refresh_memory()
            except Exception:
                LOG.exception("feedback UI refresh failed")
            current = _status_var(main_window)
            if summary.get("error"):
                if current is not None:
                    current.set(f"{channel.name}: ❌ {summary.get('error')}")
                messagebox.showwarning(APP_NAME, "Telegram Analytics: " + str(summary.get("error")), parent=main_window.root)
                return
            warning = str(summary.get("warning") or "")
            text = (
                f"Перевірено постів: {summary.get('checked', 0)}; "
                f"адмінів: {summary.get('admin_count', 0)}; "
                f"час: {float(summary.get('elapsed', 0.0)):.1f} с."
            )
            if warning:
                text += "\n\n⚠ " + warning
            if current is not None:
                current.set(f"{channel.name}: ✅ feedback оновлено · {summary.get('checked', 0)} постів")
            messagebox.showinfo(APP_NAME, text, parent=main_window.root)

        try:
            main_window._post_ui(finish)
        except Exception:
            setattr(main_window, _INFLIGHT_ATTR, False)

    threading.Thread(target=worker, name="RC57FeedbackRefresh", daemon=True).start()


def build_memory_rc57(self) -> None:
    tab = getattr(self, "memory_tab", None)
    if tab is None:
        return
    for child in tab.winfo_children():
        child.destroy()

    top = ttk.Frame(tab)
    top.pack(fill="x", pady=(0, 8))
    self.rc57_feedback_status = tk.StringVar(value="Feedback: очікує Telegram.")
    self.rc51_feedback_status = self.rc57_feedback_status
    ttk.Label(top, textvariable=self.rc57_feedback_status, font=("Segoe UI", 10, "bold")).pack(side="left")
    ttk.Button(top, text="Налаштувати Telegram Analytics", command=lambda: analytics_dialog_rc57(self.root, self)).pack(side="right", padx=4)
    ttk.Button(top, text="Оновити реакції зараз", command=self._rc48_refresh_metrics_now).pack(side="right", padx=4)

    ttk.Label(
        tab,
        text=(
            "EDITOR SIGNAL: реакції всіх адміністраторів каналу. 👍 = цікава тема, 👎 = тема не потрібна, "
            "🔥 = добре написано. Кожен адмін дає окремий голос; 👍+🔥 та 👎+🔥 залишаються двома незалежними сигналами. "
            "Адмінський 👎 може тимчасово приглушити дуже схожу тему, а 🔥 навчає стилю."
        ),
        wraplength=1150, justify="left", foreground="#444",
    ).pack(anchor="w", pady=(0, 5))
    ttk.Label(
        tab,
        text=(
            "AUDIENCE SIGNAL: реакції читачів, перегляди, пересилання й відповіді. Вони нормалізуються на охоплення і "
            "впливають на пріоритет схожих тем та джерел, але НІКОЛИ не дають жорсткого veto і не вчать стиль напряму. "
            "Вікно навчання — 7 днів."
        ),
        wraplength=1150, justify="left", foreground="#555",
    ).pack(anchor="w", pady=(0, 9))

    cols = ("post", "age", "alike", "adis", "afire", "editor", "audience", "views", "react", "rate", "fwd", "coverage")
    self.rc57_feedback_tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
    self.rc51_feedback_tree = self.rc57_feedback_tree
    heads = ("Пост", "Вік", "Адм 👍", "Адм 👎", "Адм 🔥", "Editor", "Audience", "Перегл.", "Реакції", "ER", "Пересл.", "Покриття")
    widths = (500, 58, 55, 55, 55, 65, 78, 70, 70, 58, 60, 90)
    for col, head, width in zip(cols, heads, widths):
        self.rc57_feedback_tree.heading(col, text=head)
        self.rc57_feedback_tree.column(col, width=width, anchor="w" if col == "post" else "center")
    self.rc57_feedback_tree.pack(fill="both", expand=True)
    self.rc57_feedback_note = tk.StringVar(value="")
    self.rc51_feedback_note = self.rc57_feedback_note
    ttk.Label(tab, textvariable=self.rc57_feedback_note, foreground="#666", wraplength=1150).pack(anchor="w", pady=(8, 0))


def _audience_label(row, baseline: float) -> str:
    score = audience_performance_score(row, baseline)
    if row_int(row, "views") <= 0:
        return "—"
    if score >= 0.75:
        return "сильно +"
    if score >= 0.20:
        return "+"
    if score <= -0.65:
        return "слабо"
    if score <= -0.20:
        return "−"
    return "норма"


def refresh_memory_rc57(self) -> None:
    tree = getattr(self, "rc57_feedback_tree", None)
    if tree is None:
        return
    for iid in tree.get_children():
        tree.delete(iid)
    channel_id = int(getattr(self, "current_channel_id", 0) or 0)
    if not channel_id:
        self.rc57_feedback_status.set("Feedback: оберіть канал.")
        return
    health = reaction_health()
    if not health.ready:
        self.rc57_feedback_status.set("❌ Telegram Analytics: " + health.message)
        self.rc57_feedback_note.set("Завершіть MTProto-авторизацію. До цього editor/audience feedback не оновлюється.")
        return
    try:
        channel = self.db.get_channel(channel_id)
        rows = self.db.rc51_feedback_rows(channel_id, days=FEEDBACK_WINDOW_DAYS, limit=120)
        stats = self.db.rc57_feedback_stats(channel_id)
    except Exception as exc:
        self.rc57_feedback_status.set(f"Feedback: {exc}")
        return

    rates = [audience_raw_rate(row) for row in rows if row_int(row, "views") >= 25]
    baseline = statistics.median(rates) if rates else 0.0
    name = str(getattr(channel, "name", "") or "") if channel else ""
    self.rc57_feedback_status.set(
        f"{name}: MTProto OK · адмінів {int(stats.get('admin_count') or 0)} · "
        f"editor-постів {int(stats.get('editor_rated_posts') or 0)} · audience-постів {int(stats.get('audience_rated_posts') or 0)} · "
        f"👍 {int(stats.get('likes') or 0)} · 👎 {int(stats.get('dislikes') or 0)} · 🔥 {int(stats.get('fires') or 0)}"
    )

    from .rc52_feedback import topic_feedback_signal
    rows = sorted(
        rows,
        key=lambda row: (
            abs(topic_feedback_signal(row)) + abs(audience_performance_score(row, baseline)),
            str(row_value(row, "published_at", "")),
        ),
        reverse=True,
    )
    for row in rows:
        text = " ".join(str(row_value(row, "teaser_text", "") or row_value(row, "title", "")).replace("\n", " ").split())
        if len(text) > 100:
            text = text[:97].rstrip() + "…"
        views = row_int(row, "views")
        reactions = row_int(row, "audience_total")
        er = (100.0 * reactions / views) if views > 0 else 0.0
        editor_score = topic_feedback_signal(row)
        tree.insert(
            "", "end",
            values=(
                text,
                age_label(str(row_value(row, "published_at", ""))),
                row_int(row, "likes"), row_int(row, "dislikes"), row_int(row, "fires"),
                "—" if editor_score == 0 else f"{editor_score:+.0f}",
                _audience_label(row, baseline), views, reactions,
                f"{er:.1f}%" if views else "—", row_int(row, "forwards"),
                coverage_label(str(row_value(row, "editor_coverage", ""))),
            ),
        )
    self.rc57_feedback_note.set(
        "Editor має вищу вагу за Audience. Audience коригує пріоритет лише м'яко; жорстке приглушення можливе тільки через адмінський 👎 на дуже схожій історії."
    )


def analytics_dialog_rc57(parent, main_window) -> None:
    from . import rc54_mtproto
    before = {str(w) for w in parent.winfo_children()}
    rc54_mtproto._analytics_dialog_rc54(parent, main_window)
    candidates = [w for w in parent.winfo_children() if isinstance(w, tk.Toplevel) and str(w) not in before and w.winfo_exists()]
    if not candidates:
        return
    win = candidates[-1]
    try:
        win.title("Telegram Analytics")
    except Exception:
        pass
    for widget in _walk(win):
        if not isinstance(widget, ttk.Label):
            continue
        try:
            text = str(widget.cget("text") or "")
        except Exception:
            continue
        if "читає тільки реакції" in text or "підключеним Telegram-акаунтом" in text:
            widget.configure(
                text=(
                    "Одна MTProto user-session використовується як технічний доступ. Редакторська оцінка береться з реакцій ВСІХ адміністраторів каналу, "
                    "яких Telegram дозволяє ідентифікувати; окремо збирається агрегована реакція аудиторії."
                )
            )
