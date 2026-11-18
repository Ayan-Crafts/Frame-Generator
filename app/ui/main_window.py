import os
import shutil
from pathlib import Path
import time

import psutil

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QTabWidget,
    QMainWindow,
    QLabel,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QWidget,
    QMessageBox,
    QFrame,
    QProgressBar,
    QSizePolicy,
    QComboBox,
    QPlainTextEdit,
    QDialog,
    QDialogButtonBox,
    QApplication,
    QScrollArea,
)

from app import APP_NAME, APP_VERSION
from app.hardware.capabilities import PIPELINE_CPU, PIPELINE_GPU, get_report
from app.hardware.detector import HardwareDetector
from app.processing.exporter import VideoExporter, VideoProbeError
from app.processing.scanner import DatasetScanner, VIDEO_EXTENSIONS, output_names
from app.processing.worker import ExportWorker
from app.jobs.job_manager import JobManager
from app.utils.logging_setup import get_logger
from app.utils.paths import log_dir

from app.ui.annotation_tab import AnnotationTab
from app.ui.background import FunctionTask, TelemetryThread, directory_jpeg_bytes

log = get_logger("ui")

ACCELERATION_MODES = [
    ("AUTO (GPU if verified)", "auto"),
    ("GPU (NVDEC) only", "gpu"),
    ("CPU only", "cpu"),
]


class StatCard(QFrame):

    def __init__(
        self,
        title,
        value="--",
        subtitle="",
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("statCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            16,
            12,
            16,
            12,
        )

        self.title_label = QLabel(title)
        self.title_label.setObjectName(
            "statTitle"
        )

        self.value_label = QLabel(value)
        self.value_label.setObjectName(
            "statValue"
        )

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName(
            "statSubtitle"
        )

        layout.addWidget(
            self.title_label
        )

        layout.addWidget(
            self.value_label
        )

        layout.addWidget(
            self.subtitle_label
        )

    def set_value(self, value):
        self.value_label.setText(
            str(value)
        )

    def set_subtitle(self, text):
        self.subtitle_label.setText(
            str(text)
        )


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            f"{APP_NAME} {APP_VERSION} — Frame Generator"
        )

        # Use a percentage of the available screen instead of a fixed
        # window size so the dashboard scales well on laptops and 27"+ monitors.
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            initial_width = min(1920, max(1200, int(available.width() * 0.82)))
            initial_height = min(1200, max(760, int(available.height() * 0.82)))
        else:
            initial_width = 1500
            initial_height = 900

        self.setMinimumSize(1050, 700)
        self.resize(initial_width, initial_height)

        # ==================================================
        # STATE
        # ==================================================

        self.input_directory = ""
        self.output_directory = ""

        # Presence only. Whether the pipeline can actually use the GPU is
        # decided by the capability report, probed in the background.
        self.hardware = (
            HardwareDetector().detect()
        )
        self.capabilities = None
        self._capability_task = None
        self._frame_count_task = None
        self._output_size_task = None
        self._finished_workers = []
        self.failed_videos = {}
        self.current_pipeline = None
        self._job_ended = True

        self.worker = None
        self.dataset_info = None

        self.job_manager = JobManager()
        self.job_id = None

        self.export_start_time = None

        self.current_video_total_frames = 0
        self.current_video_frames = 0

        self.total_processed_videos = 0
        self.total_output_bytes = 0

        self.total_dataset_frames = 0

        self.current_video_name = "--"

        # ==================================================
        # MAIN STYLE
        # ==================================================

        self.setStyleSheet(
            """
            QMainWindow {
                background: #0f172a;
                color: #e5e7eb;
            }

            QWidget {
                font-family: Segoe UI;
                font-size: 10pt;
            }

            QLabel {
                color: #e5e7eb;
            }

            QFrame#section {
                background: #111827;
                border: 1px solid #263244;
                border-radius: 10px;
            }

            QFrame#statCard {
                background: #111827;
                border: 1px solid #263244;
                border-radius: 10px;
                min-height: 95px;
            }

            QLabel#statTitle {
                color: #94a3b8;
                font-size: 9pt;
                font-weight: 600;
            }

            QLabel#statValue {
                color: #f8fafc;
                font-size: 22pt;
                font-weight: 700;
            }

            QLabel#statSubtitle {
                color: #64748b;
                font-size: 8pt;
            }

            QLabel#sectionTitle {
                color: #f8fafc;
                font-size: 11pt;
                font-weight: 700;
            }

            QLabel#pathLabel {
                background: #0b1220;
                border: 1px solid #263244;
                border-radius: 7px;
                padding: 10px;
                color: #cbd5e1;
            }

            QLabel#currentVideo {
                color: #f8fafc;
                font-size: 13pt;
                font-weight: 600;
            }

            QProgressBar {
                background: #0b1220;
                border: 1px solid #263244;
                border-radius: 6px;
                height: 18px;
                text-align: center;
                color: #e5e7eb;
            }

            QProgressBar::chunk {
                background: #22c55e;
                border-radius: 5px;
            }

            QPushButton {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 10px 16px;
                color: #f8fafc;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #273449;
            }

            QPushButton:disabled {
                background: #111827;
                color: #475569;
                border-color: #1e293b;
            }

            QPushButton#startButton {
                background: #16a34a;
                border: none;
                min-height: 42px;
                font-size: 11pt;
            }

            QPushButton#startButton:hover {
                background: #15803d;
            }

            QPushButton#cancelButton {
                background: #991b1b;
                border: none;
                min-height: 42px;
                font-size: 11pt;
            }

            QPushButton#cancelButton:hover {
                background: #b91c1c;
            }

            QLabel#hardwareHeader {
                color: #22c55e;
                font-size: 10pt;
                font-weight: 700;
            }
            """
        )

        # ==================================================
        # CENTRAL WIDGET
        # ==================================================

        central = QWidget()

        main_layout = QVBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            24,
            20,
            24,
            20,
        )

        main_layout.setSpacing(
            14
        )

        # ==================================================
        # HEADER
        # ==================================================

        header_layout = QHBoxLayout()

        title = QLabel(
            "FRAME GENERATOR"
        )

        title.setStyleSheet(
            """
            font-size: 20pt;
            font-weight: 800;
            color: #f8fafc;
            """
        )

        self.hardware_header = QLabel(
            self.hardware_header_text()
        )

        self.hardware_header.setObjectName(
            "hardwareHeader"
        )

        header_layout.addWidget(
            title
        )

        header_layout.addStretch()

        header_layout.addWidget(
            self.hardware_header
        )

        self.system_check_button = QPushButton("SYSTEM CHECK")
        self.system_check_button.setToolTip(
            "Show detected FFmpeg, NVIDIA GPU, driver and verified acceleration."
        )
        self.system_check_button.clicked.connect(self.show_system_check)
        header_layout.addWidget(self.system_check_button)

        logs_button = QPushButton("LOGS")
        logs_button.setToolTip(f"Open the log folder:\n{log_dir()}")
        logs_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))
        )
        header_layout.addWidget(logs_button)

        main_layout.addLayout(
            header_layout
        )

        # ==================================================
        # DIRECTORIES
        # ==================================================

        directory_section = QFrame()

        directory_section.setObjectName(
            "section"
        )

        directory_layout = QVBoxLayout(
            directory_section
        )

        directory_layout.setContentsMargins(
            16,
            14,
            16,
            14,
        )

        input_title = QLabel(
            "INPUT DIRECTORY"
        )

        input_title.setObjectName(
            "sectionTitle"
        )

        self.input_label = QLabel(
            "Not selected"
        )

        self.input_label.setObjectName(
            "pathLabel"
        )

        input_row = QHBoxLayout()

        input_row.addWidget(
            self.input_label,
            1,
        )

        input_button = QPushButton(
            "SELECT INPUT"
        )

        input_button.clicked.connect(
            self.select_input
        )

        input_row.addWidget(
            input_button
        )

        output_title = QLabel(
            "OUTPUT DIRECTORY"
        )

        output_title.setObjectName(
            "sectionTitle"
        )

        self.output_label = QLabel(
            "Not selected"
        )

        self.output_label.setObjectName(
            "pathLabel"
        )

        output_row = QHBoxLayout()

        output_row.addWidget(
            self.output_label,
            1,
        )

        output_button = QPushButton(
            "SELECT OUTPUT"
        )

        output_button.clicked.connect(
            self.select_output
        )

        output_row.addWidget(
            output_button
        )

        directory_layout.addWidget(
            input_title
        )

        directory_layout.addLayout(
            input_row
        )

        directory_layout.addSpacing(
            8
        )

        directory_layout.addWidget(
            output_title
        )

        directory_layout.addLayout(
            output_row
        )

        main_layout.addWidget(
            directory_section
        )

        # ==================================================
        # DATASET STATISTICS
        # ==================================================

        stats_grid = QGridLayout()

        stats_grid.setSpacing(
            10
        )

        self.videos_card = StatCard(
            "VIDEOS",
            "0",
            "videos detected",
        )

        self.input_size_card = StatCard(
            "INPUT SIZE",
            "0 GB",
            "total dataset size",
        )

        self.frames_card = StatCard(
            "TOTAL FRAMES",
            "0",
            "estimated frames",
        )

        self.output_size_card = StatCard(
            "OUTPUT SIZE",
            "0 GB",
            "frames generated",
        )

        self.processed_card = StatCard(
            "PROCESSED",
            "0 / 0",
            "videos completed",
        )

        self.progress_card = StatCard(
            "PROGRESS",
            "0%",
            "overall export",
        )

        self.speed_card = StatCard(
            "SPEED",
            "0x",
            "FFmpeg processing speed",
        )

        self.eta_card = StatCard(
            "ETA",
            "--",
            "estimated time remaining",
        )

        cards = [
            self.videos_card,
            self.input_size_card,
            self.frames_card,
            self.output_size_card,
            self.processed_card,
            self.progress_card,
            self.speed_card,
            self.eta_card,
        ]

        for index, card in enumerate(
            cards
        ):

            row = index // 4
            column = index % 4

            stats_grid.addWidget(
                card,
                row,
                column,
            )

        main_layout.addLayout(
            stats_grid
        )

        # ==================================================
        # CURRENT VIDEO
        # ==================================================

        current_section = QFrame()

        current_section.setObjectName(
            "section"
        )

        current_layout = QVBoxLayout(
            current_section
        )

        current_layout.setContentsMargins(
            16,
            14,
            16,
            14,
        )

        current_title = QLabel(
            "CURRENT VIDEO"
        )

        current_title.setObjectName(
            "sectionTitle"
        )

        self.current_video_label = QLabel(
            "--"
        )

        self.current_video_label.setObjectName(
            "currentVideo"
        )

        self.current_frame_label = QLabel(
            "Frame 0 / 0"
        )

        self.pipeline_label = QLabel(
            "Pipeline: --"
        )
        self.pipeline_label.setObjectName(
            "statSubtitle"
        )
        self.pipeline_label.setToolTip(
            "Which stages run on the GPU and which on the CPU for the current video."
        )

        self.current_progress = (
            QProgressBar()
        )

        self.current_progress.setRange(
            0,
            100,
        )

        self.current_progress.setValue(
            0
        )

        current_layout.addWidget(
            current_title
        )

        current_layout.addWidget(
            self.current_video_label
        )

        current_layout.addWidget(
            self.current_frame_label
        )

        current_layout.addWidget(
            self.pipeline_label
        )

        current_layout.addWidget(
            self.current_progress
        )

        main_layout.addWidget(
            current_section
        )

        # ==================================================
        # HARDWARE / SYSTEM STATISTICS
        # ==================================================

        hardware_grid = QGridLayout()

        hardware_grid.setSpacing(
            10
        )

        self.gpu_card = StatCard(
            "GPU",
            "--",
            "active accelerator",
        )

        self.gpu_usage_card = StatCard(
            "GPU UTILIZATION",
            "--",
            "GPU load",
        )

        self.vram_card = StatCard(
            "VRAM",
            "--",
            "GPU memory",
        )

        self.temperature_card = StatCard(
            "GPU TEMPERATURE",
            "--",
            "GPU temperature",
        )

        self.cpu_card = StatCard(
            "CPU",
            "--",
            "CPU utilization",
        )

        self.ram_card = StatCard(
            "RAM",
            "--",
            "system memory",
        )

        self.disk_card = StatCard(
            "DISK",
            "--",
            "write throughput",
        )

        self.elapsed_card = StatCard(
            "ELAPSED",
            "00:00:00",
            "export runtime",
        )

        hardware_cards = [
            self.gpu_card,
            self.gpu_usage_card,
            self.vram_card,
            self.temperature_card,
            self.cpu_card,
            self.ram_card,
            self.disk_card,
            self.elapsed_card,
        ]

        for index, card in enumerate(
            hardware_cards
        ):

            row = index // 4
            column = index % 4

            hardware_grid.addWidget(
                card,
                row,
                column,
            )

        main_layout.addLayout(
            hardware_grid
        )

        # ==================================================
        # CONTROLS
        # ==================================================

        controls = QHBoxLayout()

        mode_label = QLabel("ACCELERATION")
        mode_label.setObjectName("sectionTitle")
        controls.addWidget(mode_label)

        self.mode_combo = QComboBox()
        for text, value in ACCELERATION_MODES:
            self.mode_combo.addItem(text, value)
        self.mode_combo.setToolTip(
            "AUTO: decode on the NVIDIA GPU when the self-test passed, otherwise "
            "CPU; falls back to CPU per video if the GPU cannot decode it.\n"
            "GPU: always use NVDEC (fails if unsupported).\n"
            "CPU: never use the GPU (slower, works everywhere)."
        )
        self.mode_combo.setStyleSheet(
            "QComboBox { background: #1e293b; color: #f8fafc; border: 1px solid #334155;"
            " border-radius: 7px; padding: 9px; min-width: 190px; }"
        )
        controls.addWidget(self.mode_combo)

        self.start_button = QPushButton(
            "START EXPORTING"
        )

        self.start_button.setObjectName(
            "startButton"
        )

        self.start_button.clicked.connect(
            self.start_export
        )

        self.pause_button = QPushButton(
            "PAUSE EXPORT"
        )

        self.pause_button.setEnabled(
            False
        )

        self.pause_button.clicked.connect(
            self.toggle_pause
        )

        self.cancel_button = QPushButton(
            "CANCEL EXPORT"
        )

        self.cancel_button.setObjectName(
            "cancelButton"
        )

        self.cancel_button.setEnabled(
            False
        )

        self.cancel_button.clicked.connect(
            self.show_cancel_options
        )

        controls.addWidget(
            self.start_button
        )

        controls.addWidget(
            self.pause_button
        )

        controls.addWidget(
            self.cancel_button
        )

        self.tabs = QTabWidget()

        # On laptop screens (e.g. 1366x768, or 1080p at 125% scaling) the
        # page needs more height than the window has; v2.0 squashed the
        # SELECT buttons to empty bars and overlapped the card rows. A
        # scroll area keeps every widget at its natural size.
        converter_scroll = QScrollArea()
        converter_scroll.setWidgetResizable(True)
        converter_scroll.setFrameShape(QFrame.NoFrame)
        converter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        central.setObjectName("converterPage")
        central.setStyleSheet("QWidget#converterPage { background: #0f172a; }")
        converter_scroll.setWidget(central)

        # Controls stay pinned below the scrollable content.
        converter_page = QWidget()
        converter_page.setObjectName("converterPage")
        page_layout = QVBoxLayout(converter_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(converter_scroll, 1)
        controls_bar = QFrame()
        controls_bar.setObjectName("controlsBar")
        controls_bar.setStyleSheet(
            "QFrame#controlsBar { background: #0f172a; border-top: 1px solid #263244; }"
        )
        controls.setContentsMargins(24, 10, 24, 12)
        controls_bar.setLayout(controls)
        page_layout.addWidget(controls_bar)

        self.tabs.addTab(
            converter_page,
            "VIDEO → FRAMES"
        )

        self.annotation_tab = AnnotationTab(
            self
        )

        self.tabs.addTab(
            self.annotation_tab,
            "ANNOTATION TOOL"
        )

        self.setCentralWidget(
            self.tabs
        )

        # ==================================================
        # SYSTEM MONITOR TIMER
        # ==================================================

        self.previous_disk_bytes = (
            self._disk_write_bytes()
        )

        self.previous_disk_time = (
            time.monotonic()
        )

        self._last_output_size_update = 0.0

        self.monitor_timer = QTimer(
            self
        )

        self.monitor_timer.timeout.connect(
            self.update_system_stats
        )

        self.monitor_timer.start(
            1000
        )

        # GPU telemetry (nvidia-smi) runs on its own thread.
        self.telemetry = None
        if self.hardware is not None and getattr(self.hardware, "vendor", "") == "NVIDIA":
            self.telemetry = TelemetryThread(parent=self)
            self.telemetry.sample.connect(self.update_nvidia_stats)
            self.telemetry.start()
        else:
            for card in (self.gpu_card, self.gpu_usage_card, self.vram_card, self.temperature_card):
                card.set_value("N/A")
            if self.hardware is not None:
                self.gpu_card.set_value(self.hardware.vendor)
                self.gpu_card.set_subtitle("no NVIDIA acceleration path")

        self.start_capability_probe()

    # ==================================================
    # CAPABILITIES
    # ==================================================

    def start_capability_probe(self, refresh=False):
        if self._capability_task is not None and self._capability_task.isRunning():
            return
        self.hardware_header.setText("● CHECKING ACCELERATION…")
        self.hardware_header.setStyleSheet("color: #fbbf24;")
        self.system_check_button.setEnabled(False)
        self._capability_task = FunctionTask(lambda: get_report(refresh=refresh), self)
        self._capability_task.succeeded.connect(self.capabilities_ready)
        self._capability_task.failed.connect(
            lambda message: self.hardware_header.setText(f"● CHECK FAILED: {message}")
        )
        self._capability_task.finished.connect(
            lambda: self.system_check_button.setEnabled(True)
        )
        self._capability_task.start()

    def capabilities_ready(self, report):
        self.capabilities = report
        self.hardware_header.setText(self.hardware_header_text())
        if report.gpu_pipeline_ready:
            color = "#22c55e"
        elif report.ffmpeg_ok:
            color = "#fbbf24"
        else:
            color = "#f87171"
        self.hardware_header.setStyleSheet(f"color: {color};")
        self.hardware_header.setToolTip("\n".join(report.summary_lines()))

        if not report.ffmpeg_ok:
            problems = report.ffmpeg_problems or [report.ffmpeg_error or "FFmpeg unavailable"]
            self.show_message(
                "Video extraction is unavailable:\n\n" + "\n".join(problems)
                + "\n\nThe annotation tool still works."
            )

    def show_system_check(self):
        report = self.capabilities
        dialog = QDialog(self)
        dialog.setWindowTitle("System Check")
        dialog.resize(760, 460)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 9pt;")
        lines = [f"{APP_NAME} {APP_VERSION}", ""]
        lines += report.summary_lines() if report else ["Capability check still running…"]
        lines += ["", f"Logs: {log_dir()}"]
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        buttons = QDialogButtonBox()
        recheck = buttons.addButton("RE-CHECK", QDialogButtonBox.ActionRole)
        copy = buttons.addButton("COPY", QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))

        def do_recheck():
            dialog.accept()
            self.start_capability_probe(refresh=True)

        recheck.clicked.connect(do_recheck)
        dialog.exec()

    @staticmethod
    def _disk_write_bytes():
        # psutil returns None where disk counters are unavailable
        # (containers, some VMs); v2.0 crashed at startup there.
        try:
            counters = psutil.disk_io_counters()
        except Exception:
            counters = None
        return counters.write_bytes if counters else None

    # ==================================================
    # HARDWARE HEADER
    # ==================================================

    def hardware_header_text(self):
        """Describe what the pipeline will really use, never just GPU presence."""

        report = self.capabilities

        if report is None:
            return "● CHECKING ACCELERATION…"

        if not report.ffmpeg_ok:
            return "● FFMPEG UNAVAILABLE — EXTRACTION DISABLED"

        if report.gpu_pipeline_ready:
            return "● NVIDIA NVDEC DECODE VERIFIED"

        if report.gpu_detected:
            return f"● CPU MODE — NVIDIA GPU FOUND, NVDEC {report.nvdec_state.upper()}"

        if self.hardware is not None and getattr(self.hardware, "vendor", "") == "AMD":
            return "● CPU MODE — AMD GPU (NO AMD PIPELINE)"

        return "● CPU MODE — NO NVIDIA GPU"

    # ==================================================
    # INPUT
    # ==================================================

    def select_input(self):

        directory = (
            QFileDialog.getExistingDirectory(
                self,
                "Select Input Directory",
            )
        )

        if not directory:
            return

        self.input_directory = directory

        self.input_label.setText(
            directory
        )

        scanner = DatasetScanner()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.dataset_info = scanner.scan(
                directory
            )
        except OSError as exc:
            self.dataset_info = None
            QApplication.restoreOverrideCursor()
            self.show_message(f"Could not read the input directory:\n{exc}")
            return
        QApplication.restoreOverrideCursor()

        self.videos_card.set_value(
            self.dataset_info.video_count
        )

        self.input_size_card.set_value(
            f"{self.dataset_info.total_gb:.2f} GB"
        )

        self.processed_card.set_value(
            f"0 / "
            f"{self.dataset_info.video_count}"
        )

        if self.dataset_info.video_count == 0:
            self.frames_card.set_value("0")
            self.show_message(
                "No supported video files were found in this folder or its "
                "sub-folders.\n\nSupported: "
                + ", ".join(sorted(e.lstrip(".") for e in VIDEO_EXTENSIONS))
            )
            return

        self.frames_card.set_value(
            "Calculating..."
        )
        self.start_frame_count(self.dataset_info.videos)

    def start_frame_count(self, videos):
        def count():
            exporter = VideoExporter(mode="cpu")
            total = 0
            unreadable = []
            for video in videos:
                try:
                    total += exporter.get_video_info(video).total_frames
                except (VideoProbeError, OSError) as exc:
                    unreadable.append(f"{video.name}: {str(exc).splitlines()[0]}")
            return total, unreadable

        task = FunctionTask(count, self)
        task.succeeded.connect(self.frame_count_ready)
        task.failed.connect(lambda message: self.frames_card.set_value("--"))
        task.finished.connect(lambda: setattr(self, "_frame_count_task", None))
        task.finished.connect(task.deleteLater)
        self._frame_count_task = task
        task.start()

    def frame_count_ready(self, result):
        total, unreadable = result
        self.total_dataset_frames = total
        self.frames_card.set_value(f"{total:,}")
        if unreadable:
            self.frames_card.set_subtitle(f"{len(unreadable)} unreadable file(s)")
            self.frames_card.setToolTip("\n".join(unreadable))
        else:
            self.frames_card.set_subtitle("estimated frames")
            self.frames_card.setToolTip("")

    # ==================================================
    # OUTPUT
    # ==================================================

    def select_output(self):

        directory = (
            QFileDialog.getExistingDirectory(
                self,
                "Select Output Directory",
            )
        )

        if not directory:
            return

        self.output_directory = directory

        self.output_label.setText(
            directory
        )

    # ==================================================
    # START
    # ==================================================

    def start_export(self):

        if not self.input_directory:

            self.show_message(
                "Please select an input directory."
            )

            return

        if not self.output_directory:

            self.show_message(
                "Please select an output directory."
            )

            return

        if not self.dataset_info:

            self.show_message(
                "Please select an input directory first."
            )

            return

        if self.worker is not None and self.worker.isRunning():
            return

        videos = self.dataset_info.videos

        if not videos:
            self.show_message("The input directory contains no supported videos.")
            return

        report = self.capabilities
        if report is not None and not report.ffmpeg_ok:
            problems = report.ffmpeg_problems or [report.ffmpeg_error or "FFmpeg unavailable"]
            self.show_message("Cannot export:\n\n" + "\n".join(problems))
            return

        output_directory = Path(
            self.output_directory
        )

        problem = self._output_directory_problem(output_directory)
        if problem:
            self.show_message(problem)
            return

        mode = self.mode_combo.currentData()
        if mode == "gpu" and report is not None and not report.gpu_pipeline_ready:
            answer = QMessageBox.question(
                self,
                "GPU not verified",
                "GPU decoding did not pass the self-test on this system "
                f"(NVDEC: {report.nvdec_state} {report.nvdec_detail}).\n\n"
                "Exports in GPU-only mode will most likely fail. Switch to AUTO?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self.mode_combo.setCurrentIndex(0)

        job = self.job_manager.create_job(
            self.input_directory,
            self.output_directory,
            videos,
        )

        self.job_id = job["job_id"]

        self.export_start_time = (
            time.monotonic()
        )

        self.total_processed_videos = 0

        self.total_output_bytes = 0

        self.failed_videos = {}

        self._launch_worker(videos, output_directory)

    def _output_directory_problem(self, output_directory: Path):
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"The output directory cannot be created:\n{exc}"

        if not os.access(output_directory, os.W_OK):
            return (
                "The output directory is not writable. Choose a folder you "
                f"have write access to.\n\n{output_directory}"
            )

        try:
            if output_directory.resolve() == Path(self.input_directory).resolve():
                return (
                    "Please choose an output directory different from the input "
                    "directory, so extracted frames are kept apart from the videos."
                )
        except OSError:
            pass

        return None

    def _launch_worker(self, videos, output_directory):
        self._job_ended = False
        self.start_button.setEnabled(False)
        self.start_button.setText("EXPORTING...")
        self.pause_button.setEnabled(True)
        self.pause_button.setText("PAUSE EXPORT")
        self.cancel_button.setEnabled(True)
        self.mode_combo.setEnabled(False)

        worker = ExportWorker(
            videos,
            output_directory,
            self.job_id,
            acceleration_mode=self.mode_combo.currentData(),
        )

        worker.progress.connect(self.update_progress)
        worker.video_finished.connect(self.video_finished)
        worker.video_failed.connect(self.video_failed)
        worker.warning.connect(self.export_warning)
        worker.job_finished.connect(self.export_finished)
        worker.paused.connect(self.export_paused)
        worker.stopped.connect(self.export_stopped)
        worker.cancelled.connect(self.export_cancelled)
        worker.error.connect(self.export_error)
        # QThread.finished fires once the thread has really stopped; only
        # then may the object be released (v2.0 dropped the reference from
        # inside slots while run() was still executing).
        worker.finished.connect(lambda w=worker: self._worker_thread_done(w))

        # Parent the thread to the window: Qt then owns the C++ object, so
        # dropping the Python reference can never destroy a running thread.
        worker.setParent(self)

        previous = self.worker
        if previous is not None and not previous.isRunning():
            previous.deleteLater()

        self.worker = worker
        worker.start()

    def _worker_thread_done(self, worker):
        self.mode_combo.setEnabled(True)
        if self.worker is not worker:
            worker.deleteLater()
            return
        if self._job_ended:
            self.worker = None
            worker.deleteLater()
        # Paused/stopped: keep the finished thread object; RESUME replaces it.

    # ==================================================
    # PROGRESS
    # ==================================================

    def update_progress(
        self,
        data,
    ):

        video = data.get(
            "video",
            "--",
        )

        frames = int(
            data.get(
                "frames",
                0,
            )
        )

        total_frames = int(
            data.get(
                "total_frames",
                0,
            )
        )

        fps = float(
            data.get(
                "fps",
                0,
            )
        )

        speed = float(
            data.get(
                "speed",
                0,
            )
        )

        self.current_video_name = video

        self.current_video_label.setText(
            video
        )

        self.current_video_frames = frames

        self.current_video_total_frames = (
            total_frames
        )

        self.current_frame_label.setText(
            f"Frame {frames:,} / "
            f"{total_frames:,}"
        )

        if total_frames > 0:

            percentage = (
                frames /
                total_frames *
                100
            )

            percentage = max(
                0,
                min(
                    100,
                    percentage,
                ),
            )

            self.current_progress.setValue(
                int(percentage)
            )

            self.progress_card.set_value(
                f"{percentage:.1f}%"
            )

        self.speed_card.set_value(
            f"{speed:.2f}x"
        )

        self.speed_card.set_subtitle(
            f"{fps:.0f} FPS"
        )

        self.update_eta(
            frames,
            total_frames,
            fps,
        )

        pipeline = data.get("pipeline")
        if pipeline and pipeline != self.current_pipeline:
            self.current_pipeline = pipeline
            self.pipeline_label.setText(f"Pipeline: {pipeline}")
            if pipeline == PIPELINE_GPU:
                self.pipeline_label.setStyleSheet("color: #4ade80;")
            elif pipeline == PIPELINE_CPU:
                self.pipeline_label.setStyleSheet("color: #fbbf24;")
            else:
                self.pipeline_label.setStyleSheet("")

        # Output size is refreshed by the 1 s timer on a worker thread;
        # v2.0 rescanned the whole output tree here on every progress line.

    # ==================================================
    # ETA
    # ==================================================

    def update_eta(
        self,
        frames,
        total_frames,
        fps,
    ):
        """ETA for the current video from FFmpeg's live frames-per-second."""

        if total_frames <= 0 or fps <= 0:

            self.eta_card.set_value(
                "--"
            )

            return

        remaining = max(
            0,
            total_frames - frames,
        )

        self.eta_card.set_value(
            self.format_duration(
                remaining / fps
            )
        )
        self.eta_card.set_subtitle("current video")

    # ==================================================
    # VIDEO FINISHED
    # ==================================================

    def video_finished(self):

        self.total_processed_videos += 1

        if self.dataset_info:

            total = (
                self.dataset_info.video_count
            )

            self.processed_card.set_value(
                f"{self.total_processed_videos} "
                f"/ {total}"
            )

    def video_failed(self, name, message):
        # Collected and summarised at the end instead of one modal dialog
        # per file; the batch continues with the next video.
        self.failed_videos[name] = message
        self.processed_card.set_subtitle(
            f"videos completed • {len(self.failed_videos)} failed"
        )
        self.dataset_label_status(f"FAILED: {name} — continuing")

    def export_warning(self, message):
        log.warning(message)
        self.pipeline_label.setToolTip(message)

    # ==================================================
    # PAUSE
    # ==================================================

    def toggle_pause(self):

        if self.worker is None:
            return

        if (
            self.pause_button.text()
            == "PAUSE EXPORT"
        ):

            self.worker.pause()

            self.pause_button.setEnabled(
                False
            )

            self.dataset_label_status(
                "Pausing export..."
            )

        elif (
            self.pause_button.text()
            == "RESUME EXPORT"
        ):

            self.resume_export()

    # ==================================================
    # RESUME
    # ==================================================

    def resume_export(self):

        if self.worker is not None:

            if self.worker.isRunning():
                return

        if not self.job_id:

            return

        job = self.job_manager.load_job(
            self.job_id
        )

        if not job:

            self.show_message(
                "Resume job could not be found."
            )

            return

        videos = [
            Path(video)
            for video in job.get(
                "videos",
                [],
            )
        ]

        output_directory = Path(
            job["output_directory"]
        )

        # Already-finished videos are re-reported (quickly, via their
        # .complete marker) by the new worker, so the counter restarts.
        self.total_processed_videos = 0
        self.failed_videos = {}

        self._launch_worker(videos, output_directory)

    # ==================================================
    # CANCEL
    # ==================================================

    def show_cancel_options(self):

        if self.worker is None:
            return

        dialog = QMessageBox(
            self
        )

        dialog.setWindowTitle(
            "Cancel Export"
        )

        dialog.setText(
            "Choose how to cancel this export."
        )

        keep_button = dialog.addButton(
            "STOP & KEEP PROGRESS",
            QMessageBox.AcceptRole,
        )

        delete_button = dialog.addButton(
            "CANCEL & DELETE",
            QMessageBox.DestructiveRole,
        )

        dialog.addButton(
            "BACK",
            QMessageBox.RejectRole,
        )

        dialog.exec()

        clicked = (
            dialog.clickedButton()
        )

        if not self.worker.isRunning():
            # Paused/stopped: there is no running thread to signal (v2.0
            # called worker.cancel_delete(), a no-op here, and the UI stuck).
            self._cancel_idle_job(clicked == delete_button, clicked == keep_button)
            return

        if clicked == keep_button:

            self.worker.stop_keep()

            self.pause_button.setEnabled(
                False
            )

            self.cancel_button.setEnabled(
                False
            )

            self.dataset_label_status(
                "Stopping — progress will be kept."
            )

        elif clicked == delete_button:

            confirm = (
                QMessageBox.question(
                    self,
                    "Delete Export",
                    "This will permanently delete "
                    "all exported frames for the "
                    "current video.\n\n"
                    "Are you sure?",
                    QMessageBox.Yes |
                    QMessageBox.No,
                    QMessageBox.No,
                )
            )

            if confirm == QMessageBox.Yes:

                self.worker.cancel_delete()

                self.pause_button.setEnabled(
                    False
                )

                self.cancel_button.setEnabled(
                    False
                )

                self.dataset_label_status(
                    "Cancelling and deleting..."
                )

    def _cancel_idle_job(self, delete, keep):
        if not (delete or keep):
            return

        job = self.job_manager.load_job(self.job_id) if self.job_id else None

        if delete:
            confirm = QMessageBox.question(
                self,
                "Delete Export",
                "This will permanently delete all exported frames for the "
                "video that was in progress.\n\nAre you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            current = job.get("current_video") if job else None
            if current:
                videos = [Path(v) for v in job.get("videos", [])]
                name = output_names(videos).get(Path(current), Path(current).stem)
                target = Path(job["output_directory"]) / name
                shutil.rmtree(target, ignore_errors=True)
            if self.job_id:
                self.job_manager.cancel_job(self.job_id)
            self.export_cancelled()
            self._release_idle_worker()
            return

        if self.job_id:
            self.job_manager.update_job(self.job_id, status="stopped")
        self.export_stopped()

    def _release_idle_worker(self):
        worker = self.worker
        if worker is not None and not worker.isRunning():
            self.worker = None
            worker.deleteLater()

    # ==================================================
    # PAUSED
    # ==================================================

    def export_paused(self):

        self.start_button.setEnabled(
            False
        )

        self.pause_button.setEnabled(
            True
        )

        self.pause_button.setText(
            "RESUME EXPORT"
        )

        self.cancel_button.setEnabled(
            True
        )

        self.dataset_label_status(
            "EXPORT PAUSED — progress preserved"
        )

    # ==================================================
    # STOPPED
    # ==================================================

    def export_stopped(self):

        self.start_button.setEnabled(
            False
        )

        self.pause_button.setEnabled(
            True
        )

        self.pause_button.setText(
            "RESUME EXPORT"
        )

        self.cancel_button.setEnabled(
            False
        )

        self.dataset_label_status(
            "EXPORT STOPPED — progress preserved"
        )

    # ==================================================
    # CANCELLED
    # ==================================================

    def export_cancelled(self):

        self.start_button.setEnabled(
            True
        )

        self.start_button.setText(
            "START EXPORTING"
        )

        self.pause_button.setEnabled(
            False
        )

        self.cancel_button.setEnabled(
            False
        )

        self.pause_button.setText(
            "PAUSE EXPORT"
        )

        self.dataset_label_status(
            "EXPORT CANCELLED — OUTPUT DELETED"
        )

        self._job_ended = True
        self.job_id = None

        self.current_progress.setValue(
            0
        )

    # ==================================================
    # COMPLETED
    # ==================================================

    def export_finished(self, summary=None):

        summary = summary or {}
        failed = summary.get("failed") or self.failed_videos

        self.start_button.setEnabled(
            True
        )

        self.start_button.setText(
            "START EXPORTING"
        )

        self.pause_button.setEnabled(
            False
        )

        self.pause_button.setText(
            "PAUSE EXPORT"
        )

        self.cancel_button.setEnabled(
            False
        )

        self.progress_card.set_value(
            "100%"
        )

        self.current_progress.setValue(
            100
        )

        self.eta_card.set_value(
            "DONE"
        )

        self._job_ended = True

        if failed:
            self.dataset_label_status(
                f"EXPORT FINISHED — {len(failed)} VIDEO(S) FAILED"
            )
            details = "\n\n".join(
                f"• {Path(name).name}\n{message}" for name, message in failed.items()
            )
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Export finished with errors")
            box.setText(
                f"{summary.get('completed', 0)} of {summary.get('total', 0)} videos "
                f"were exported. {len(failed)} could not be processed.\n\n"
                "Frames from successful videos are complete. See details below "
                f"or the log folder:\n{log_dir()}"
            )
            box.setDetailedText(details)
            box.exec()
        else:
            self.dataset_label_status(
                "EXPORT COMPLETED"
            )

    # ==================================================
    # ERROR
    # ==================================================

    def export_error(
        self,
        message,
    ):

        self.start_button.setEnabled(
            True
        )

        self.start_button.setText(
            "START EXPORTING"
        )

        self.pause_button.setEnabled(
            False
        )

        self.cancel_button.setEnabled(
            False
        )

        self.dataset_label_status(
            "EXPORT ERROR"
        )

        self._job_ended = True

        QMessageBox.critical(
            self,
            "Export Error",
            f"{message}\n\nLogs: {log_dir()}",
        )

    # ==================================================
    # SYSTEM MONITOR
    # ==================================================

    def update_system_stats(self):

        # ----------------------------------------------
        # CPU
        # ----------------------------------------------

        cpu = psutil.cpu_percent(
            interval=None
        )

        self.cpu_card.set_value(
            f"{cpu:.0f}%"
        )

        # ----------------------------------------------
        # RAM
        # ----------------------------------------------

        memory = psutil.virtual_memory()

        used_gb = (
            memory.used /
            (1024 ** 3)
        )

        total_gb = (
            memory.total /
            (1024 ** 3)
        )

        self.ram_card.set_value(
            f"{used_gb:.1f} GB"
        )

        self.ram_card.set_subtitle(
            f"of {total_gb:.1f} GB"
        )

        # ----------------------------------------------
        # DISK
        # ----------------------------------------------

        written = self._disk_write_bytes()

        now = time.monotonic()

        if written is None or self.previous_disk_bytes is None:

            self.disk_card.set_value("N/A")
            self.previous_disk_bytes = written

        else:

            delta_bytes = max(0, written - self.previous_disk_bytes)

            delta_time = (
                now -
                self.previous_disk_time
            )

            write_speed = (
                delta_bytes / delta_time / (1024 ** 2)
                if delta_time > 0
                else 0
            )

            self.previous_disk_bytes = written

            if write_speed >= 1024:

                self.disk_card.set_value(
                    f"{write_speed / 1024:.2f} GB/s"
                )

            else:

                self.disk_card.set_value(
                    f"{write_speed:.0f} MB/s"
                )

        self.previous_disk_time = now

        # GPU telemetry arrives from TelemetryThread.

        # ----------------------------------------------
        # Elapsed
        # ----------------------------------------------

        if self.export_start_time:

            elapsed = (
                time.monotonic()
                - self.export_start_time
            )

            self.elapsed_card.set_value(
                self.format_duration(
                    elapsed
                )
            )

        # ----------------------------------------------
        # Output size
        # ----------------------------------------------

        self.update_output_size()

    # ==================================================
    # NVIDIA METRICS
    # ==================================================

    def update_nvidia_stats(self, sample):
        """Receives samples from TelemetryThread (never blocks the GUI)."""

        if not sample:
            self.gpu_usage_card.set_value("N/A")
            return

        def fmt(value, suffix=""):
            return "N/A" if value is None else f"{value:.0f}{suffix}"

        name = sample.get("name", "NVIDIA GPU")
        self.gpu_card.set_value(name.replace("NVIDIA GeForce ", ""))
        self.gpu_card.setToolTip(name)
        if self.capabilities is not None:
            self.gpu_card.set_subtitle(
                "NVDEC verified" if self.capabilities.gpu_pipeline_ready
                else f"NVDEC {self.capabilities.nvdec_state}"
            )

        self.gpu_usage_card.set_value(fmt(sample.get("gpu"), "%"))
        decoder = sample.get("decoder")
        self.gpu_usage_card.set_subtitle(
            "GPU load" if decoder is None else f"GPU load • NVDEC {decoder:.0f}%"
        )

        used, total = sample.get("vram_used"), sample.get("vram_total")
        if used is not None:
            self.vram_card.set_value(f"{used / 1024:.1f} GB")
        if total is not None:
            self.vram_card.set_subtitle(f"of {total / 1024:.1f} GB")

        self.temperature_card.set_value(fmt(sample.get("temperature"), "°C"))

    # ==================================================
    # OUTPUT SIZE
    # ==================================================

    def update_output_size(self, force=False):
        """Refresh the OUTPUT SIZE card on a worker thread (at most every 3 s)."""

        if not self.output_directory:
            return

        now = time.monotonic()
        if not force and now - self._last_output_size_update < 3.0:
            return

        if self._output_size_task is not None and self._output_size_task.isRunning():
            return

        root = Path(self.output_directory)
        if not root.exists():
            return

        self._last_output_size_update = now
        task = FunctionTask(lambda: directory_jpeg_bytes(root), self)
        task.succeeded.connect(self._output_size_ready)
        task.finished.connect(lambda: setattr(self, "_output_size_task", None))
        task.finished.connect(task.deleteLater)
        self._output_size_task = task
        task.start()

    def _output_size_ready(self, total_bytes):
        self.total_output_bytes = total_bytes
        self.output_size_card.set_value(f"{total_bytes / (1024 ** 3):.2f} GB")

    # ==================================================
    # SHUTDOWN
    # ==================================================

    def closeEvent(self, event):
        if self.annotation_tab.has_unsaved_changes():
            answer = QMessageBox.question(
                self,
                "Unsaved annotations",
                "Save annotation changes to annotations.csv before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Save and not self.annotation_tab.save_annotations():
                event.ignore()
                return

        worker = self.worker
        if worker is not None and worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Export in progress",
                "An export is running. Stop it and keep the frames extracted so "
                "far? It can be resumed later from the same output folder.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            worker.stop_keep()
            # FFmpeg is asked to quit gracefully (up to ~10 s worst case).
            worker.wait(20000)

        if self.telemetry is not None:
            self.telemetry.stop()
            self.telemetry.wait(3000)

        for task in (self._capability_task, self._frame_count_task, self._output_size_task):
            try:
                if task is not None and task.isRunning():
                    task.wait(10000)
            except RuntimeError:
                pass  # already deleted

        self.monitor_timer.stop()
        self.annotation_tab.shutdown()
        super().closeEvent(event)

    # ==================================================
    # STATUS
    # ==================================================

    def dataset_label_status(
        self,
        text,
    ):

        self.current_video_label.setText(
            text
        )

    # ==================================================
    # MESSAGE
    # ==================================================

    def show_message(
        self,
        message,
    ):

        QMessageBox.warning(
            self,
            "Frame Generator",
            message,
        )

    # ==================================================
    # FORMAT TIME
    # ==================================================

    @staticmethod
    def format_duration(
        seconds,
    ):

        try:

            seconds = int(
                max(
                    0,
                    seconds,
                )
            )

            hours = (
                seconds // 3600
            )

            minutes = (
                (seconds % 3600)
                // 60
            )

            seconds = (
                seconds % 60
            )

            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        except Exception:

            return "--"