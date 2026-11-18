"""Subprocess helpers shared by every external-tool call.

Two cross-platform problems are handled in one place:

* Windows GUI builds have no console. Without ``CREATE_NO_WINDOW`` every
  ``nvidia-smi`` / ``ffmpeg`` call (the telemetry timer runs one per
  second) flashes a console window on screen.
* Tool output must be decoded as UTF-8 (FFmpeg prints file names verbatim)
  with replacement, otherwise a non-ASCII path in an error message raises
  ``UnicodeDecodeError`` under the Windows ANSI code page.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Sequence

NO_WINDOW_FLAGS = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
)


def popen_kwargs() -> dict:
    """Keyword arguments every ``subprocess`` call should use."""
    kwargs = {
        "encoding": "utf-8",
        "errors": "replace",
    }
    if NO_WINDOW_FLAGS:
        kwargs["creationflags"] = NO_WINDOW_FLAGS
    return kwargs


def run(
    command: Sequence[str],
    timeout: float = 10.0,
) -> subprocess.CompletedProcess | None:
    """Run a short-lived tool. Returns ``None`` if it cannot be started or times out."""
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            **popen_kwargs(),
        )
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        return None
