from __future__ import annotations

from . import ui as base_ui
from .responsive_ui import ResponsiveMainWindow
from .rc102_contract import Rc102EditorialReviewService, Rc102Supervisor as ProductionSupervisorService


class ProductionMainWindow(ResponsiveMainWindow):
    """Production UI with exactly one local-only supervisor from first paint."""

    def __init__(self, store, runtime, logs_dir):
        self._rc20_closing = False
        self._rc20_runtime_action = False
        self._rc20_last_refresh: dict[str, float] = {}
        self._rc20_heartbeat_after = None
        self._rc20_data_refresh_inflight: set[str] = set()

        original = base_ui.LocalOnlyProductionSupervisorService
        base_ui.LocalOnlyProductionSupervisorService = ProductionSupervisorService
        try:
            base_ui.MainWindow.__init__(self, store, runtime, logs_dir)
        finally:
            base_ui.LocalOnlyProductionSupervisorService = original

        self.review = Rc102EditorialReviewService(store)
        self._rc102_relabel_editorial_actions()
        self.book.bind("<<NotebookTabChanged>>", self._rc20_tab_changed, add="+")
        self._rc20_ui_heartbeat()

    def start_runtime(self):
        if not getattr(self, "_startup_ready", False):
            return super().start_runtime()
        try:
            self.supervisor.set_expected_running(True)
        except Exception:
            pass
        return super().start_runtime()

    def _rc102_relabel_editorial_actions(self) -> None:
        tab = self.tabs.get("editorial")
        if tab is None:
            return
        stack = list(tab.winfo_children())
        while stack:
            current = stack.pop()
            try:
                if current.winfo_class() == "TButton" and str(current.cget("text")) == "Погодити в READY":
                    current.configure(text="Погодити й опублікувати")
                stack.extend(current.winfo_children())
            except Exception:
                pass

    def _rc102_publish_editorial(self, article_id: int) -> None:
        try:
            self.review.approve(article_id)
        except Exception as exc:
            base_ui.messagebox.showerror("Редакторська черга", str(exc), parent=self)
            return
        self.refresh_editorial_review(); self.refresh_queue(); self.refresh_learning()
        self.status.set(f"Публікую #{article_id} після рішення редактора…")

        def work():
            try:
                result = self.runtime.publisher.publish_human_approved(article_id)
                self.review.record_publish_now(article_id, result)
                msg = f"Матеріал #{article_id}: {result}"
            except Exception as exc:
                try:
                    self.review.record_publish_now(article_id, "EXCEPTION")
                except Exception:
                    pass
                msg = f"Помилка ручної публікації #{article_id}: {exc}"
            self.after(0, lambda: (self.status.set(msg), self.refresh_editorial_review(), self.refresh_queue(), self.refresh_history(), self.refresh_learning()))

        import threading
        threading.Thread(target=work, daemon=True, name=f"V2-Editorial-Publish-{article_id}").start()

    def editorial_approve(self):
        article_id = self._selected_editorial_article()
        if article_id is not None:
            self._rc102_publish_editorial(article_id)

    def editorial_publish_now(self):
        article_id = self._selected_editorial_article()
        if article_id is not None:
            self._rc102_publish_editorial(article_id)

    def editorial_reject(self):
        article_id = self._selected_editorial_article()
        if article_id is None:
            return
        if not base_ui.messagebox.askyesno("Редакторська черга", f"Відхилити матеріал #{article_id}?", parent=self):
            return
        try:
            self.review.reject(article_id)
            try:
                self.editorial_tree.delete(str(article_id))
            except Exception:
                pass
            self.refresh_editorial_review(); self.refresh_queue(); self.refresh_history(); self.refresh_learning()
            if str(article_id) in self.editorial_tree.get_children():
                raise RuntimeError("Відхилений матеріал залишився в редакторській черзі")
        except Exception as exc:
            base_ui.messagebox.showerror("Редакторська черга", str(exc), parent=self)
