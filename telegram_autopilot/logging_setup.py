from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir


def configure_logging() -> logging.Logger:
    logger=logging.getLogger("telegram_autopilot")
    if logger.handlers: return logger
    logger.setLevel(logging.INFO)
    handler=RotatingFileHandler(logs_dir()/"telegram_autopilot.log",maxBytes=4*1024*1024,backupCount=4,encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    logger.addHandler(handler)
    return logger
