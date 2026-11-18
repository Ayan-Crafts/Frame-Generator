"""GUI entry point.

Run with ``python -m app.main`` or ``python app/main.py`` from the
repository root, or launch the installed ``TrackNetPrepper`` executable.
"""

import argparse
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    # `python app/main.py` puts app/ (not the repo root) on sys.path, so
    # `import app` failed in v2.0 even though the README documented it.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import APP_NAME, APP_VERSION  # noqa: E402


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="TrackNetPrepper", description=APP_NAME)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument(
        "--smoke-test",
        type=float,
        metavar="SECONDS",
        help="Open the main window, wait for the capability check, then exit "
        "after SECONDS (used to verify installations). Exit code 0 = window shown.",
    )
    parser.add_argument(
        "--screenshot",
        metavar="PNG",
        help="With --smoke-test: save a screenshot of the main window before exiting.",
    )
    parser.add_argument("--verbose", action="store_true", help="Log debug output to stderr.")
    # Qt consumes its own options (e.g. -platform); ignore what we do not know.
    args, _unknown = parser.parse_known_args(argv)
    return args


def main():
    args = parse_args(sys.argv[1:])

    from app.utils.logging_setup import configure_logging

    log = configure_logging(verbose=args.verbose)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.utils.paths import resource_path

    if sys.platform == "win32":
        # Own taskbar group/icon instead of python.exe's.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "TrackNetPrepper.FrameGenerator"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("TrackNetPrepper")
    app.setDesktopFileName("tracknet-prepper")

    icon_path = resource_path("icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    log.info("Main window shown (platform plugin: %s)", app.platformName())

    if args.smoke_test is not None:
        def finish():
            report = window.capabilities
            if report is not None:
                log.info("Smoke test capability summary:")
                for line in report.summary_lines():
                    log.info("  %s", line)
            if args.screenshot:
                saved = window.grab().save(args.screenshot)
                log.info("Screenshot %s: %s", "saved" if saved else "FAILED", args.screenshot)
            log.info("Smoke test complete; closing.")
            window.close()
            app.quit()

        QTimer.singleShot(int(args.smoke_test * 1000), finish)

    code = app.exec()
    log.info("Exiting with code %s", code)
    logging.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
