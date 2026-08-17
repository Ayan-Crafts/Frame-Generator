import subprocess
import re
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class VideoExporter(QObject):

    progress = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()

    def export_video(
        self,
        video_path: Path,
        output_root: Path,
    ):
        try:
            video_name = video_path.stem
            output_directory = output_root / video_name

            output_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_pattern = (
                output_directory / "%06d.jpg"
            )

            command = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-hwaccel",
                "cuda",
                "-hwaccel_output_format",
                "cuda",
                "-i",
                str(video_path),
                "-map",
                "0:v:0",
                "-fps_mode",
                "passthrough",
                "-vf",
                "hwdownload,format=nv12",
                "-q:v",
                "2",
                "-start_number",
                "1",
                str(output_pattern),
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            while True:
                line = process.stderr.readline()

                if not line and process.poll() is not None:
                    break

                if line:
                    self._parse_progress(
                        line,
                        video_path,
                    )

            return_code = process.wait()

            if return_code != 0:
                self.error.emit(
                    f"Failed to export: {video_path.name}"
                )
                return

            self.finished.emit()

        except Exception as exc:
            self.error.emit(str(exc))

    def _parse_progress(
        self,
        line: str,
        video_path: Path,
    ):
        match = re.search(
            r"frame=\s*(\d+).*?"
            r"fps=\s*([\d.]+).*?"
            r"time=([\d:.]+).*?"
            r"speed=([\d.]+)x",
            line,
        )

        if not match:
            return

        frames = int(match.group(1))
        fps = float(match.group(2))
        speed = float(match.group(4))

        self.progress.emit({
            "video": video_path.name,
            "frames": frames,
            "fps": fps,
            "speed": speed,
        })