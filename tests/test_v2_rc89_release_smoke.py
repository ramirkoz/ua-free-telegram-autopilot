from __future__ import annotations

import json
from pathlib import Path

from telegram_autopilot.v2 import first_run_import


def test_noninteractive_first_run_skips_dialog_and_writes_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(first_run_import, "data_dir", lambda: tmp_path)
    monkeypatch.setenv("UA_FREE_AUTOPILOT_SKIP_FIRST_RUN_IMPORT", "1")

    def boom(*args, **kwargs):
        raise AssertionError("interactive dialog must not open in noninteractive first run")

    monkeypatch.setattr(first_run_import.messagebox, "askyesno", boom)
    result = first_run_import.maybe_import_legacy_data(root=object())

    assert result == {"imported": False, "reason": "noninteractive_first_run"}
    marker = tmp_path / "first_run_import.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["skipped"] is True
    assert payload["reason"] == "noninteractive_first_run"
