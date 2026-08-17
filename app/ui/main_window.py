from pathlib import Path
from PySide6.QtCore import QTimer
from app.monitoring.system import SystemMonitor
from app.jobs.job_manager import JobManager
from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QWidget,
)
from app.hardware.detector import HardwareDetector
from app.processing.scanner import DatasetScanner
from app.processing.worker import ExportWorker
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Frame Generator")
        self.resize(700, 450)
        self.input_directory = ""
        self.output_directory = ""
        self.hardware = HardwareDetector().detect()
        self.dataset_info = None
        self.worker = None
        self.monitor = SystemMonitor()
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(
        self.update_system_stats
        )
        self.worker = None
        self.dataset_info = None
        self.job_manager = JobManager()
        self.job_id = None
        self.monitor_timer.start(1000)
        self.input_label = QLabel(
            "Input: Not selected"
        )
        self.output_label = QLabel(
            "Output: Not selected"
        )
        self.hardware_label = QLabel(
            self.hardware_status()
        )
        self.dataset_label = QLabel(
            "Dataset: Not scanned"
        )
        input_button = QPushButton(
            "Select Input Directory"
        )
        output_button = QPushButton(
            "Select Output Directory"
        )
        self.start_button = QPushButton(
            "START EXPORTING"
        )
        self.stats_label = QLabel(
            "System: Idle"
        )
        input_button.clicked.connect(
            self.select_input
        )
        output_button.clicked.connect(
            self.select_output
        )
        self.start_button.clicked.connect(
            self.start_export
        )
        layout = QVBoxLayout()
        layout.addWidget(
            self.input_label
        )
        layout.addWidget(
            input_button
        )
        layout.addWidget(
            self.output_label
        )
        layout.addWidget(
            output_button
        )
        layout.addWidget(
            self.hardware_label
        )
        layout.addWidget(
            self.dataset_label
        )
        layout.addWidget(
        self.stats_label
        )
        layout.addStretch()
        layout.addWidget(
            self.start_button
        )
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
    def select_input(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Input Directory"
        )
        if not directory:
            return
        self.input_directory = directory
        self.input_label.setText(
            f"Input: {directory}"
        )
        scanner = DatasetScanner()
        self.dataset_info = scanner.scan(
            directory
        )
        self.dataset_label.setText(
            f"Dataset: "
            f"{self.dataset_info.video_count} videos | "
            f"{self.dataset_info.total_gb:.2f} GB"
        )
    def select_output(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory"
        )
        if not directory:
            return
        self.output_directory = directory
        self.output_label.setText(
            f"Output: {directory}"
        )
    def hardware_status(self):
        if self.hardware is None:
            return "Hardware: CPU"
        if self.hardware.vendor == "NVIDIA":
            memory = (
                f"{self.hardware.memory_mb / 1024:.1f} GB"
                if self.hardware.memory_mb
                else "Unknown"
            )
            return (
                f"Hardware: NVIDIA "
                f"{self.hardware.name} | "
                f"VRAM: {memory} | "
                f"Driver: {self.hardware.driver} | "
                f"Acceleration: "
                f"{self.hardware.acceleration}"
            )
        if self.hardware.vendor == "AMD":
            return (
                f"Hardware: AMD "
                f"{self.hardware.name} | "
                f"Acceleration: "
                f"{self.hardware.acceleration}"
            )

        return "Hardware: CPU"
    def start_export(self):

        if not self.input_directory:
            self.dataset_label.setText(
                "Please select an input directory."
            )
            return

        if not self.output_directory:
            self.dataset_label.setText(
                "Please select an output directory."
            )
            return

        if not self.dataset_info:
            self.dataset_label.setText(
                "Dataset has not been scanned."
            )
            return

        videos = self.dataset_info.videos

        output_directory = Path(
            self.output_directory
        )

        # ------------------------------------------
        # Create persistent job
        # ------------------------------------------

        job = self.job_manager.create_job(
            self.input_directory,
            self.output_directory,
            videos,
        )

        self.job_id = job["job_id"]

        # ------------------------------------------
        # UI
        # ------------------------------------------

        self.start_button.setEnabled(False)
        self.start_button.setText(
            "EXPORTING..."
        )

        self.dataset_label.setText(
            "Export starting..."
        )

        # ------------------------------------------
        # Worker
        # ------------------------------------------

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

        self.worker.error.connect(
            self.export_error
        )

        self.worker.start()
    def update_progress(self, data):

        self.dataset_label.setText(
            f"Processing: {data['video']} | "
            f"Frames: {data['frames']:,} | "
            f"FPS: {data['fps']:.0f} | "
            f"Speed: {data['speed']:.2f}x | "
            f"Time: {data['time']}"
        )
    def video_finished(self):
        print("Video completed.")
    def export_finished(self):
        self.start_button.setEnabled(True)
        self.start_button.setText(
            "START EXPORTING"
        )
        self.dataset_label.setText(
            "Export completed."
        )
        self.worker = None
    def export_error(self, message):

        self.start_button.setEnabled(True)

        self.start_button.setText(
            "START EXPORTING"
        )

        self.dataset_label.setText(
            f"Error: {message}"
        )
    def update_system_stats(self):

        cpu = self.monitor.cpu_percent()

        memory = self.monitor.memory()

        nvidia = self.monitor.nvidia()

        ram_used_gb = (
            memory["used"] / (1024 ** 3)
        )

        ram_total_gb = (
            memory["total"] / (1024 ** 3)
        )

        text = (
            f"CPU: {cpu:.0f}% | "
            f"RAM: {ram_used_gb:.1f}/"
            f"{ram_total_gb:.1f} GB"
        )

        if nvidia:

            vram_used = nvidia["vram_used"]
            vram_total = nvidia["vram_total"]

            text += (
                f" | GPU: {nvidia['gpu']:.0f}%"
                f" | VRAM: "
                f"{vram_used:.0f}/"
                f"{vram_total:.0f} MB"
                f" | Temp: "
                f"{nvidia['temperature']:.0f}°C"
            )

        self.stats_label.setText(text)