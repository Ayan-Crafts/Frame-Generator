from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.hardware.capabilities import get_report
from app.jobs.job_manager import JobManager
from app.processing.exporter import VideoExporter
from app.processing.scanner import output_names
from app.utils.logging_setup import get_logger

log = get_logger("worker")


class ExportWorker(QThread):
    """Runs a batch export off the GUI thread.

    Signals are named ``job_*`` / ``video_*`` deliberately: v2.0 declared
    ``finished = Signal()``, which shadows ``QThread.finished`` (the signal
    Qt emits when the thread has *actually* stopped). Lifetime handling in
    the window relies on the real ``QThread.finished``.
    """

    progress = Signal(dict)
    video_finished = Signal()
    video_failed = Signal(str, str)        # video name, message
    warning = Signal(str)
    job_finished = Signal(dict)            # summary
    paused = Signal()
    stopped = Signal()
    cancelled = Signal()
    error = Signal(str)                    # fatal for the whole job

    def __init__(
        self,
        videos: list[Path],
        output_directory: Path,
        job_id: str,
        acceleration_mode: str = "auto",
    ):
        super().__init__()

        self.videos = videos
        self.output_directory = output_directory
        self.job_id = job_id
        self.acceleration_mode = acceleration_mode

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
        try:
            self._run()
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Export worker crashed")
            self.error.emit(f"The export stopped unexpectedly:\n{exc}")

    def _run(self):

        gpu_ready = False
        if self.acceleration_mode != "cpu":
            # Cached after the first call (startup probe usually ran already).
            gpu_ready = get_report().gpu_pipeline_ready

        current_failure = {}

        def on_error(message):
            current_failure["message"] = message

        exporter = VideoExporter(
            mode=self.acceleration_mode,
            gpu_ready=gpu_ready,
            on_progress=self.progress.emit,
            on_error=on_error,
            on_warning=self.warning.emit,
        )

        names = output_names(self.videos)

        job = self.job_manager.load_job(self.job_id) or {}
        completed_videos = list(job.get("completed_videos", []))
        failed_videos = {}
        warnings = []
        self.warning.connect(warnings.append)

        for video in self.videos:

            if self._control_requested:
                self._handle_control(video)
                return

            self.job_manager.update_job(
                self.job_id,
                status="processing",
                current_video=str(video),
            )

            current_failure.clear()

            result = exporter.export_video(
                video,
                self.output_directory,
                should_stop=lambda: self._control_requested,
                get_action=lambda: self._action,
                output_name=names.get(video),
            )

            if result == "paused":
                self.job_manager.update_job(
                    self.job_id, status="paused", current_video=str(video)
                )
                self.paused.emit()
                return

            if result == "stopped":
                self.job_manager.update_job(
                    self.job_id, status="stopped", current_video=str(video)
                )
                self.stopped.emit()
                return

            if result == "cancelled":
                self.job_manager.cancel_job(self.job_id)
                self.cancelled.emit()
                return

            if result is False:
                # One bad file must not end the whole batch (v2.0 stopped
                # here without emitting any terminal signal).
                message = current_failure.get("message", "Unknown error")
                failed_videos[str(video)] = message
                self.job_manager.update_job(
                    self.job_id,
                    current_video=None,
                    failed_videos=failed_videos,
                )
                self.video_failed.emit(video.name, message)
                continue

            video_string = str(video)
            if video_string not in completed_videos:
                completed_videos.append(video_string)

            self.job_manager.update_job(
                self.job_id,
                status="processing",
                current_video=None,
                completed_videos=completed_videos,
                last_pipeline=exporter.last_pipeline,
            )

            self.video_finished.emit()

        summary = {
            "total": len(self.videos),
            "completed": len(self.videos) - len(failed_videos),
            "failed": failed_videos,
            "warnings": warnings,
        }

        if failed_videos:
            self.job_manager.update_job(
                self.job_id,
                status="completed_with_errors",
                current_video=None,
                failed_videos=failed_videos,
            )
        else:
            self.job_manager.complete_job(self.job_id)

        self.job_finished.emit(summary)

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
