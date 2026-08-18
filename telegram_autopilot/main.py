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
from .ui_direct_format import apply_direct_format_ui


def main() -> int:
    logger=configure_logging()
    try:
        with InstanceLock():
            db=Database(); db.quick_check(); recover_interrupted_work(db); root=tk.Tk(); app=MainWindow(root,db); apply_direct_format_ui(app); root.protocol("WM_DELETE_WINDOW",app.close); root.mainloop(); return 0
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