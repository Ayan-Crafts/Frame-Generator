"""Application logging.

Logs go to a rotating file in the per-user log directory so that problems
on end-user machines (where there is no console) can be diagnosed. Uncaught
exceptions, including those raised inside Qt slots, are logged instead of
silently disappearing.
"""

from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
import threading

from app import APP_NAME, APP_VERSION
from app.utils.paths import log_dir

LOG_FILE_NAME = "tracknet-prepper.log"

_configured = False


def configure_logging(verbose: bool = False, console: bool = True) -> logging.Logger:
    global _configured
    logger = logging.getLogger("tnp")
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
    )

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir() / LOG_FILE_NAME,
            maxBytes=2 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # A read-only or full profile must never prevent the app starting.
        pass

    # Windowed (frozen) builds have no stderr at all.
    if sys.stderr is not None and (console or verbose):
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.info(
        "%s %s starting | Python %s | %s %s | frozen=%s",
        APP_NAME,
        APP_VERSION,
        platform.python_version(),
        platform.system(),
        platform.release(),
        getattr(sys, "frozen", False),
    )

    _install_excepthooks(logger)
    _configured = True
    return logger


def _install_excepthooks(logger: logging.Logger) -> None:
    previous = sys.excepthook

    def handle(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))
        if sys.stderr is not None:
            previous(exc_type, exc, tb)

    sys.excepthook = handle

    def thread_handle(args):
        logger.critical(
            "Uncaught exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = thread_handle


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"tnp.{name}")
