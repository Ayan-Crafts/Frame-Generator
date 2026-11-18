"""Per-user, per-platform locations for logs and settings.

Nothing here ever points inside the installation directory: installed
copies may be read-only (Program Files, /opt), and uninstalling must not
touch user data. Datasets are never written by the app except to the
output directory the user picks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app import APP_ID


def _windows_local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / "AppData" / "Local"


def user_data_dir() -> Path:
    """Directory for logs, capability cache and diagnostics."""
    override = os.environ.get("TNP_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = _windows_local_appdata() / "TrackNetPrepper"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "TrackNetPrepper"
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        path = Path(base) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def jobs_dir() -> Path:
    """Job state directory.

    Kept at ``~/.frame-generator/jobs`` for compatibility with job files
    written by v1/v2.0.
    """
    override = os.environ.get("TNP_JOBS_DIR")
    path = Path(override) if override else Path.home() / ".frame-generator" / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_base_dir() -> Path:
    """Directory that contains bundled resources.

    Frozen (PyInstaller): the directory holding bundled data (``_MEIPASS``).
    Source checkout: the repository root.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """Locate a bundled resource (icons etc.)."""
    candidates = [app_base_dir() / "app" / "resources", app_base_dir() / "resources"]
    for base in candidates:
        path = base.joinpath(*parts)
        if path.exists():
            return path
    return candidates[0].joinpath(*parts)
