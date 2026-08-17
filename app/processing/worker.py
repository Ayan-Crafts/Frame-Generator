from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.processing.exporter import VideoExporter
from app.jobs.job_manager import JobManager


class ExportWorker(QThread):

    progress = Signal(dict)
    video_finished = Signal()
    finished = Signal()
    paused = Signal()
    stopped = Signal()
    cancelled = Signal()
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

        self._control_requested = False
        self._action = None

    # ==================================================
    # CONTROL
    # ==================================================

    def pause(self):

        if not self.isRunning():
            return

        self._action = "pause"
        self._control_requested = True

    def stop_keep(self):

        if not self.isRunning():
            return

        self._action = "stop_keep"
        self._control_requested = True

    def cancel_delete(self):

        if not self.isRunning():
            return

        self._action = "cancel_delete"
        self._control_requested = True

    # ==================================================
    # RUN
    # ==================================================

    def run(self):

        exporter = VideoExporter()

        exporter.progress.connect(
            self.progress.emit
        )

        exporter.error.connect(
            self.error.emit
        )

        for video in self.videos:

            # ------------------------------------------
            # Check whether control was requested
            # ------------------------------------------

            if self._control_requested:
                self._handle_control(video)
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

            result = exporter.export_video(
                video,
                self.output_directory,
                should_stop=lambda:
                    self._control_requested,
                get_action=lambda:
                    self._action,
            )

            # ------------------------------------------
            # Pause
            # ------------------------------------------

            if result == "paused":

                self.job_manager.update_job(
                    self.job_id,
                    status="paused",
                    current_video=str(video),
                )

                self.paused.emit()

                return

            # ------------------------------------------
            # Stop but preserve progress
            # ------------------------------------------

            if result == "stopped":

                self.job_manager.update_job(
                    self.job_id,
                    status="stopped",
                    current_video=str(video),
                )

                self.stopped.emit()

                return

            # ------------------------------------------
            # Cancel and delete
            # ------------------------------------------

            if result == "cancelled":

                self.job_manager.cancel_job(
                    self.job_id
                )

                self.cancelled.emit()

                return

            # ------------------------------------------
            # Export failed
            # ------------------------------------------

            if result is False:

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

    # ==================================================
    # CONTROL HANDLER
    # ==================================================

    def _handle_control(
        self,
        video: Path,
    ):

        if self._action == "pause":

            self.job_manager.update_job(
                self.job_id,
                status="paused",
                current_video=str(video),
            )

            self.paused.emit()

        elif self._action == "stop_keep":

            self.job_manager.update_job(
                self.job_id,
                status="stopped",
                current_video=str(video),
            )

            self.stopped.emit()

        elif self._action == "cancel_delete":

            self.job_manager.cancel_job(
                self.job_id
            )

            self.cancelled.emit()

    # ==================================================
    # CLEAR CONTROL
    # ==================================================

    def clear_control(self):

        self._control_requested = False
        self._action = None