from __future__ import annotations

import sys
import threading
import tkinter.messagebox as messagebox
from pathlib import Path

from ..instance_lock import AlreadyRunning, InstanceLock
from ..paths import data_dir
from . import V2_VERSION
from .advanced_update_coordinator import AdvancedUpdateCoordinator as UpdateCoordinator
from .bounded_ingest import BoundedStrictIngestService
from .loghub import LogHub, event
from .provider_compat import install_provider_compat
from .runtime_hardening import HardenedReadyStore as HardenedV2Store, HardenedRuntimeEngine as RuntimeEngine
from .ui_hardening import FastMainWindow as MainWindow
from .update_protocol import UpdateProtocol
from .first_run_import import maybe_import_legacy_data
from .credential_recovery import recover_missing_credentials_from_siblings
from .rc90_runtime_repair import repair_polling_baseline
from ..language_tool_local import shutdown_languagetool


def v2_database_path() -> Path:
    return data_dir() / "telegram_autopilot_v2.sqlite3"

def _manual_test_build() -> bool:
    roots = [Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[2]]
    return any((root / "MANUAL_TEST_BUILD.txt").is_file() for root in roots)

def main() -> int:
    logs = data_dir() / "logs" / "v2"
    LogHub(logs).configure()
    install_provider_compat()
    event("app", "V2 startup", database=str(v2_database_path()))
    try:
        with InstanceLock():
            import_root = None
            try:
                import tkinter as tk
                import_root = tk.Tk(); import_root.withdraw()
                maybe_import_legacy_data(import_root)
            finally:
                try:
                    if import_root is not None: import_root.destroy()
                except Exception:
                    pass
            store = HardenedV2Store(v2_database_path())
            try:
                poll_repair = repair_polling_baseline(store)
                event("app", "RC90 polling baseline repair checked", **poll_repair)
            except Exception as exc:
                event("app", "RC90 polling baseline repair failed", level=30, detail=str(exc)[:1200])
            try:
                recovery = recover_missing_credentials_from_siblings()
                event("app", "credential recovery checked", **recovery)
            except Exception as exc:
                event("app", "credential recovery failed", level=30, detail=str(exc)[:1200])
            runtime = RuntimeEngine(store)
            runtime.ingest = BoundedStrictIngestService(store)
            app = MainWindow(store, runtime, logs)
            update_coordinator = UpdateCoordinator(app, store, runtime)

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
                try:
                    UpdateProtocol().mark_startup_healthy(V2_VERSION)
                    if _manual_test_build():
                        event("update", "manual test build: auto-update disabled", version=V2_VERSION)
                    else:
                        update_coordinator.start()
                    event("update", "startup health marker written", version=V2_VERSION)
                except Exception as exc:
                    event("update", "startup health marker failed", level=30, detail=str(exc)[:1000])
                if store.list_channels(enabled_only=True):
                    app.after(250, app.start_runtime)
                else:
                    app.book.select(app.tabs["migration"])

            def begin_startup_maintenance() -> None:
                threading.Thread(target=maintenance_worker, name="V2-Startup-Maintenance", daemon=True).start()
                finish_startup_when_ready()

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
    finally:
        shutdown_languagetool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
