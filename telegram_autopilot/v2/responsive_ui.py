from __future__ import annotations

import sqlite3
import statistics
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator

from .advanced_supervisor import AdvancedSupervisorService
from .feedback import analytics_configured
from .learning import audience_performance_score, audience_raw_rate
from .loghub import event
from .ui import BLOCK_UA, DECISION_UA, PROVIDER_UA, STAGE_UA, MainWindow as BaseMainWindow


class ResponsiveMainWindow(BaseMainWindow):
    """Responsive V2 UI shell with all periodic storage work outside Tk's main thread."""

    def __init__(self, store, runtime, logs_dir):
        self._rc20_closing = False
        self._rc20_runtime_action = False
        self._rc20_last_refresh: dict[str, float] = {}
        self._rc20_heartbeat_after = None
        self._rc20_data_refresh_inflight: set[str] = set()
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

    def _rc20_async_refresh(self, key: str, work: Callable[[], object], apply: Callable[[object], None]) -> None:
        """Run slow reads outside Tk and marshal only widget updates back to Tk."""
        if self._rc20_closing:
            return
        inflight = getattr(self, "_rc20_data_refresh_inflight", None)
        if inflight is None:
            inflight = set()
            self._rc20_data_refresh_inflight = inflight
        if key in inflight:
            return
        inflight.add(key)
        started = time.monotonic()

        def worker() -> None:
            result: object = None
            error: Exception | None = None
            try:
                result = work()
            except Exception as exc:
                error = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)

            def finish() -> None:
                inflight.discard(key)
                if self._rc20_closing:
                    return
                try:
                    self.runtime.ui_last_refresh_ms = elapsed_ms
                except Exception:
                    pass
                if error is not None:
                    event("ui", "background refresh failed", level=30, view=key, elapsed_ms=elapsed_ms, detail=str(error)[:1200])
                    return
                try:
                    apply(result)
                except Exception as exc:
                    event("ui", "background refresh apply failed", level=30, view=key, detail=str(exc)[:1200])

            try:
                self.after(0, finish)
            except Exception:
                inflight.discard(key)

        threading.Thread(target=worker, daemon=True, name=f"V2-UI-Refresh-{key}").start()

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
                    except Exception as exc:
                        event("ui", "refresh dispatch failed", level=30, view=key, detail=str(exc)[:1200])
                self._rc20_last_refresh[key] = now
        finally:
            self.runtime.ui_refresh_inflight = False
            if self.winfo_exists() and not self._rc20_closing:
                self._refresh_after_id = self.after(750, self.refresh_all)

    def refresh_home(self):
        def work() -> object:
            snap = self.runtime.health_snapshot()
            with self._ui_read(timeout=0.20) as con:
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
            return snap, counts, int(rejected or 0), int(waiting or 0), blocked

        def apply(result: object) -> None:
            snap, counts, rejected, waiting, blocked = result  # type: ignore[misc]
            alive = sum(1 for value in snap["channels"].values() if value["alive"])
            healthy = sum(1 for value in snap["providers"] if value["state"] == "HEALTHY")
            configured = sum(
                1 for value in snap["providers"]
                if not (value["state"] == "CONFIG_ERROR" and str(value.get("detail", "")).casefold().startswith("не налаштовано"))
            )
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
            blockers_text = ", ".join(f"{BLOCK_UA.get(blocker, blocker)}={value}" for blocker, value in blocked.items()) or "немає активних"
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

        self._rc20_async_refresh("home", work, apply)

    def refresh_channels(self):
        selected = self.channel_tree.selection()
        wanted = selected[0] if selected else ""

        def work() -> object:
            result = []
            for row in self.store.list_channels():
                channel_id = int(row["id"])
                cfg = self.store.get_channel(channel_id)
                sources = len(self.store.sources_for_channel(channel_id, enabled_only=False))
                rules = cfg.policy.selection_rules if cfg else ""
                policy = (rules[:180] + "…") if len(rules) > 180 else rules
                result.append((
                    channel_id,
                    str(row["name"]),
                    "Моніторинг" if str(row["channel_mode"]) == "monitoring" else "Редакційний",
                    "так" if row["enabled"] else "ні",
                    sources,
                    policy,
                ))
            return result

        def apply(result: object) -> None:
            rows = list(result)  # type: ignore[arg-type]
            self.channel_tree.delete(*self.channel_tree.get_children())
            for values in rows:
                self.channel_tree.insert("", "end", iid=str(values[0]), values=values)
            children = self.channel_tree.get_children()
            target = wanted if wanted in children else (children[0] if children else "")
            if target:
                self.channel_tree.selection_set(target)
                self.channel_tree.focus(target)

        self._rc20_async_refresh("channels", work, apply)

    def refresh_queue(self):
        selected = self.queue_filter.get()
        clauses = {
            "Готово": "a.stage='READY'",
            "Заблоковано AI": "a.blocked_by='AI'",
            "Заблоковано джерелом": "a.blocked_by='SOURCE'",
            "Заблоковано медіа": "a.blocked_by='MEDIA'",
            "Проблема якості": "a.blocked_by='QUALITY'",
            "Очікує": "a.decision='PENDING'",
        }

        def work() -> object:
            where = "a.stage NOT IN ('PUBLISHED','ARCHIVED') AND a.decision NOT IN ('REJECT','DUPLICATE')"
            if selected in clauses:
                where += " AND " + clauses[selected]
            with self._ui_read(timeout=0.20) as con:
                rows = con.execute(
                    f"SELECT a.*,c.name channel_name FROM articles a JOIN channels c ON c.id=a.channel_id WHERE {where} ORDER BY a.id DESC LIMIT 200"
                ).fetchall()
            return [
                (
                    int(row["id"]), str(row["channel_name"]), STAGE_UA.get(row["stage"], row["stage"]),
                    DECISION_UA.get(row["decision"], row["decision"]), BLOCK_UA.get(row["blocked_by"], row["blocked_by"]),
                    str(row["title"] or "")[:240], str(row["last_error_detail"] or row["status_detail"] or "")[:260],
                )
                for row in rows
            ]

        def apply(result: object) -> None:
            rows = list(result)  # type: ignore[arg-type]
            self.queue_tree.delete(*self.queue_tree.get_children())
            for values in rows:
                self.queue_tree.insert("", "end", iid=str(values[0]), values=values)

        self._rc20_async_refresh("queue", work, apply)

    def refresh_history(self):
        def work() -> object:
            with self._ui_read(timeout=0.20) as con:
                rows = con.execute(
                    "SELECT a.*,c.name channel_name FROM articles a JOIN channels c ON c.id=a.channel_id "
                    "WHERE a.stage='PUBLISHED' OR a.decision IN ('REJECT','DUPLICATE') ORDER BY a.id DESC LIMIT 250"
                ).fetchall()
            return [
                (
                    int(row["id"]), str(row["channel_name"]),
                    "Опубліковано" if row["stage"] == "PUBLISHED" else DECISION_UA.get(row["decision"], row["decision"]),
                    str(row["title"] or "")[:260], row["published_at"], row["canonical_source_url"],
                )
                for row in rows
            ]

        def apply(result: object) -> None:
            rows = list(result)  # type: ignore[arg-type]
            self.history_tree.delete(*self.history_tree.get_children())
            for values in rows:
                self.history_tree.insert("", "end", values=values)

        self._rc20_async_refresh("history", work, apply)

    def refresh_ai(self):
        def work() -> object:
            return [
                (
                    health.provider,
                    PROVIDER_UA.get(str(health.state), str(health.state)),
                    health.model,
                    health.success_count,
                    health.failure_count,
                    health.cooldown_until,
                    health.detail[:300],
                )
                for health in self.store.provider_health()
            ]

        def apply(result: object) -> None:
            rows = list(result)  # type: ignore[arg-type]
            self.ai_tree.delete(*self.ai_tree.get_children())
            for values in rows:
                self.ai_tree.insert("", "end", iid=str(values[0]), values=values)

        self._rc20_async_refresh("ai", work, apply)

    def refresh_learning(self):
        if not hasattr(self, "learning_tree"):
            return
        current = self.learning_channel_var.get().strip()
        feedback_ready = bool(self._feedback_ready)

        def work() -> object:
            mapping = {
                f"{int(row['id'])} · {str(row['name'])}": int(row["id"])
                for row in self.store.list_channels()
            }
            chosen = current if current in mapping else (next(iter(mapping)) if mapping else "")
            if not chosen:
                return mapping, chosen, None
            if not feedback_ready:
                return mapping, chosen, None
            cid = int(mapping[chosen])
            rows = self.feedback.feedback_rows(cid, limit=180)
            stats = self.feedback.stats(cid)
            profile = self.learning.summary(cid)
            rates = [audience_raw_rate(row) for row in rows if int(row.get("views") or 0) >= 25]
            baseline = statistics.median(rates) if rates else 0.0
            display_rows = []
            for row in rows:
                perf = audience_performance_score(row, baseline)
                audience = "—" if int(row.get("views") or 0) <= 0 else ("сильно +" if perf >= .75 else "+" if perf >= .2 else "слабо" if perf <= -.65 else "−" if perf <= -.2 else "норма")
                title = " ".join(str(row.get("title") or "").split())
                if len(title) > 95:
                    title = title[:92].rstrip() + "…"
                display_rows.append((
                    row.get("article_id"), title, str(row.get("published_at") or "")[:16].replace("T", " "),
                    int(row.get("likes") or 0), int(row.get("dislikes") or 0), int(row.get("fires") or 0),
                    audience, int(row.get("views") or 0), int(row.get("audience_total") or 0),
                    int(row.get("forwards") or 0), int(row.get("replies") or 0), self._coverage_ua(str(row.get("editor_coverage") or "")),
                ))
            configured, config_text = analytics_configured()
            return mapping, chosen, (display_rows, stats, profile, configured, config_text)

        def apply(result: object) -> None:
            mapping, chosen, payload = result  # type: ignore[misc]
            values = list(mapping)
            self.learning_channel_combo["values"] = values
            if chosen and self.learning_channel_var.get().strip() != chosen:
                self.learning_channel_var.set(chosen)
            if not chosen:
                self.learning_status.set("Немає каналів")
                return
            if payload is None:
                return
            rows, stats, profile, configured, config_text = payload
            self.learning_tree.delete(*self.learning_tree.get_children())
            for values_row in rows:
                self.learning_tree.insert("", "end", iid=str(values_row[0]), values=values_row)
            self.learning_status.set(
                f"{'✅' if configured else '⚠'} {config_text} · відстежено {int(stats.get('tracked') or 0)} · "
                f"адмін-постів {int(stats.get('editor_rated_posts') or 0)} · audience-постів {int(stats.get('audience_rated_posts') or 0)} · "
                f"👍 {int(stats.get('likes') or 0)} · 👎 {int(stats.get('dislikes') or 0)} · 🔥 {int(stats.get('fires') or 0)}"
            )
            self.learning_summary.set(
                f"Навчання тем: +{int(profile.get('topic_positive') or 0)} / −{int(profile.get('topic_negative') or 0)} прикладів · "
                f"Навчання стилю: {int(profile.get('style_examples') or 0)} 🔥-прикладів · "
                f"Audience: {int(profile.get('audience_examples') or 0)} нормалізованих прикладів · "
                f"останнє оновлення: {profile.get('last_checked') or 'ще не було'}"
            )

        self._rc20_async_refresh("learning", work, apply)

    def refresh_supervisor(self):
        if not hasattr(self, "supervisor_status"):
            return

        def work() -> object:
            return self.supervisor.summary()

        def apply(result: object) -> None:
            summary = dict(result)  # type: ignore[arg-type]
            snap = summary.get("snapshot") or {}
            incidents = summary.get("incidents") or []
            cfg = summary.get("config") or {}
            ai = snap.get("ai") or {}
            q = snap.get("queue") or {}
            incident_text = "; ".join(f"{i.get('severity')} {i.get('code')}: {i.get('title')}" for i in incidents) or "немає"
            self.supervisor_status.set(
                f"Supervisor thread: {'працює' if summary.get('thread_alive') else 'не працює'} · "
                f"AI {ai.get('healthy', 0)}/{ai.get('total', 0)} · active jobs {q.get('active', 0)} · "
                f"last publish {q.get('last_publish') or 'немає'} · incidents: {incident_text} · "
                f"mirror: {cfg.get('mirror_dir') or 'не задано'}"
            )

        self._rc20_async_refresh("supervisor", work, apply)

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
