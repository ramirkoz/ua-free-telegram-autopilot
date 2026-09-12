from __future__ import annotations

import json
import logging
import logging.handlers
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOG_NAMES = (
    "app", "ingest", "ai", "editorial", "worker", "publish",
    "migration", "supervisor", "feedback", "learning", "media",
)


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context = getattr(record, "context", None)
        if isinstance(context, dict) and context:
            clean = {k: v for k, v in context.items() if v not in (None, "")}
            if clean:
                return base + " " + json.dumps(clean, ensure_ascii=False, separators=(",", ":"), default=str)
        return base


class ErrorOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.ERROR


@dataclass(slots=True)
class LogHub:
    root: Path
    max_bytes: int = 10 * 1024 * 1024
    backups: int = 5

    def configure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        formatter = ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        for name in LOG_NAMES:
            logger = logging.getLogger(f"telegram_autopilot.v2.{name}")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            self._replace_handlers(logger, self.root / f"{name}.log", formatter)

        errors = logging.getLogger("telegram_autopilot.v2.errors")
        errors.setLevel(logging.ERROR)
        errors.propagate = False
        self._replace_handlers(errors, self.root / "error.log", formatter, error_only=True)

    def _replace_handlers(self, logger: logging.Logger, path: Path, formatter: logging.Formatter, *, error_only: bool = False) -> None:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=self.max_bytes, backupCount=self.backups, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        if error_only:
            handler.addFilter(ErrorOnlyFilter())
        logger.addHandler(handler)


def logger(name: str) -> logging.Logger:
    """Return a module logger without allowing telemetry to break the module itself.

    Registered module streams get their own rotating file. If a future module emits
    an event before its stream is registered, fall back to the app stream instead of
    raising inside production code. The original stream is preserved by ``event``.
    """
    clean = str(name or "app").strip() or "app"
    if clean not in LOG_NAMES:
        return logging.getLogger("telegram_autopilot.v2.app")
    return logging.getLogger(f"telegram_autopilot.v2.{clean}")


def event(name: str, message: str, *, level: int = logging.INFO, **context: Any) -> None:
    clean = str(name or "app").strip() or "app"
    if clean not in LOG_NAMES:
        context = {"original_stream": clean, **context}
    logger(clean).log(level, message, extra={"context": context})
    if level >= logging.ERROR:
        logging.getLogger("telegram_autopilot.v2.errors").log(level, message, extra={"context": context})
