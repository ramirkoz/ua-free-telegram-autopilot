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
from .rc45_editorial_fit import install_rc45_editorial_fit
from .rc45_style import install_rc45_style
from .rc45_fact_guard import install_rc45_fact_guard
from .rc45_ui import install_rc45_ui
from .rc46_policy import install_rc46_policy
from .rc46_transport import install_rc46_transport
from .rc47_policy import install_rc47_policy
from .rc48_learning import install_rc48_learning
from .rc48_ui import install_rc48_ui
from .rc49_policy import install_rc49_policy
from .rc49_router import install_rc49_router
from .rc51_feedback import install_rc51_feedback
from .rc51_ui import install_rc51_ui
from .rc52_feedback import install_rc52_feedback
from .rc52_ui import install_rc52_ui


def main() -> int:
    logger=configure_logging()
    try:
        with InstanceLock():
            install_rc33_policy()
            install_rc35_source_compat()
            install_rc44_source_transport()
            install_rc46_transport()
            install_rc37_policy()
            install_rc38_policy()
            install_rc39_policy()
            install_rc40_policy()
            install_rc41_policy()
            install_rc42_policy()
            install_rc45_policy()
            install_rc45_editorial_fit()
            install_rc45_style()
            install_rc45_fact_guard()
            install_rc46_policy()
            install_rc47_policy()
            install_rc48_learning()
            install_rc49_policy()
            install_rc49_router()
            install_rc51_feedback()
            install_rc52_feedback()
            install_rc42_ui()
            install_rc45_ui()
            install_rc43_ui()
            install_rc48_ui()
            install_rc51_ui()
            install_rc52_ui()
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