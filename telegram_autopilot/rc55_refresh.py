from __future__ import annotations

import threading
from tkinter import messagebox

from . import APP_NAME
from .rc54_mtproto import refresh_feedback_metrics_rc54

_INSTALLED = False
_INFLIGHT_ATTR = "_rc55_reaction_refresh_inflight"


def _feedback_status_var(main_window):
    return getattr(main_window, "rc51_feedback_status", None) or getattr(
        main_window, "rc48_memory_status", None
    )


def refresh_metrics_now_rc55(main_window) -> None:
    """Refresh Telegram feedback with the RC54 MTProto transport every time.

    RC51's UI imported its refresh function by value before RC54 installed its
    transport patch. The first refresh after authorization therefore used RC54,
    while later button presses could still call the stale RC51 implementation.
    Keep the UI entry point bound to the current transport and always return the
    UI from its busy state even if an unexpected exception escapes the reader.
    """
    channel_id = int(getattr(main_window, "current_channel_id", 0) or 0)
    if not channel_id:
        messagebox.showwarning(APP_NAME, "Спочатку оберіть канал.", parent=main_window.root)
        return

    channel = main_window.db.get_channel(channel_id)
    if channel is None:
        return

    status = _feedback_status_var(main_window)
    if bool(getattr(main_window, _INFLIGHT_ATTR, False)):
        if status is not None:
            status.set(f"{channel.name}: попереднє оновлення реакцій ще виконується…")
        return

    setattr(main_window, _INFLIGHT_ATTR, True)
    if status is not None:
        status.set(f"{channel.name}: читаю 👍 / 👎 / 🔥 з Telegram…")

    def worker() -> None:
        try:
            summary = refresh_feedback_metrics_rc54(main_window.db, channel, force=True)
        except Exception as exc:  # UI must never stay in an endless 'оновлюю' state.
            summary = {
                "configured": True,
                "checked": 0,
                "saved": 0,
                "error": str(exc) or exc.__class__.__name__,
                "policy_warning": "",
            }

        def finish() -> None:
            setattr(main_window, _INFLIGHT_ATTR, False)
            try:
                main_window._rc48_refresh_memory()
            except Exception:
                pass

            if summary.get("error"):
                messagebox.showwarning(
                    APP_NAME,
                    "Telegram Analytics: " + str(summary.get("error")),
                    parent=main_window.root,
                )
                return
            if not summary.get("configured"):
                messagebox.showinfo(
                    APP_NAME,
                    "Telegram Analytics ще не налаштовано.",
                    parent=main_window.root,
                )
                return

            text = (
                f"Перевірено постів: {summary.get('checked', 0)}; "
                f"оновлено реакцій: {summary.get('saved', 0)}."
            )
            if summary.get("policy_warning"):
                text += (
                    "\n\nРеакції прочитані, але Telegram не дозволив автоматично "
                    "обмежити меню до 👍 👎 🔥: " + str(summary.get("policy_warning"))
                )
            messagebox.showinfo(APP_NAME, text, parent=main_window.root)

        try:
            main_window._ui_queue.put(finish)
        except Exception:
            # Queue failure is exceptional, but do not permanently lock refresh.
            setattr(main_window, _INFLIGHT_ATTR, False)

    threading.Thread(target=worker, name="RC55Feedback", daemon=True).start()


def install_rc55_refresh() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # These module globals were imported by value in RC48/RC51 UI modules.
    # Rebinding only rc48_learning/rc51_feedback in RC54 was therefore not enough.
    from . import rc48_ui, rc51_ui
    from .ui import MainWindow

    rc48_ui.refresh_channel_metrics = refresh_feedback_metrics_rc54
    rc51_ui.refresh_feedback_metrics = refresh_feedback_metrics_rc54
    MainWindow._rc48_refresh_metrics_now = refresh_metrics_now_rc55

    _INSTALLED = True
