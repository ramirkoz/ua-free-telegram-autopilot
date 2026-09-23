from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(sys.executable).resolve().parent
_RUNTIME = _ROOT / "_runtime"
os.environ.setdefault("UA_FREE_TELEGRAM_AUTOPILOT_ROOT", str(_ROOT))
os.environ.setdefault("PYTHONNOUSERSITE", "1")
# Keep Tk fully portable even though Tcl/Tk lives under _runtime.
os.environ.setdefault("TCL_LIBRARY", str(_RUNTIME / "tcl" / "tcl8.6"))
os.environ.setdefault("TK_LIBRARY", str(_RUNTIME / "tcl" / "tk8.6"))

# Child Python invocations (pip/Codex maintenance) must never recursively start the GUI.
if (
    Path(sys.executable).name.casefold() == "ua_free_telegram_autopilot.exe"
    and os.environ.get("UA_FREE_CHILD_PROCESS") != "1"
    and len(sys.argv) == 1
):
    from telegram_autopilot.v2.main import main
    raise SystemExit(main())
