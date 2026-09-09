from __future__ import annotations

import sys
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
            if store.list_channels(enabled_only=True):
                app.after(700, app.start_runtime)
            else:
                app.after(700, lambda: app.book.select(app.tabs["migration"]))
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
