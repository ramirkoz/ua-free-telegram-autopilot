from __future__ import annotations

import faulthandler
import sys
import threading
import traceback
import tkinter.messagebox as messagebox
from pathlib import Path

from ..instance_lock import AlreadyRunning, InstanceLock
from ..paths import data_dir
from . import V2_VERSION
from .advanced_update_coordinator import AdvancedUpdateCoordinator as UpdateCoordinator
from .bounded_ingest import BoundedStrictIngestService
from .domain import ProviderState
from .loghub import LogHub, event
from .provider_compat import install_provider_compat
from .runtime_hardening import HardenedReadyStore as HardenedV2Store, HardenedRuntimeEngine as RuntimeEngine
from .ui_hardening import FastMainWindow
from .update_protocol import UpdateProtocol
from .update_signing import signing_key_available
from .first_run_import import maybe_import_legacy_data
from .migration_repair import repair_polling_baseline
from .commercial_profile_audit import audit_commercial_profiles
from ..language_tool_local import shutdown_languagetool


_CRASH_STREAM = None


class MainWindow(FastMainWindow):
    """Main UI with an explicit AI probe result instead of a generic completion message."""

    def test_ai(self) -> None:
        self.status_text.set("Перевіряю налаштовані AI-провайдери…")

        def work() -> None:
            try:
                results = list(self.runtime.gateway.probe_all())
                skipped = 0
                healthy = 0
                for item in results:
                    detail = str(getattr(item, "detail", "") or "").casefold()
                    state = getattr(item, "state", ProviderState.UNKNOWN)
                    if state == ProviderState.CONFIG_ERROR and (
                        "не налаштовано" in detail
                        or "secret" in detail
                        or "вимкнено" in detail
                        or "disabled" in detail
                    ):
                        skipped += 1
                    elif state == ProviderState.HEALTHY:
                        healthy += 1
                tested = max(0, len(results) - skipped)
                failed = max(0, tested - healthy)
                if tested == 0:
                    text = f"AI тест: 0 перевірено · пропущено {skipped}. Немає активних налаштованих маршрутів."
                else:
                    text = f"AI тест: перевірено {tested} · працює {healthy} · помилки {failed} · пропущено {skipped}"
                event("ai", "manual provider probe complete", tested=tested, healthy=healthy, failed=failed, skipped=skipped)
                self.after(0, lambda: self.status_text.set(text))
            except Exception as exc:
                event("ai", "manual provider probe failed", level=40, detail=str(exc)[:1200])
                msg = str(exc)
                self.after(0, lambda msg=msg: self.status_text.set(f"Тест AI: помилка: {msg}"))

        threading.Thread(target=work, name="AI-Manual-Probe", daemon=True).start()


def v2_database_path() -> Path:
    return data_dir() / "telegram_autopilot_v2.sqlite3"


def _manual_test_build() -> bool:
    roots = [Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[2]]
    return any((root / "MANUAL_TEST_BUILD.txt").is_file() for root in roots)


def _enable_crash_diagnostics(logs: Path) -> None:
    global _CRASH_STREAM
    logs.mkdir(parents=True, exist_ok=True)
    crash_path = logs / "crash.log"
    try:
        _CRASH_STREAM = crash_path.open("a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_CRASH_STREAM, all_threads=True)
    except Exception:
        _CRASH_STREAM = None

    previous_sys_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def sys_hook(exc_type, exc_value, exc_tb):
        try:
            if _CRASH_STREAM is not None:
                _CRASH_STREAM.write("\n=== UNHANDLED MAIN THREAD EXCEPTION ===\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=_CRASH_STREAM)
                _CRASH_STREAM.flush()
        finally:
            previous_sys_hook(exc_type, exc_value, exc_tb)

    def thread_hook(args):
        try:
            if _CRASH_STREAM is not None:
                _CRASH_STREAM.write(f"\n=== UNHANDLED THREAD EXCEPTION: {getattr(args.thread, 'name', 'unknown')} ===\n")
                traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=_CRASH_STREAM)
                _CRASH_STREAM.flush()
        finally:
            previous_thread_hook(args)

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook


def _run_visible_first_run_import() -> None:
    target = data_dir()
    marker = target / "first_run_import.json"
    target_db = target / "telegram_autopilot_v2.sqlite3"
    if marker.exists() or target_db.exists():
        return

    import tkinter as tk

    root = tk.Tk()
    root.title("UA FREE Telegram Autopilot V2 · запуск")
    root.geometry("620x180")
    root.resizable(False, False)
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    frame = tk.Frame(root, padx=22, pady=22)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="UA FREE Telegram Autopilot запускається", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text=(
            "Перший запуск може зайняти кілька хвилин: перевіряються попередні дані, "
            "налаштування та AI-компоненти. Не запускайте другу копію програми."
        ),
        wraplength=560,
        justify="left",
    ).pack(anchor="w", pady=(12, 8))
    tk.Label(frame, text="Очікую рішення щодо імпорту попередніх даних…", fg="#555").pack(anchor="w")

    try:
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.update_idletasks()
        root.after(1200, lambda: root.attributes("-topmost", False))
        event("app", "first-run UI visible")
        maybe_import_legacy_data(root)
        event("app", "first-run import stage complete")
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _present_main_window(app) -> None:
    try:
        app.deiconify()
        app.lift()
        app.update_idletasks()
        app.after(100, app.focus_force)
        event("app", "main window visible")
    except Exception as exc:
        event("app", "main window presentation failed", level=30, detail=str(exc)[:1000])


def main() -> int:
    logs = data_dir() / "logs" / "v2"
    LogHub(logs).configure()
    _enable_crash_diagnostics(logs)
    install_provider_compat()
    event("app", "V2 startup", database=str(v2_database_path()), version=V2_VERSION)
    try:
        with InstanceLock():
            _run_visible_first_run_import()

            store = HardenedV2Store(v2_database_path())
            try:
                poll_repair = repair_polling_baseline(store)
                event("app", "polling baseline repair checked", **poll_repair)
            except Exception as exc:
                event("app", "polling baseline repair failed", level=30, detail=str(exc)[:1200])

            runtime = RuntimeEngine(store)
            runtime.ingest = BoundedStrictIngestService(store)
            app = MainWindow(store, runtime, logs)
            _present_main_window(app)
            update_coordinator = UpdateCoordinator(app, store, runtime)

            # RC103 startup must never be gated by database housekeeping. The UI
            # and runtime become available first; feedback schema and retention are
            # best-effort background tasks and cannot veto application startup.
            app.set_startup_ready(True, "Готово · фонове обслуговування БД не блокує запуск")
            event("app", "startup stage", stage="UI_READY")

            try:
                UpdateProtocol().mark_startup_healthy(V2_VERSION)
                event("update", "startup health marker written", version=V2_VERSION)
            except Exception as exc:
                event("update", "startup health marker failed", level=30, detail=str(exc)[:1000])

            if store.list_channels(enabled_only=True):
                def start_runtime_and_mark_ready() -> None:
                    try:
                        app.start_runtime()
                        event("app", "startup stage", stage="RUNTIME_READY")
                    except Exception as exc:
                        event("app", "runtime start failed", level=40, detail=str(exc)[:1600])
                        app.set_startup_ready(False, f"Помилка запуску runtime: {exc}")
                        return
                    if _manual_test_build():
                        event("update", "manual test build: auto-update disabled", version=V2_VERSION)
                    elif signing_key_available():
                        update_coordinator.start()
                        event("update", "RC107 signed-manifest auto-update enabled", version=V2_VERSION)
                    else:
                        event(
                            "update",
                            "RC107 safety gate: auto-update disabled because no trusted Ed25519 public key is configured",
                            level=30,
                            version=V2_VERSION,
                        )
                app.after(250, start_runtime_and_mark_ready)
            else:
                app.book.select(app.tabs["migration"])
                event("app", "startup stage", stage="UI_READY_NO_CHANNELS")

            def background_startup_tasks() -> None:
                # None of these tasks is allowed to block UI/runtime readiness.
                try:
                    stats = store.run_startup_maintenance()
                    event("app", "startup maintenance scheduled", **dict(stats or {}))
                except Exception as exc:
                    event("app", "startup maintenance scheduling failed", level=30, detail=str(exc)[:1200])
                try:
                    profile_audit = audit_commercial_profiles(store)
                    event(
                        "editorial",
                        "commercial profile audit complete",
                        **{k: v for k, v in profile_audit.items() if k != "results"},
                    )
                    for item in profile_audit.get("results", []):
                        if item.get("issues") or item.get("notes"):
                            event(
                                "editorial",
                                "commercial profile audit channel",
                                level=30 if item.get("issues") else 20,
                                **item,
                            )
                except Exception as exc:
                    event("editorial", "commercial profile audit failed", level=30, detail=str(exc)[:1200])
                try:
                    feedback_stats = app.feedback.ensure_schema()
                    event("feedback", "schema ready", **dict(feedback_stats or {}))
                    try:
                        app.after(0, lambda: app.set_feedback_ready(True, "Статистика / навчання готові"))
                    except Exception:
                        pass
                except Exception as exc:
                    event("feedback", "schema failed", level=30, detail=str(exc)[:1200])
                    try:
                        msg = str(exc)
                        app.after(0, lambda msg=msg: app.set_feedback_ready(False, f"Статистика / навчання недоступні: {msg}"))
                    except Exception:
                        pass

            app.after(1000, lambda: threading.Thread(
                target=background_startup_tasks,
                name="V2-Post-Startup-Background",
                daemon=True,
            ).start())
            app.mainloop()
    except AlreadyRunning as exc:
        try:
            messagebox.showerror(
                "UA FREE Telegram Autopilot V2",
                f"{exc}\n\nЯкщо головного вікна ще не видно, перший запуск може все ще тривати. Не запускайте другу копію.",
            )
        except Exception:
            pass
        return 2
    except Exception as exc:
        event("app", "fatal startup error", level=40, detail=str(exc))
        try:
            if _CRASH_STREAM is not None:
                _CRASH_STREAM.write("\n=== FATAL STARTUP ERROR ===\n")
                traceback.print_exc(file=_CRASH_STREAM)
                _CRASH_STREAM.flush()
        except Exception:
            pass
        try:
            messagebox.showerror("UA FREE Telegram Autopilot V2", f"Помилка запуску:\n{exc}\n\nДеталі: Data\\logs\\v2\\crash.log")
        except Exception:
            pass
        return 1
    finally:
        shutdown_languagetool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
