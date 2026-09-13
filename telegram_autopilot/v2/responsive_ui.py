from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .advanced_supervisor import AdvancedSupervisorService
from .ui import BLOCK_UA, DECISION_UA, STAGE_UA, MainWindow as BaseMainWindow


class ResponsiveMainWindow(BaseMainWindow):
    """RC21 UI shell that keeps database work away from Tk's critical path."""

    def __init__(self, store, runtime, logs_dir):
        self._rc20_closing = False
        self._rc20_runtime_action = False
        self._rc20_last_refresh: dict[str, float] = {}
        self._rc20_heartbeat_after = None
        super().__init__(store, runtime, logs_dir)

        # Replace the RC19 supervisor after the base widgets exist. The config and
        # paths live in Data, so this is transparent to the existing Nагляд tab.
        try:
            self.supervisor.stop()
        except Exception:
            pass
        self.supervisor = AdvancedSupervisorService(store, runtime, logs_dir)
        self.supervisor.start()
        self.book.bind("<<NotebookTabChanged>>", self._rc20_tab_changed, add="+")
        self._rc20_ui_heartbeat()

    @contextmanager
    def _ui_read(self, timeout: float = 0.35) -> Iterator[sqlite3.Connection]:
        seconds = max(0.05, min(2.0, float(timeout)))
        con = sqlite3.connect(self.store.path, timeout=seconds, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute(f"PRAGMA busy_timeout={int(seconds * 1000)}")
        con.execute("PRAGMA query_only=ON")
        try:
            yield con
        finally:
            con.close()

    def _active_tab_key(self) -> str:
        try:
            selected = str(self.book.select())
            for key, frame in self.tabs.items():
                if str(frame) == selected:
                    return key
        except Exception:
            pass
        return "home"

    def _rc20_tab_changed(self, _event=None) -> None:
        self._rc20_last_refresh.pop(self._active_tab_key(), None)
        try:
            self.after_idle(self.refresh_all)
        except Exception:
            pass

    def _rc20_ui_heartbeat(self) -> None:
        if self._rc20_closing:
            return
        self.runtime.ui_heartbeat_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        try:
            self._rc20_heartbeat_after = self.after(500, self._rc20_ui_heartbeat)
        except Exception:
            self._rc20_heartbeat_after = None

    def refresh_all(self):
        if self._rc20_closing:
            return
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None

        key = self._active_tab_key()
        ttl = {
            "home": 2.5, "channels": 8.0, "queue": 6.0, "history": 10.0,
            "ai": 8.0, "learning": 30.0, "supervisor": 2.5,
        }.get(key, 30.0)
        now = time.monotonic()
        started = time.monotonic()
        self.runtime.ui_refresh_inflight = True
        try:
            if now - float(self._rc20_last_refresh.get(key, 0.0)) >= ttl:
                fn = {
                    "home": self.refresh_home,
                    "channels": self.refresh_channels,
                    "queue": self.refresh_queue,
                    "history": self.refresh_history,
                    "ai": self.refresh_ai,
                    "learning": self.refresh_learning,
                    "supervisor": self.refresh_supervisor,
                }.get(key)
                if fn is not None:
                    try:
                        fn()
                    except sqlite3.OperationalError:
                        # A writer owns SQLite for a moment. Skip this paint instead
                        # of blocking Tk for the normal 30-second storage timeout.
                        pass
                    except Exception:
                        # UI telemetry will expose repeated stalls; one failed paint
                        # must never take down the runtime.
                        pass
                self._rc20_last_refresh[key] = now
        finally:
            self.runtime.ui_refresh_inflight = False
            self.runtime.ui_last_refresh_ms = int((time.monotonic() - started) * 1000)
            if self.winfo_exists() and not self._rc20_closing:
                self._refresh_after_id = self.after(750, self.refresh_all)

    def refresh_home(self):
        snap = self.runtime.health_snapshot()
        alive = sum(1 for value in snap["channels"].values() if value["alive"])
        healthy = sum(1 for value in snap["providers"] if value["state"] == "HEALTHY")
        configured = sum(
            1 for value in snap["providers"]
            if not (value["state"] == "CONFIG_ERROR" and str(value.get("detail", "")).casefold().startswith("не налаштовано"))
        )
        with self._ui_read() as con:
            counts = {row[0]: row[1] for row in con.execute("SELECT stage,COUNT(*) FROM articles GROUP BY stage")}
            rejected = con.execute("SELECT COUNT(*) FROM articles WHERE decision='REJECT'").fetchone()[0]
            waiting = con.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','WAITING','LEASED')").fetchone()[0]
            blocked = {
                row[0]: row[1]
                for row in con.execute(
                    """SELECT a.blocked_by,COUNT(DISTINCT j.article_id)
                       FROM jobs j JOIN articles a ON a.id=j.article_id
                       WHERE j.state IN ('QUEUED','WAITING','LEASED')
                         AND a.blocked_by IS NOT NULL AND a.blocked_by<>'NONE'
                       GROUP BY a.blocked_by"""
                )
            }
        ai_blocked = int(blocked.get("AI", 0) or 0)
        if self._running:
            if healthy == 0 and ai_blocked:
                self.status.set("Автопілот: AI пауза, workers активні")
            elif alive == 0:
                self.status.set("Автопілот: workers не працюють")
            else:
                self.status.set("Автопілот працює")
        provider_total = len(snap["providers"])
        configured_text = f"{configured} налаштовано" if provider_total else "стан ще не перевірено"
        blockers_text = ", ".join(f"{BLOCK_UA.get(key, key)}={value}" for key, value in blocked.items()) or "немає активних"
        text = (
            "UA FREE Telegram Autopilot V2\n\n"
            f"Канали: {alive}/{len(snap['channels'])} workers активні\n"
            f"AI: {healthy}/{provider_total} healthy · {configured_text}\n"
            f"Черга: {waiting}\nОпубліковано: {counts.get('PUBLISHED', 0)}\n"
            f"Готово: {counts.get('READY', 0)}\nВідхилено: {rejected}\n\n"
            f"Активні блокери: {blockers_text}"
        )
        self.home_text.configure(state="normal")
        self.home_text.delete("1.0", "end")
        self.home_text.insert("1.0", text)
        self.home_text.configure(state="disabled")

    def refresh_queue(self):
        where = "a.stage NOT IN ('PUBLISHED','ARCHIVED') AND a.decision NOT IN ('REJECT','DUPLICATE')"
        selected = self.queue_filter.get()
        clauses = {
            "Готово": "a.stage='READY'",
            "Заблоковано AI": "a.blocked_by='AI'",
            "Заблоковано джерелом": "a.blocked_by='SOURCE'",
            "Заблоковано медіа": "a.blocked_by='MEDIA'",
            "Проблема якості": "a.blocked_by='QUALITY'",
            "Очікує": "a.decision='PENDING'",
        }
        if selected in clauses:
            where += " AND " + clauses[selected]
        with self._ui_read() as con:
            rows = con.execute(
                f"SELECT a.*,c.name channel_name FROM articles a JOIN channels c ON c.id=a.channel_id WHERE {where} ORDER BY a.id DESC LIMIT 200"
            ).fetchall()
        self.queue_tree.delete(*self.queue_tree.get_children())
        for row in rows:
            self.queue_tree.insert("", "end", iid=str(row["id"]), values=(
                row["id"], row["channel_name"], STAGE_UA.get(row["stage"], row["stage"]),
                DECISION_UA.get(row["decision"], row["decision"]), BLOCK_UA.get(row["blocked_by"], row["blocked_by"]),
                str(row["title"] or "")[:240], str(row["last_error_detail"] or row["status_detail"] or "")[:260],
            ))

    def refresh_history(self):
        with self._ui_read() as con:
            rows = con.execute(
                "SELECT a.*,c.name channel_name FROM articles a JOIN channels c ON c.id=a.channel_id "
                "WHERE a.stage='PUBLISHED' OR a.decision IN ('REJECT','DUPLICATE') ORDER BY a.id DESC LIMIT 250"
            ).fetchall()
        self.history_tree.delete(*self.history_tree.get_children())
        for row in rows:
            status = "Опубліковано" if row["stage"] == "PUBLISHED" else DECISION_UA.get(row["decision"], row["decision"])
            self.history_tree.insert("", "end", values=(
                row["id"], row["channel_name"], status, str(row["title"] or "")[:260], row["published_at"], row["canonical_source_url"],
            ))

    def start_runtime(self):
        if not self._startup_ready:
            self.status.set("Підготовка бази ще триває…")
            return
        if self._running or self._rc20_runtime_action:
            return
        self._rc20_runtime_action = True
        self.status.set("Автопілот запускається…")
        self.start_button.configure(state="disabled")

        def work() -> None:
            error = None
            try:
                self.runtime.start()
            except Exception as exc:
                error = exc
            def done() -> None:
                self._rc20_runtime_action = False
                if error is None:
                    self._running = True
                    self.supervisor.set_expected_running(True)
                    self.status.set("Автопілот працює")
                else:
                    self.status.set(f"Помилка запуску: {error}")
                    self.start_button.configure(state="normal")
                self._rc20_last_refresh.clear()
            try:
                self.after(0, done)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True, name="V2-Runtime-Start").start()

    def stop_runtime(self):
        if not self._running or self._rc20_runtime_action:
            return
        self._rc20_runtime_action = True
        self.supervisor.set_expected_running(False)
        self.status.set("Автопілот зупиняється…")

        def work() -> None:
            error = None
            try:
                self.runtime.stop(timeout=30.0)
            except Exception as exc:
                error = exc
            def done() -> None:
                self._rc20_runtime_action = False
                self._running = False
                self.status.set("Автопілот зупинено" if error is None else f"Зупинка з помилкою: {error}")
                self.start_button.configure(state=("normal" if self._startup_ready else "disabled"))
                self._rc20_last_refresh.clear()
            try:
                self.after(0, done)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True, name="V2-Runtime-Stop").start()

    def _close(self):
        if self._rc20_closing:
            return
        self._rc20_closing = True
        try:
            self.supervisor.set_expected_running(False)
        except Exception:
            pass
        self.status.set("Завершую роботу…")
        for after_id in (self._refresh_after_id, self._rc20_heartbeat_after):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        try:
            self.feedback_runtime.stop()
        except Exception:
            pass

        def work() -> None:
            try:
                self.runtime.stop(timeout=20.0)
            except Exception:
                pass
            try:
                self.supervisor.stop()
            except Exception:
                pass
            try:
                self.after(0, self.destroy)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True, name="V2-App-Close").start()
