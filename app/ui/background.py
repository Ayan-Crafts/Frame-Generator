"""Small helpers for running blocking work off the GUI thread.

v2.0 ran ``nvidia-smi`` (1 s timeout) and a recursive scan of the whole
output tree on the GUI thread every second and on every progress update,
which froze the window on large exports.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal

from app.monitoring.system import SystemMonitor
from app.utils.logging_setup import get_logger

log = get_logger("background")


class FunctionTask(QThread):
    """Run ``fn`` once in a thread and emit its result."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.succeeded.emit(self._fn())
        except Exception as exc:
            log.exception("Background task failed")
            self.failed.emit(str(exc))


class TelemetryThread(QThread):
    """Polls GPU telemetry once per interval while the app runs."""

    sample = Signal(object)  # dict or None

    def __init__(self, interval: float = 1.5, parent=None):
        super().__init__(parent)
        self._interval = interval
        self._running = True
        self._monitor = SystemMonitor()

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                self.sample.emit(self._monitor.nvidia())
            except Exception:
                log.exception("GPU telemetry failed")
                self.sample.emit(None)
            slept = 0.0
            while self._running and slept < self._interval:
                time.sleep(0.1)
                slept += 0.1


def directory_jpeg_bytes(root: Path) -> int:
    """Total size of *.jpg files under ``root`` using fast ``os.scandir``."""
    total = 0
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.name.lower().endswith(".jpg"):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total
