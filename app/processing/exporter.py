import json
import subprocess
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.processing.resume import ResumeManager
from app.processing.resource_manager import ResourceManager


class VideoExporter(QObject):

    progress = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()

        self.resume_manager = ResumeManager()
        self.resource_manager = ResourceManager()

    def get_video_info(self, video_path: Path):

        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream="
            "r_frame_rate,"
            "avg_frame_rate,"
            "nb_frames,"
            "duration",
            "-of",
            "json",
            str(video_path),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)
        stream = data["streams"][0]

        fps_text = (
            stream.get("avg_frame_rate")
            or stream.get("r_frame_rate")
        )

        fps = float(Fraction(fps_text))

        nb_frames = stream.get("nb_frames")

        if nb_frames:
            total_frames = int(nb_frames)
        else:
            duration = float(
                stream.get("duration", 0)
            )
            total_frames = round(
                duration * fps
            )

        return {
            "fps": fps,
            "total_frames": total_frames,
        }

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

            # ------------------------------------------
            # Source information
            # ------------------------------------------

            video_info = self.get_video_info(
                video_path
            )

            fps = video_info["fps"]
            total_frames = video_info[
                "total_frames"
            ]

            # ------------------------------------------
            # Existing frames
            # ------------------------------------------

            resume_info = (
                self.resume_manager.inspect(
                    output_directory
                )
            )

            if resume_info.completed:

                self.progress.emit({
                    "video": video_path.name,
                    "frames": total_frames,
                    "fps": 0,
                    "speed": 0,
                    "time": "complete",
                    "status": "skipped",
                })

                return True

            existing_frames = (
                resume_info.existing_frames
            )

            resume_frame = (
                existing_frames + 1
            )

            # ------------------------------------------
            # Already complete
            # ------------------------------------------

            if existing_frames >= total_frames:

                self.resume_manager.mark_complete(
                    output_directory
                )

                self.progress.emit({
                    "video": video_path.name,
                    "frames": total_frames,
                    "fps": 0,
                    "speed": 0,
                    "time": "complete",
                    "status": "completed",
                })

                return True

            remaining_frames = (
                total_frames -
                existing_frames
            )

            # ------------------------------------------
            # Safe seek
            # ------------------------------------------

            target_time = (
                (resume_frame - 1) / fps
            )

            # Seek backwards so FFmpeg lands on
            # a safe keyframe before the target.
            seek_time = max(
                0.0,
                target_time - 5.0,
            )

            # Number of frames to discard after
            # the seek point.
            discard_frames = round(
                (target_time - seek_time) * fps
            )

            # ------------------------------------------
            # Resources
            # ------------------------------------------

            resource_profile = (
                self.resource_manager
                .get_profile()
            )

            threads = resource_profile[
                "ffmpeg_threads"
            ]

            output_pattern = (
                output_directory /
                "%06d.jpg"
            )

            # FFmpeg will decode from the safe seek
            # point, discard exactly the frames before
            # the requested source frame, then write
            # only the remaining frames.
            filter_expression = (
                "hwdownload,"
                "format=nv12,"
                f"select='gte(n,{discard_frames})'"
            )
            self.progress.emit({
                "video": video_path.name,
                "frames": existing_frames,
                "fps": 0,
                "speed": 0,
                "time": "starting",
                "status": "processing",
                "resources": resource_profile,
                "total_frames": total_frames,
            })

            command = [

                "ffmpeg",

                "-hide_banner",

                "-ss",
                str(seek_time),

                "-hwaccel",
                "cuda",

                "-hwaccel_output_format",
                "cuda",

                "-i",
                str(video_path),

                "-map",
                "0:v:0",

                "-vf",
                filter_expression,

                "-frames:v",
                str(remaining_frames),

                "-fps_mode",
                "passthrough",

                "-q:v",
                "2",

                "-threads",
                str(threads),

                "-start_number",
                str(resume_frame),

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
                        resume_frame,
                        total_frames,
                    )

                    progress_data = {}

            stderr = process.stderr.read()

            return_code = process.wait()

            # ------------------------------------------
            # FFmpeg failure
            # ------------------------------------------

            if return_code != 0:

                self.error.emit(
                    f"FFmpeg failed for "
                    f"{video_path.name}\n\n"
                    f"{stderr}"
                )

                return False

            # ------------------------------------------
            # Final validation
            # ------------------------------------------

            final_info = (
                self.resume_manager.inspect(
                    output_directory
                )
            )

            final_frames = (
                final_info.existing_frames
            )

            if final_frames != total_frames:

                self.resume_manager.remove_complete_marker(
                    output_directory
                )

                self.error.emit(
                    f"Incomplete export for "
                    f"{video_path.name}\n"
                    f"Expected: {total_frames}\n"
                    f"Found: {final_frames}"
                )

                return False

            # ------------------------------------------
            # Successful completion
            # ------------------------------------------

            self.resume_manager.mark_complete(
                output_directory
            )

            self.progress.emit({
                "video": video_path.name,
                "frames": final_frames,
                "fps": 0,
                "speed": 0,
                "time": "complete",
                "status": "completed",
            })

            return True

        except Exception as exc:

            self.error.emit(
                str(exc)
            )

            return False

    def _emit_progress(
        self,
        video_path: Path,
        data: dict,
        resume_frame: int,
        total_frames: int,
    ):

        try:

            frame = int(
                data.get(
                    "frame",
                    resume_frame,
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

            speed = float(speed_text)

            out_time = data.get(
                "out_time",
                "00:00:00.000000",
            )

            self.progress.emit({
                "video": video_path.name,
                "frames": frame,
                "fps": fps,
                "speed": speed,
                "time": out_time,
                "resume_frame": resume_frame,
                "total_frames": total_frames,
                "status": "processing",
            })

        except (
            ValueError,
            TypeError,
        ):
            pass