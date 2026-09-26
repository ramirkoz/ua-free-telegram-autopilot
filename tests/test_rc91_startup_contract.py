from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_first_run_is_not_hidden_before_interactive_import():
    src = _read("telegram_autopilot/v2/main.py")
    assert "import_root.withdraw()" not in src
    assert "root.withdraw()" not in src
    assert "root.deiconify()" in src
    assert src.index("root.deiconify()") < src.index("maybe_import_legacy_data(root)")


def test_native_and_thread_crashes_have_persistent_log():
    src = _read("telegram_autopilot/v2/main.py")
    assert "faulthandler.enable" in src
    assert 'logs / "crash.log"' in src
    assert "threading.excepthook" in src
    assert "sys.excepthook" in src


def test_main_window_is_explicitly_presented():
    src = _read("telegram_autopilot/v2/main.py")
    assert "app.deiconify()" in src
    assert "app.lift()" in src
    assert "app.focus_force" in src
    assert 'stage="UI_READY"' in src
    assert 'stage="RUNTIME_READY"' in src


def test_updater_cannot_race_fresh_runtime_start():
    src = _read("telegram_autopilot/v2/main.py")
    assert "app.after(30000, update_coordinator.start)" in src


def test_windows_single_instance_uses_kernel_mutex_not_portable_file_lock():
    src = _read("telegram_autopilot/instance_lock.py")
    assert "CreateMutexW" in src
    assert "Local\\\\UA_FREE_Telegram_Autopilot_V2" in src
    windows_block = src[src.index('if os.name == "nt"'):src.index('self.path.parent.mkdir')]
    assert "msvcrt" not in windows_block
    assert "self.path.open" not in windows_block


def test_current_version_metadata_is_consistent():
    version = _read("VERSION.txt").strip()
    assert version == "2.0.0-rc94"
    assert _read("PUBLIC_VERSION.txt").strip() == version
    assert _read("V2_VERSION.txt").strip() == version
    assert f'__version__ = "{version}"' in _read("telegram_autopilot/__init__.py")
    assert f'V2_VERSION = "{version}"' in _read("telegram_autopilot/v2/__init__.py")
    assert 'version = "2.0.0rc94"' in _read("pyproject.toml")
