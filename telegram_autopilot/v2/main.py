from __future__ import annotations

import sys
import threading
import tkinter.messagebox as messagebox
from pathlib import Path

from ..instance_lock import AlreadyRunning, InstanceLock
from ..paths import data_dir
from .loghub import LogHub, event
from .runtime import RuntimeEngine
from .storage import V2Store
from .ui import MainWindow


def v2_database_path() -> Path:
    return data_dir() / "telegram_autopilot_v2.sqlite3"


def main() -> int:
    logs = data_dir() / "logs" / "v2"
    LogHub(logs).configure()
    event("app", "V2 startup", database=str(v2_database_path()))
    try:
        with InstanceLock():
            store = V2Store(v2_database_path())
            runtime = RuntimeEngine(store)
            app = MainWindow(store, runtime, logs)

            # RC9: never run one-time DB maintenance on the Tk thread. RC8 did so from
            # V2Store.__init__, before the window was drawn, which made a migrated DB look hung.
            maintenance_done = threading.Event()
            maintenance_result: dict[str, object] = {}
            app.set_startup_ready(False, "Підготовка бази… інтерфейс залишається активним")

            def maintenance_worker() -> None:
                try:
                    maintenance_result["stats"] = store.run_startup_maintenance()
                    event("app", "startup maintenance complete", **dict(maintenance_result["stats"]))
                except Exception as exc:
                    maintenance_result["error"] = exc
                    event("app", "startup maintenance failed", level=40, detail=str(exc)[:1600])
                # Optional feedback/learning schema is deliberately isolated: analytics must never
                # prevent the core autopilot from starting.
                try:
                    maintenance_result["feedback_stats"] = app.feedback.ensure_schema()
                    event("feedback", "schema ready", **dict(maintenance_result["feedback_stats"]))
                except Exception as exc:
                    maintenance_result["feedback_error"] = exc
                    event("feedback", "schema failed", level=30, detail=str(exc)[:1200])
                finally:
                    maintenance_done.set()

            def finish_startup_when_ready() -> None:
                if not maintenance_done.is_set():
                    if app.winfo_exists():
                        app.after(200, finish_startup_when_ready)
                    return
                error = maintenance_result.get("error")
                if error is not None:
                    app.set_startup_ready(False, "Помилка підготовки бази. Runtime не запущено")
                    try:
                        messagebox.showerror("UA FREE Telegram Autopilot V2", f"Помилка підготовки бази:\n{error}")
                    except Exception:
                        pass
                    return
                stats = maintenance_result.get("stats") or {}
                feedback_error = maintenance_result.get("feedback_error")
                if feedback_error is None:
                    app.set_feedback_ready(True, "Статистика / навчання готові")
                else:
                    app.set_feedback_ready(False, f"Статистика / навчання недоступні: {feedback_error}")
                app.set_startup_ready(True, f"Підготовка бази завершена: URL={stats.get('normalized_urls', 0)}, дублікати={stats.get('reconciled_duplicates', 0)}")
                if store.list_channels(enabled_only=True):
                    app.after(250, app.start_runtime)
                else:
                    app.book.select(app.tabs["migration"])

            def begin_startup_maintenance() -> None:
                threading.Thread(target=maintenance_worker, name="V2-Startup-Maintenance", daemon=True).start()
                finish_startup_when_ready()

            # Give Tk time to paint the window before any maintenance work starts.
            app.after(150, begin_startup_maintenance)
            app.mainloop()
    except AlreadyRunning as exc:
        try:
            messagebox.showerror("UA FREE Telegram Autopilot V2", str(exc))
        except Exception:
            pass
        return 2
    except Exception as exc:
        event("app", "fatal startup error", level=40, detail=str(exc))
        try:
            messagebox.showerror("UA FREE Telegram Autopilot V2", f"Помилка запуску:\n{exc}")
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
