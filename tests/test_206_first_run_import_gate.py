from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from telegram_autopilot.v2 import first_run_import as importer
from telegram_autopilot.v2 import main as startup


def test_empty_db_and_failed_marker_allow_retry(tmp_path, monkeypatch):
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE channels(id INTEGER)")
    (tmp_path / "first_run_import.json").write_text(json.dumps({"imported": False}))
    monkeypatch.setattr(importer, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(importer.messagebox, "askyesno", lambda *a, **k: False)
    result = importer.maybe_import_legacy_data(None)
    assert result["reason"] == "skipped"


def test_existing_channels_skip_first_run_dialog(tmp_path, monkeypatch):
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE channels(id INTEGER)")
        con.execute("INSERT INTO channels VALUES (1)")
    monkeypatch.setattr(importer, "data_dir", lambda: tmp_path)
    result = importer.maybe_import_legacy_data(None)
    assert result["imported"] is True
    assert result["channels"] == 1


def test_failed_import_never_unlinks_existing_database(tmp_path, monkeypatch):
    db = tmp_path / "telegram_autopilot_v2.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE channels(id INTEGER)")
    monkeypatch.setattr(importer, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(importer.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(importer.filedialog, "askdirectory", lambda **kw: str(tmp_path / "missing"))
    monkeypatch.setattr(importer.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(importer.tk, "Toplevel", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no display")))
    result = importer.maybe_import_legacy_data(None)
    assert result["imported"] is False
    assert db.exists()
