from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox

from . import APP_NAME
from .database import Database
from .instance_lock import AlreadyRunning, InstanceLock
from .logging_setup import configure_logging
from .startup_recovery import recover_interrupted_work
from .ui import MainWindow
from .rc33_policy import install_rc33_policy
from .rc35_source_compat import install_rc35_source_compat
from .rc37_policy import install_rc37_policy
from .rc38_policy import install_rc38_policy
from .rc39_policy import install_rc39_policy
from .rc40_policy import install_rc40_policy
from .rc41_policy import install_rc41_policy
from .rc42_policy import install_rc42_policy
from .rc42_ui import install_rc42_ui
from .rc43_ui import install_rc43_ui
from .rc44_source_transport import install_rc44_source_transport
from .rc45_policy import install_rc45_policy
from .rc45_style import install_rc45_style
from .rc45_fact_guard import install_rc45_fact_guard
from .rc45_ui import install_rc45_ui


def main() -> int:
    logger=configure_logging()
    try:
        with InstanceLock():
            install_rc33_policy()
            install_rc35_source_compat()
            install_rc44_source_transport()
            install_rc37_policy()
            install_rc38_policy()
            install_rc39_policy()
            install_rc40_policy()
            install_rc41_policy()
            install_rc42_policy()
            install_rc45_policy()
            install_rc45_style()
            install_rc45_fact_guard()
            install_rc42_ui()
            install_rc45_ui()
            install_rc43_ui()
            db=Database(); db.quick_check(); recover_interrupted_work(db); root=tk.Tk(); app=MainWindow(root,db); root.protocol("WM_DELETE_WINDOW",app.close); root.mainloop(); return 0
    except AlreadyRunning as exc:
        try:r=tk.Tk();r.withdraw();messagebox.showwarning(APP_NAME,str(exc),parent=r);r.destroy()
        except tk.TclError:pass
        return 2
    except Exception as exc:
        logger.exception("Startup failed: %s",exc)
        try:r=tk.Tk();r.withdraw();messagebox.showerror(APP_NAME,str(exc),parent=r);r.destroy()
        except tk.TclError:pass
        return 1


if __name__ == "__main__": raise SystemExit(main())
