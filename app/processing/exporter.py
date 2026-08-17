import subprocess
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

            output_directory = (
                output_root / video_name
            )

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

                "-progress",
                "pipe:1",

                "-nostats",

                str(output_pattern),
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            progress_data = {}

            while True:

                line = process.stdout.readline()

                if not line:
                    if process.poll() is not None:
                        break

                    continue

                line = line.strip()

                if "=" not in line:
                    continue

                key, value = line.split(
                    "=",
                    1,
                )

                progress_data[key] = value

                if key == "progress":

                    self._emit_progress(
                        video_path,
                        progress_data,
                    )

                    progress_data = {}

            stderr = process.stderr.read()

            return_code = process.wait()

            if return_code != 0:

                self.error.emit(
                    f"Failed to export "
                    f"{video_path.name}\n"
                    f"{stderr}"
                )

                return

            self.finished.emit()

        except Exception as exc:

            self.error.emit(
                str(exc)
            )

    def _emit_progress(
        self,
        video_path: Path,
        data: dict,
    ):

        try:

            frame = int(
                data.get(
                    "frame",
                    0,
                )
            )

            fps = float(
                data.get(
                    "fps",
                    0,
                )
            )

            speed_text = data.get(
                "speed",
                "0x",
            )

            if speed_text.endswith("x"):
                speed_text = speed_text[:-1]

            speed = float(
                speed_text
            )

            out_time = data.get(
                "out_time",
                "00:00:00.000000",
            )

            self.progress.emit(
                {
                    "video": video_path.name,
                    "frames": frame,
                    "fps": fps,
                    "speed": speed,
                    "time": out_time,
                }
            )

        except (
            ValueError,
            TypeError,
        ):
            return