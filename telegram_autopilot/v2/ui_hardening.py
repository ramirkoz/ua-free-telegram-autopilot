from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk
import threading
import time
from typing import Callable

from .loghub import event
from .production_ui import ProductionMainWindow


class FastMainWindow(ProductionMainWindow):
    """RC51 UI hardening.

    Slow reads stay off the Tk thread.  Large Treeview refreshes are additionally
    applied in small slices, so rebuilding queue/history tables cannot monopolise
    the Windows message pump and make the window appear hung.
    """

    _TREE_VIEWS = {
        "queue": "queue_tree",
        "editorial": "editorial_tree",
        "history": "history_tree",
        "ai": "ai_tree",
    }

    def __init__(self, store, runtime, logs_dir):
        self._rc51_results: queue.Queue[tuple[str, object, Exception | None, int, int]] = queue.Queue()
        self._rc51_render_signatures: dict[str, int] = {}
        self._rc51_pump_after = None
        self._rc51_tree_generation: dict[str, int] = {}
        self._rc51_tree_after: dict[str, object] = {}
        self._rc51_tree_started: dict[str, float] = {}
        super().__init__(store, runtime, logs_dir)
        self._install_windows_editing_support()
        self._rc51_result_pump()

    def _install_windows_editing_support(self) -> None:
        """Normal Windows editing in every V2 Entry/Combobox/Text widget.

        Physical Win32 keycodes keep Ctrl+V/C/X/A working while the Ukrainian
        keyboard layout is active.  Right-click exposes a standard edit menu.
        """
        for widget_class in ("Entry", "TEntry", "TCombobox", "Text"):
            self.bind_class(widget_class, "<Control-KeyPress>", self._control_edit_shortcut, add="+")
            self.bind_class(widget_class, "<Shift-Insert>", self._paste_shortcut, add="+")
            self.bind_class(widget_class, "<Button-3>", self._show_edit_menu, add="+")

    @staticmethod
    def _edit_action(event: tk.Event) -> str:
        keysym = str(getattr(event, "keysym", "") or "").casefold()
        keycode = int(getattr(event, "keycode", 0) or 0)
        by_symbol = {"v": "paste", "c": "copy", "x": "cut", "a": "select_all"}
        return by_symbol.get(keysym) or {86: "paste", 67: "copy", 88: "cut", 65: "select_all"}.get(keycode, "")

    def _control_edit_shortcut(self, event: tk.Event):
        action = self._edit_action(event)
        if not action:
            return None
        if action == "select_all":
            self._select_all_widget(event.widget)
        elif action == "paste":
            self._paste_widget(event.widget)
        else:
            event.widget.event_generate({"copy": "<<Copy>>", "cut": "<<Cut>>"}[action])
        return "break"

    def _paste_shortcut(self, event: tk.Event):
        self._paste_widget(event.widget)
        return "break"

    def _paste_widget(self, widget: tk.Widget) -> None:
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return
        try:
            if isinstance(widget, tk.Text):
                try:
                    widget.delete("sel.first", "sel.last")
                except tk.TclError:
                    pass
                widget.insert("insert", value)
            else:
                try:
                    first = widget.index("sel.first")
                    last = widget.index("sel.last")
                    widget.delete(first, last)
                except tk.TclError:
                    pass
                widget.insert("insert", value)
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _select_all_widget(widget: tk.Widget) -> None:
        try:
            if isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "1.0")
                widget.see("insert")
            else:
                widget.selection_range(0, "end")
                widget.icursor("end")
        except tk.TclError:
            pass

    def _show_edit_menu(self, event: tk.Event):
        widget = event.widget
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Вирізати", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Копіювати", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Вставити", command=lambda: self._paste_widget(widget))
        menu.add_separator()
        menu.add_command(label="Виділити все", command=lambda: self._select_all_widget(widget))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _rc20_async_refresh(self, key: str, work: Callable[[], object], apply: Callable[[object], None]) -> None:
        if self._rc20_closing:
            return
        inflight = self._rc20_data_refresh_inflight
        if key in inflight:
            return
        inflight.add(key)
        started = time.monotonic()

        def worker() -> None:
            result: object = None
            error: Exception | None = None
            signature = 0
            try:
                result = work()
                signature = hash(repr(result))
            except Exception as exc:
                error = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            # Never call Tk from this thread.  Tkinter cross-thread calls are
            # nondeterministic on Windows and were a real production freeze source.
            self._rc51_results.put((key, (apply, result), error, elapsed_ms, signature))

        threading.Thread(target=worker, daemon=True, name=f"V2-UI-Refresh-{key}").start()

    def _rc51_result_pump(self) -> None:
        if self._rc20_closing:
            return
        # Apply only one completed view per pump.  A burst of six completed
        # refreshes used to create a long uninterrupted block of Tk work.
        try:
            key, payload, error, elapsed_ms, signature = self._rc51_results.get_nowait()
        except queue.Empty:
            key = ""
            payload = None
            error = None
            elapsed_ms = 0
            signature = 0

        if key:
            self._rc20_data_refresh_inflight.discard(key)
            try:
                self.runtime.ui_last_refresh_ms = elapsed_ms
            except Exception:
                pass
            if error is not None:
                event("ui", "background refresh failed", level=30, view=key, elapsed_ms=elapsed_ms, detail=str(error)[:1200])
            else:
                apply, result = payload  # type: ignore[misc]
                if self._rc51_render_signatures.get(key) != signature:
                    if key in self._TREE_VIEWS:
                        self._rc51_schedule_tree_render(key, result, signature)
                    else:
                        try:
                            apply(result)
                            self._rc51_render_signatures[key] = signature
                        except Exception as exc:
                            event("ui", "background refresh apply failed", level=30, view=key, detail=str(exc)[:1200])

        try:
            self._rc51_pump_after = self.after(80, self._rc51_result_pump)
        except Exception:
            self._rc51_pump_after = None

    def _rc51_schedule_tree_render(self, key: str, result: object, signature: int) -> None:
        """Render a large Treeview incrementally instead of delete/reinsert in one go."""
        attr = self._TREE_VIEWS.get(key)
        tree = getattr(self, attr, None) if attr else None
        if tree is None:
            return

        rows = list(result or [])  # type: ignore[arg-type]
        generation = int(self._rc51_tree_generation.get(key, 0)) + 1
        self._rc51_tree_generation[key] = generation
        self._rc51_tree_started[key] = time.monotonic()

        try:
            selected = tuple(tree.selection())
            existing = tuple(tree.get_children())
        except Exception as exc:
            event("ui", "tree snapshot failed", level=30, view=key, detail=str(exc)[:1200])
            return

        desired: list[tuple[str, tuple[object, ...]]] = []
        seen: set[str] = set()
        for index, values in enumerate(rows):
            values_tuple = tuple(values)
            raw_iid = values_tuple[0] if values_tuple else index
            iid = str(raw_iid)
            if not iid or iid in seen:
                iid = f"{key}-{index}-{raw_iid}"
            seen.add(iid)
            desired.append((iid, values_tuple))

        stale = [iid for iid in existing if iid not in seen]
        batch_size = 24

        def delete_batch(offset: int = 0) -> None:
            if self._rc20_closing or self._rc51_tree_generation.get(key) != generation:
                return
            end = min(len(stale), offset + batch_size)
            for iid in stale[offset:end]:
                try:
                    tree.delete(iid)
                except Exception:
                    pass
            if end < len(stale):
                self._rc51_tree_after[key] = self.after(1, lambda: delete_batch(end))
            else:
                self._rc51_tree_after[key] = self.after(1, lambda: row_batch(0))

        def row_batch(offset: int = 0) -> None:
            if self._rc20_closing or self._rc51_tree_generation.get(key) != generation:
                return
            end = min(len(desired), offset + batch_size)
            for index in range(offset, end):
                iid, values = desired[index]
                try:
                    if tree.exists(iid):
                        tree.item(iid, values=values)
                        tree.move(iid, "", index)
                    else:
                        tree.insert("", index, iid=iid, values=values)
                except Exception as exc:
                    event("ui", "tree row render failed", level=30, view=key, iid=iid, detail=str(exc)[:500])
            if end < len(desired):
                self._rc51_tree_after[key] = self.after(1, lambda: row_batch(end))
                return

            for iid in selected:
                try:
                    if tree.exists(iid):
                        tree.selection_add(iid)
                except Exception:
                    pass
            self._rc51_render_signatures[key] = signature
            elapsed_ms = int((time.monotonic() - self._rc51_tree_started.get(key, time.monotonic())) * 1000)
            try:
                self.runtime.ui_last_refresh_ms = elapsed_ms
            except Exception:
                pass
            self._rc51_tree_after.pop(key, None)
            event("ui", "tree refresh applied", view=key, rows=len(desired), elapsed_ms=elapsed_ms)

        if stale:
            delete_batch(0)
        else:
            row_batch(0)

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
        # Heavy operational tables do not need to be rebuilt every few seconds.
        # Manual actions still trigger their normal refresh immediately.
        ttl = {
            "home": 7.5,
            "channels": 30.0,
            "queue": 30.0,
            "editorial": 20.0,
            "history": 60.0,
            "ai": 30.0,
            "learning": 90.0,
            "supervisor": 10.0,
        }.get(key, 60.0)
        now = time.monotonic()
        self.runtime.ui_refresh_inflight = bool(self._rc20_data_refresh_inflight or self._rc51_tree_after)
        try:
            if now - float(self._rc20_last_refresh.get(key, 0.0)) >= ttl:
                fn = {
                    "home": self.refresh_home,
                    "channels": self.refresh_channels,
                    "queue": self.refresh_queue,
                    "editorial": self.refresh_editorial_review,
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
            try:
                if self.winfo_exists() and not self._rc20_closing:
                    self._refresh_after_id = self.after(1500, self.refresh_all)
            except Exception:
                self._refresh_after_id = None

    def _close(self):
        for after_id in tuple(self._rc51_tree_after.values()):
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._rc51_tree_after.clear()
        if self._rc51_pump_after is not None:
            try:
                self.after_cancel(self._rc51_pump_after)
            except Exception:
                pass
            self._rc51_pump_after = None
        return super()._close()
