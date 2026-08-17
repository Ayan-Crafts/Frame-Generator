from pathlib import Path

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

        # State
        self.input_directory = ""
        self.output_directory = ""
        self.hardware = HardwareDetector().detect()
        self.dataset_info = None
        self.worker = None

        # Labels
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

        # Buttons
        input_button = QPushButton(
            "Select Input Directory"
        )

        output_button = QPushButton(
            "Select Output Directory"
        )

        self.start_button = QPushButton(
            "START EXPORTING"
        )

        # Connections
        input_button.clicked.connect(
            self.select_input
        )

        output_button.clicked.connect(
            self.select_output
        )

        self.start_button.clicked.connect(
            self.start_export
        )

        # Layout
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

        layout.addStretch()

        layout.addWidget(
            self.start_button
        )

        # Window
        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)

    # --------------------------------------------------
    # Input directory
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Output directory
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Hardware
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Start export
    # --------------------------------------------------

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

        if self.dataset_info.video_count == 0:

            self.dataset_label.setText(
                "No supported videos found."
            )

            return

        videos = self.dataset_info.videos

        output_directory = Path(
            self.output_directory
        )

        # Disable start button while exporting
        self.start_button.setEnabled(False)

        self.start_button.setText(
            "EXPORTING..."
        )

        self.dataset_label.setText(
            f"Starting export of "
            f"{len(videos)} videos..."
        )

        # Create worker
        self.worker = ExportWorker(
            videos,
            output_directory,
        )

        # Connect signals
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

        # Start background thread
        self.worker.start()

    # --------------------------------------------------
    # Progress
    # --------------------------------------------------

    def update_progress(self, data):

        self.dataset_label.setText(
            f"Processing: {data['video']} | "
            f"Frames: {data['frames']} | "
            f"FPS: {data['fps']:.0f} | "
            f"Speed: {data['speed']:.2f}x"
        )

    # --------------------------------------------------
    # Video finished
    # --------------------------------------------------

    def video_finished(self):

        print("Video completed.")

    # --------------------------------------------------
    # Export finished
    # --------------------------------------------------

    def export_finished(self):

        self.start_button.setEnabled(True)

        self.start_button.setText(
            "START EXPORTING"
        )

        self.dataset_label.setText(
            "Export completed."
        )

        self.worker = None

    # --------------------------------------------------
    # Export error
    # --------------------------------------------------

    def export_error(self, message):

        self.start_button.setEnabled(True)

        self.start_button.setText(
            "START EXPORTING"
        )

        self.dataset_label.setText(
            f"Error: {message}"
        )