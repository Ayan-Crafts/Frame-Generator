from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.processing.exporter import VideoExporter
from app.jobs.job_manager import JobManager


class ExportWorker(QThread):

    progress = Signal(dict)
    video_finished = Signal()
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        videos: list[Path],
        output_directory: Path,
        job_id: str,
    ):
        super().__init__()

        self.videos = videos
        self.output_directory = output_directory
        self.job_id = job_id

        self.job_manager = JobManager()

        self._stop_requested = False

    def run(self):

        exporter = VideoExporter()

        exporter.progress.connect(
            self.progress.emit
        )

        exporter.error.connect(
            self.error.emit
        )

        for video in self.videos:

            if self._stop_requested:
                self.job_manager.update_job(
                    self.job_id,
                    status="stopped",
                )
                return

            # ------------------------------------------
            # Save current video
            # ------------------------------------------

            self.job_manager.update_job(
                self.job_id,
                status="processing",
                current_video=str(video),
            )

            # ------------------------------------------
            # Export
            # ------------------------------------------

            success = exporter.export_video(
                video,
                self.output_directory,
            )

            if not success:

                self.job_manager.update_job(
                    self.job_id,
                    status="stopped",
                    current_video=str(video),
                )

                return

            # ------------------------------------------
            # Video completed
            # ------------------------------------------

            job = self.job_manager.load_job(
                self.job_id
            )

            completed_videos = []

            if job:

                completed_videos = job.get(
                    "completed_videos",
                    [],
                )

            video_string = str(video)

            if video_string not in completed_videos:

                completed_videos.append(
                    video_string
                )

            self.job_manager.update_job(
                self.job_id,
                status="processing",
                current_video=None,
                completed_videos=completed_videos,
            )

            self.video_finished.emit()

        # ----------------------------------------------
        # Entire job completed
        # ----------------------------------------------

        self.job_manager.complete_job(
            self.job_id
        )

        self.finished.emit()

    def stop(self):

        self._stop_requested = True