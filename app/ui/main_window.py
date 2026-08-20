from pathlib import Path
import subprocess
import time

import psutil

from PySide6.QtCore import Qt, QTimer
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
)

from app.hardware.detector import HardwareDetector
from app.processing.scanner import DatasetScanner
from app.processing.worker import ExportWorker
from app.jobs.job_manager import JobManager

from app.ui.annotation_tab import AnnotationTab


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
            "Frame Generator"
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

        self.hardware = (
            HardwareDetector().detect()
        )

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

        main_layout.addLayout(
            controls
        )

        self.tabs = QTabWidget()

        self.tabs.addTab(
            central,
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
            psutil.disk_io_counters()
            .write_bytes
        )

        self.previous_disk_time = (
            time.monotonic()
        )

        self.monitor_timer = QTimer(
            self
        )

        self.monitor_timer.timeout.connect(
            self.update_system_stats
        )

        self.monitor_timer.start(
            1000
        )

    # ==================================================
    # HARDWARE HEADER
    # ==================================================

    def hardware_header_text(self):

        if self.hardware is None:
            return "CPU MODE"

        vendor = getattr(
            self.hardware,
            "vendor",
            "",
        )

        if vendor == "NVIDIA":

            return (
                "● NVIDIA ACCELERATION"
            )

        if vendor == "AMD":

            return (
                "● AMD ACCELERATION"
            )

        return "● CPU MODE"

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

        self.dataset_info = scanner.scan(
            directory
        )

        self.videos_card.set_value(
            self.dataset_info.video_count
        )

        self.input_size_card.set_value(
            f"{self.dataset_info.total_gb:.2f} GB"
        )

        self.frames_card.set_value(
            "Calculating..."
        )

        self.processed_card.set_value(
            f"0 / "
            f"{self.dataset_info.video_count}"
        )

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

        videos = self.dataset_info.videos

        output_directory = Path(
            self.output_directory
        )

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

        self.start_button.setEnabled(
            False
        )

        self.start_button.setText(
            "EXPORTING..."
        )

        self.pause_button.setEnabled(
            True
        )

        self.pause_button.setText(
            "PAUSE EXPORT"
        )

        self.cancel_button.setEnabled(
            True
        )

        self.worker = ExportWorker(
            videos,
            output_directory,
            self.job_id,
        )

        self.worker.progress.connect(
            self.update_progress
        )

        self.worker.video_finished.connect(
            self.video_finished
        )

        self.worker.finished.connect(
            self.export_finished
        )

        self.worker.paused.connect(
            self.export_paused
        )

        self.worker.stopped.connect(
            self.export_stopped
        )

        self.worker.cancelled.connect(
            self.export_cancelled
        )

        self.worker.error.connect(
            self.export_error
        )

        self.worker.start()

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
            speed,
        )

        self.update_output_size()

    # ==================================================
    # ETA
    # ==================================================

    def update_eta(
        self,
        frames,
        total_frames,
        speed,
    ):

        if (
            total_frames <= 0
            or speed <= 0
            or self.export_start_time is None
        ):

            self.eta_card.set_value(
                "--"
            )

            return

        remaining = max(
            0,
            total_frames - frames,
        )

        # Speed is relative to source
        # playback speed.

        remaining_seconds = (
            remaining /
            max(
                1,
                self.current_video_total_frames,
            )
        )

        elapsed = (
            time.monotonic()
            - self.export_start_time
        )

        if frames > 0:

            seconds_per_frame = (
                elapsed /
                frames
            )

            remaining_seconds = (
                remaining *
                seconds_per_frame
            )

        self.eta_card.set_value(
            self.format_duration(
                remaining_seconds
            )
        )

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

        self.start_button.setEnabled(
            False
        )

        self.pause_button.setEnabled(
            True
        )

        self.pause_button.setText(
            "PAUSE EXPORT"
        )

        self.cancel_button.setEnabled(
            True
        )

        self.worker = ExportWorker(
            videos,
            output_directory,
            self.job_id,
        )

        self.worker.progress.connect(
            self.update_progress
        )

        self.worker.video_finished.connect(
            self.video_finished
        )

        self.worker.finished.connect(
            self.export_finished
        )

        self.worker.paused.connect(
            self.export_paused
        )

        self.worker.stopped.connect(
            self.export_stopped
        )

        self.worker.cancelled.connect(
            self.export_cancelled
        )

        self.worker.error.connect(
            self.export_error
        )

        self.worker.start()

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

        self.worker = None
        self.job_id = None

        self.current_progress.setValue(
            0
        )

    # ==================================================
    # COMPLETED
    # ==================================================

    def export_finished(self):

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

        self.dataset_label_status(
            "EXPORT COMPLETED"
        )

        self.worker = None

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

        QMessageBox.critical(
            self,
            "Export Error",
            message,
        )

        self.worker = None

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

        disk = psutil.disk_io_counters()

        now = time.monotonic()

        delta_bytes = (
            disk.write_bytes -
            self.previous_disk_bytes
        )

        delta_time = (
            now -
            self.previous_disk_time
        )

        if delta_time > 0:

            write_speed = (
                delta_bytes /
                delta_time /
                (1024 ** 2)
            )

        else:

            write_speed = 0

        self.previous_disk_bytes = (
            disk.write_bytes
        )

        self.previous_disk_time = now

        if write_speed >= 1024:

            self.disk_card.set_value(
                f"{write_speed / 1024:.2f} GB/s"
            )

        else:

            self.disk_card.set_value(
                f"{write_speed:.0f} MB/s"
            )

        # ----------------------------------------------
        # GPU
        # ----------------------------------------------

        self.update_nvidia_stats()

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

    def update_nvidia_stats(self):

        if self.hardware is None:
            return

        if getattr(
            self.hardware,
            "vendor",
            "",
        ) != "NVIDIA":

            self.gpu_card.set_value(
                "N/A"
            )

            self.gpu_usage_card.set_value(
                "N/A"
            )

            self.vram_card.set_value(
                "N/A"
            )

            self.temperature_card.set_value(
                "N/A"
            )

            return

        try:

            command = [
                "nvidia-smi",
                "--query-gpu="
                "name,"
                "utilization.gpu,"
                "memory.used,"
                "memory.total,"
                "temperature.gpu",
                "--format=csv,noheader,nounits",
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=1,
            )

            if result.returncode != 0:
                return

            values = [
                x.strip()
                for x in result.stdout.split(
                    ","
                )
            ]

            if len(values) < 5:
                return

            name = values[0]
            gpu_util = values[1]
            memory_used = values[2]
            memory_total = values[3]
            temperature = values[4]

            self.gpu_card.set_value(
                name
            )

            self.gpu_usage_card.set_value(
                f"{gpu_util}%"
            )

            self.vram_card.set_value(
                f"{float(memory_used) / 1024:.1f} GB"
            )

            self.vram_card.set_subtitle(
                f"of "
                f"{float(memory_total) / 1024:.1f} GB"
            )

            self.temperature_card.set_value(
                f"{temperature}°C"
            )

        except Exception:

            pass

    # ==================================================
    # OUTPUT SIZE
    # ==================================================

    def update_output_size(self):

        if not self.output_directory:
            return

        try:

            root = Path(
                self.output_directory
            )

            if not root.exists():
                return

            total_bytes = 0

            for file in root.rglob(
                "*.jpg"
            ):

                try:
                    total_bytes += (
                        file.stat().st_size
                    )

                except OSError:
                    pass

            self.total_output_bytes = (
                total_bytes
            )

            gb = (
                total_bytes /
                (1024 ** 3)
            )

            self.output_size_card.set_value(
                f"{gb:.2f} GB"
            )

        except Exception:

            pass

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