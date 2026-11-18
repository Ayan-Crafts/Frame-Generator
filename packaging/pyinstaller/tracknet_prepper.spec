# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows and Linux.

Produces one folder (``dist/TrackNetPrepper``) holding two executables that
share a single bundled Python runtime and Qt:

* ``TrackNetPrepper[.exe]``       - GUI (no console window on Windows)
* ``tracknet-prepper-cli[.exe]``  - console tools (doctor / extract / convert)

Why one-folder and not one-file: no extraction to %TEMP% on every start
(much faster launch), fewer antivirus false positives, and the installer
compresses the folder anyway. UPX is off for the same AV reason and because
it corrupts some Qt DLLs.

FFmpeg is NOT added here: the build scripts copy it next to the
executables (``ffmpeg/``) so the installer can make it an optional
component and the app can prefer a system FFmpeg when that one is absent.

Build:  pyinstaller --noconfirm --clean packaging/pyinstaller/tracknet_prepper.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import APP_VERSION  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
GUI_NAME = "TrackNetPrepper" if IS_WINDOWS else "tracknet-prepper"
CLI_NAME = "tracknet-prepper-cli"
ICON = str(ROOT / "packaging" / "windows" / "app.ico") if IS_WINDOWS else None
VERSION_FILE = ROOT / "build" / "version_info.txt"

datas = [(str(ROOT / "app" / "resources"), "app/resources")]

# Not used by the application; keeps the bundle small and avoids pulling in
# large optional packages present in a developer environment.
excludes = [
    "tkinter", "numpy", "matplotlib", "scipy", "pandas", "IPython",
    "pytest", "PyInstaller", "setuptools", "pip",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
]

common = dict(
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

gui_a = Analysis([str(ROOT / "app" / "main.py")], **common)
cli_a = Analysis([str(ROOT / "app" / "cli.py")], **common)

if not IS_WINDOWS:
    # PyInstaller collects every Qt plugin. On Linux a few unused ones drag
    # in system libraries, some only partially copied from the build
    # machine (an ABI hazard on other systems):
    #   platformthemes/libqgtk3  -> GTK3, Pango, Cairo, HarfBuzz ...
    #   platforms/libqvnc, generic/libqtuiotouchplugin -> QtNetwork -> Kerberos
    # The app needs only the xcb/wayland/offscreen platforms; native file
    # dialogs still work through the xdg-desktop-portal theme (DBus).
    DROP_PATHS = (
        "plugins/platformthemes/libqgtk3",
        "plugins/platforms/libqvnc",
        "plugins/platforms/libqlinuxfb",
        "plugins/platforms/libqeglfs",
        "plugins/platforms/libqvkkhrdisplay",
        "plugins/egldeviceintegrations/",
        "plugins/generic/",
    )
    DROP_LIBS = (
        "libQt6Network", "libQt6EglFSDeviceIntegration", "libQt6EglFsKmsSupport",
        "libgtk-3", "libgdk-3", "libgdk_pixbuf", "libatk-", "libatk_bridge", "libatspi",
        "libcairo", "libpango", "libharfbuzz", "libthai", "libdatrie", "libfribidi",
        "libgraphite2", "libpixman", "libepoxy", "libgssapi_krb5", "libkrb5",
        "libk5crypto", "libkeyutils", "libjpeg.so",
    )

    def _keep(entry):
        dest = entry[0].replace("\\", "/")
        name = dest.rsplit("/", 1)[-1]
        if any(part in dest for part in DROP_PATHS):
            return False
        return not any(name.startswith(prefix) for prefix in DROP_LIBS)

    for analysis in (gui_a, cli_a):
        analysis.binaries = [entry for entry in analysis.binaries if _keep(entry)]

gui_pyz = PYZ(gui_a.pure)
cli_pyz = PYZ(cli_a.pure)

exe_common = dict(
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=str(VERSION_FILE) if IS_WINDOWS and VERSION_FILE.exists() else None,
)

gui_exe = EXE(gui_pyz, gui_a.scripts, [], name=GUI_NAME, console=False, **exe_common)
cli_exe = EXE(cli_pyz, cli_a.scripts, [], name=CLI_NAME, console=True, **exe_common)

coll = COLLECT(
    gui_exe,
    cli_exe,
    gui_a.binaries + cli_a.binaries,
    gui_a.datas + cli_a.datas,
    strip=False,
    upx=False,
    name="TrackNetPrepper",
)
