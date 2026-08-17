from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.processing.exporter import VideoExporter


class ExportWorker(QThread):

    progress = Signal(dict)
    video_finished = Signal()
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        videos: list[Path],
        output_directory: Path,
    ):
        super().__init__()

        self.videos = videos
        self.output_directory = output_directory
        self._stop_requested = False

    def run(self):
        exporter = VideoExporter()

        exporter.progress.connect(self.progress.emit)
        exporter.error.connect(self.error.emit)

        for video in self.videos:

            if self._stop_requested:
                break

            exporter.export_video(
                video,
                self.output_directory,
            )

            self.video_finished.emit()

        self.finished.emit()

    def stop(self):
        self._stop_requested = True