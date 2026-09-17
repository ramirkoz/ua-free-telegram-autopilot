from __future__ import annotations

from types import SimpleNamespace

from telegram_autopilot.v2.ui_hardening import FastMainWindow


class FakeTree:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[object, ...]] = {}
        self.order: list[str] = []

    def selection(self):
        return ()

    def selection_add(self, _iid):
        return None

    def get_children(self):
        return tuple(self.order)

    def exists(self, iid):
        return str(iid) in self.rows

    def delete(self, iid):
        iid = str(iid)
        self.rows.pop(iid, None)
        if iid in self.order:
            self.order.remove(iid)

    def item(self, iid, *, values):
        self.rows[str(iid)] = tuple(values)

    def move(self, iid, _parent, index):
        iid = str(iid)
        if iid in self.order:
            self.order.remove(iid)
        self.order.insert(index, iid)

    def insert(self, _parent, index, *, iid, values):
        iid = str(iid)
        self.rows[iid] = tuple(values)
        if iid in self.order:
            self.order.remove(iid)
        self.order.insert(index, iid)


class FakeWindow:
    _TREE_VIEWS = FastMainWindow._TREE_VIEWS
    _rc20_closing = False

    def __init__(self):
        self.queue_tree = FakeTree()
        self._rc51_tree_generation = {}
        self._rc51_tree_started = {}
        self._rc51_tree_after = {}
        self._rc51_render_signatures = {}
        self.runtime = SimpleNamespace(ui_last_refresh_ms=0)
        self.after_calls = 0

    def after(self, _delay, callback):
        self.after_calls += 1
        callback()
        return f"after-{self.after_calls}"


def test_queue_tree_render_is_sliced_and_preserves_all_rows():
    fake = FakeWindow()
    rows = [(index, "channel", "stage", "decision", "block", f"title {index}", "") for index in range(100)]

    FastMainWindow._rc51_schedule_tree_render(fake, "queue", rows, 12345)

    assert len(fake.queue_tree.rows) == 100
    assert fake.queue_tree.order[0] == "0"
    assert fake.queue_tree.order[-1] == "99"
    assert fake._rc51_render_signatures["queue"] == 12345
    # 100 rows with a batch size of 24 must yield to Tk several times.
    assert fake.after_calls >= 4


def test_tree_render_replaces_stale_rows_without_bulk_delete():
    fake = FakeWindow()
    fake.queue_tree.rows = {"old": ("old",)}
    fake.queue_tree.order = ["old"]

    FastMainWindow._rc51_schedule_tree_render(fake, "queue", [(7, "new")], 99)

    assert "old" not in fake.queue_tree.rows
    assert fake.queue_tree.rows["7"] == (7, "new")
    assert fake.queue_tree.order == ["7"]
