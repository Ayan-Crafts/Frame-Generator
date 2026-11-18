"""Video → JPEG frame extraction.

Pipelines (see docs/ARCHITECTURE.md):

* **GPU**: ``-hwaccel cuda -hwaccel_output_format cuda`` decodes on NVDEC,
  ``hwdownload,format=nv12`` copies frames to system memory, and the MJPEG
  encoder writes JPEGs on the CPU. Only *decoding* is GPU accelerated.
* **CPU**: software decode + MJPEG encode.

Modes: ``auto`` uses the GPU pipeline when NVDEC was verified at startup and
falls back to CPU per video if NVDEC rejects a stream (e.g. a codec or
bit depth the GPU generation does not support); ``gpu`` forces the GPU
pipeline (no fallback); ``cpu`` never touches the GPU.

Output layout is unchanged from v1/v2.0: ``<output>/<name>/%06d.jpg``
numbered from 1, plus a ``.complete`` marker when finished.

This module has no Qt dependency; the GUI worker and the CLI pass callbacks.
"""

from __future__ import annotations

import collections
import json
import math
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from app.hardware.capabilities import PIPELINE_CPU, PIPELINE_GPU
from app.processing.resource_manager import ResourceManager, free_space_gb
from app.processing.resume import ResumeManager
from app.utils import proc
from app.utils.ffmpeg import get_ffmpeg_path, get_ffprobe_path
from app.utils.logging_setup import get_logger

log = get_logger("exporter")

MODES = ("auto", "gpu", "cpu")

# Refuse to start / keep writing below this much free space.
MIN_FREE_GB = 0.5
# Rough JPEG (q:v 2) size per pixel, used only for the up-front disk warning.
EST_JPEG_BYTES_PER_PIXEL = 0.2

# Accept a small difference between the container's frame count and the
# number of frames FFmpeg can actually decode (edit lists, a dropped final
# frame, duration-based estimates for MKV/WebM).
EXACT_COUNT_TOLERANCE = (2, 0.005)      # frames, fraction
ESTIMATED_COUNT_TOLERANCE = (3, 0.02)


class VideoProbeError(Exception):
    """The input could not be read as a video."""


@dataclass
class VideoInfo:
    fps: float
    total_frames: int
    frame_count_exact: bool
    codec: str = ""
    width: int = 0
    height: int = 0
    pix_fmt: str = ""
    duration: float = 0.0


def _parse_rate(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        value = float(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return 0.0
    return value if math.isfinite(value) and value > 0 else 0.0


def _parse_float(text) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) and value > 0 else 0.0


_NOISE = ("frame=", "Conversion failed", "Terminating thread", "Task finished")
_CAUSE_HINTS = (
    "not supported", "unsupported", "Invalid output format", "Impossible to convert",
    "No decoder", "Cannot load", "CUDA_ERROR", "No device", "Invalid data",
    "Error", "error", "failed", "Failed",
)
_LOG_PREFIX = re.compile(r"^\[[^\]]+ @ [0-9a-fA-Fx]+\]\s*")


def _failure_reason(stderr: str) -> str:
    """Pick the line that explains an FFmpeg failure (not its final stats line)."""
    lines = [
        _LOG_PREFIX.sub("", line.strip())
        for line in (stderr or "").splitlines()
        if line.strip() and not any(noise in line for noise in _NOISE)
    ]
    for hint in _CAUSE_HINTS:
        for line in lines:
            if hint in line:
                return line[:200]
    return lines[-1][:200] if lines else "unknown error"


def _tail(text: str, lines: int = 6) -> str:
    content = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(content[-lines:])


class VideoExporter:

    def __init__(
        self,
        mode: str = "auto",
        gpu_ready: bool = False,
        on_progress: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_warning: Callable[[str], None] | None = None,
    ):
        if mode not in MODES:
            raise ValueError(f"Unknown acceleration mode: {mode}")

        self.mode = mode
        self.gpu_ready = gpu_ready
        self._on_progress = on_progress or (lambda data: None)
        self._on_error = on_error or (lambda message: None)
        self._on_warning = on_warning or (lambda message: None)

        self.resume_manager = ResumeManager()
        self.resource_manager = ResourceManager()

        # Set by the last export_video() call; read by callers for reporting.
        self.last_pipeline: str | None = None
        self.last_fallback_reason: str | None = None

    # ==================================================
    # CALLBACK HELPERS
    # ==================================================

    def _progress(self, data: dict):
        try:
            self._on_progress(data)
        except Exception:  # never let a UI callback break the export
            log.exception("progress callback failed")

    def _error(self, message: str):
        log.error(message)
        try:
            self._on_error(message)
        except Exception:
            log.exception("error callback failed")

    def _warning(self, message: str):
        log.warning(message)
        try:
            self._on_warning(message)
        except Exception:
            log.exception("warning callback failed")

    # ==================================================
    # VIDEO INFORMATION
    # ==================================================

    def get_video_info(self, video_path: Path) -> VideoInfo:

        if not video_path.is_file():
            raise VideoProbeError(f"File not found: {video_path}")

        if video_path.stat().st_size == 0:
            raise VideoProbeError("The file is empty (0 bytes).")

        command = [
            get_ffprobe_path(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,r_frame_rate,"
            "avg_frame_rate,nb_frames,duration:format=duration",
            "-of", "json",
            str(video_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=60,
                **proc.popen_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoProbeError("FFprobe timed out reading the file.") from exc

        if result.returncode != 0:
            detail = _tail(result.stderr, 2) or f"exit code {result.returncode}"
            raise VideoProbeError(
                "The file could not be read as a video; it may be corrupted, "
                f"incomplete or in an unsupported format.\nFFprobe: {detail}"
            )

        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise VideoProbeError("FFprobe returned unreadable output.") from exc

        streams = data.get("streams") or []
        if not streams:
            raise VideoProbeError(
                "No video stream found (the file may be audio-only or not a video)."
            )

        stream = streams[0]

        fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(
            stream.get("r_frame_rate")
        )
        if fps <= 0:
            raise VideoProbeError("Could not determine the video frame rate.")

        nb_frames = 0
        try:
            nb_frames = int(stream.get("nb_frames") or 0)
        except (TypeError, ValueError):
            nb_frames = 0

        # MKV/WebM usually carry neither nb_frames nor a stream duration;
        # the container (format) duration is the fallback. v2.0 used 0 here
        # and then marked such videos "complete" with zero frames.
        duration = _parse_float(stream.get("duration")) or _parse_float(
            (data.get("format") or {}).get("duration")
        )

        if nb_frames > 0:
            total_frames = nb_frames
            exact = True
        elif duration > 0:
            total_frames = max(1, round(duration * fps))
            exact = False
        else:
            raise VideoProbeError(
                "Could not determine the number of frames or the duration of the video."
            )

        return VideoInfo(
            fps=fps,
            total_frames=total_frames,
            frame_count_exact=exact,
            codec=stream.get("codec_name", ""),
            width=int(stream.get("width") or 0),
            height=int(stream.get("height") or 0),
            pix_fmt=stream.get("pix_fmt", ""),
            duration=duration,
        )

    # ==================================================
    # PIPELINE SELECTION
    # ==================================================

    def _use_gpu_first(self) -> bool:
        if self.mode == "cpu":
            return False
        if self.mode == "gpu":
            return True
        return self.gpu_ready

    def _build_command(
        self,
        video_path: Path,
        output_pattern: Path,
        use_gpu: bool,
        seek_time: float,
        discard_frames: int,
        frame_limit: int | None,
        threads: int,
        start_number: int,
    ) -> list[str]:

        filters = []
        if use_gpu:
            filters += ["hwdownload", "format=nv12"]
        if discard_frames > 0:
            filters.append(f"select='gte(n,{discard_frames})'")

        command = [get_ffmpeg_path(), "-hide_banner"]

        if seek_time > 0:
            command += ["-ss", f"{seek_time:.6f}"]

        if use_gpu:
            command += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]

        command += ["-i", str(video_path), "-map", "0:v:0"]

        if filters:
            command += ["-vf", ",".join(filters)]

        if frame_limit is not None:
            command += ["-frames:v", str(frame_limit)]

        command += [
            "-fps_mode", "passthrough",
            "-q:v", "2",
            "-threads", str(threads),
            "-start_number", str(start_number),
            "-progress", "pipe:1",
            "-nostats",
            str(output_pattern),
        ]
        return command

    # ==================================================
    # EXPORT VIDEO
    # ==================================================

    def export_video(
        self,
        video_path: Path,
        output_root: Path,
        should_stop=None,
        get_action=None,
        output_name: str | None = None,
    ):
        """Extract one video.

        Returns ``True`` (complete), ``False`` (failed), or ``"paused"`` /
        ``"stopped"`` / ``"cancelled"`` when a control request interrupted it.
        """

        self.last_pipeline = None
        self.last_fallback_reason = None

        try:
            output_directory = output_root / (output_name or video_path.stem)

            info = self.get_video_info(video_path)

            output_directory.mkdir(parents=True, exist_ok=True)

            use_gpu = self._use_gpu_first()

            while True:
                outcome = self._run_once(
                    video_path,
                    output_directory,
                    info,
                    use_gpu,
                    should_stop,
                    get_action,
                )

                if outcome == "gpu_failed" and self.mode == "auto":
                    # NVDEC rejected this stream; resume on the CPU from the
                    # last good frame.
                    self._warning(
                        f"{video_path.name}: GPU decoding failed "
                        f"({self.last_fallback_reason}); continuing on CPU."
                    )
                    use_gpu = False
                    continue

                if outcome == "gpu_failed":
                    self._error(
                        f"GPU decoding failed for {video_path.name} and GPU mode "
                        f"was forced.\n\n{self.last_fallback_reason}\n\n"
                        "Switch acceleration to Auto or CPU to process this file."
                    )
                    return False

                return outcome

        except VideoProbeError as exc:
            self._error(f"Skipped {video_path.name}:\n{exc}")
            return False

        except FileNotFoundError as exc:
            self._error(str(exc))
            return False

        except PermissionError as exc:
            self._error(
                f"Permission denied while processing {video_path.name}:\n{exc}\n\n"
                "Choose an output folder you can write to."
            )
            return False

        except Exception as exc:  # last resort: report, never crash the app
            log.exception("Unexpected export failure for %s", video_path)
            self._error(f"Unexpected error while processing {video_path.name}:\n{exc}")
            return False

    def _run_once(
        self,
        video_path: Path,
        output_directory: Path,
        info: VideoInfo,
        use_gpu: bool,
        should_stop,
        get_action,
    ):
        fps = info.fps
        total_frames = info.total_frames
        pipeline = PIPELINE_GPU if use_gpu else PIPELINE_CPU
        self.last_pipeline = pipeline

        # ------------------------------------------
        # Existing output / resume information
        # ------------------------------------------

        resume_info = self.resume_manager.inspect(output_directory)

        if resume_info.completed:
            self._progress({
                "video": video_path.name,
                "frames": total_frames,
                "fps": 0,
                "speed": 0,
                "time": "complete",
                "status": "skipped",
                "total_frames": total_frames,
                "pipeline": "already complete",
            })
            return True

        existing_frames = resume_info.existing_frames
        resume_frame = existing_frames + 1

        if info.frame_count_exact and existing_frames >= total_frames:
            self.resume_manager.mark_complete(output_directory)
            self._progress({
                "video": video_path.name,
                "frames": existing_frames,
                "fps": 0,
                "speed": 0,
                "time": "complete",
                "status": "completed",
                "total_frames": total_frames,
                "pipeline": "already complete",
            })
            return True

        # ------------------------------------------
        # Disk space
        # ------------------------------------------

        free_gb = free_space_gb(output_directory)
        if free_gb < MIN_FREE_GB:
            self._error(
                f"Not enough disk space to export {video_path.name}: only "
                f"{free_gb:.2f} GB free on the output drive.\n\n"
                "Free some space or choose another output folder; progress "
                "so far has been kept."
            )
            return False

        remaining_estimate = max(0, total_frames - existing_frames)
        if info.width and info.height:
            needed_gb = (
                remaining_estimate * info.width * info.height
                * EST_JPEG_BYTES_PER_PIXEL / (1024 ** 3)
            )
            if needed_gb > free_gb:
                self._warning(
                    f"{video_path.name}: roughly {needed_gb:.1f} GB may be needed "
                    f"but only {free_gb:.1f} GB is free. Export will stop safely "
                    "if the disk fills up."
                )

        # ------------------------------------------
        # Resume position
        # ------------------------------------------

        target_time = (resume_frame - 1) / fps

        # Seek backwards to a safe keyframe, then drop decoded frames
        # until the resume frame.
        seek_time = max(0.0, target_time - 5.0)
        discard_frames = round((target_time - seek_time) * fps)

        # For an exact container count, stop after exactly the missing
        # frames. For an estimated count (MKV/WebM), decode to EOF so a
        # low estimate cannot truncate the video.
        frame_limit = (
            max(0, total_frames - existing_frames)
            if info.frame_count_exact
            else None
        )

        resource_profile = self.resource_manager.get_profile(output_directory)
        threads = resource_profile["ffmpeg_threads"]

        self._progress({
            "video": video_path.name,
            "frames": existing_frames,
            "fps": 0,
            "speed": 0,
            "time": "starting",
            "status": "processing",
            "resume_frame": resume_frame,
            "total_frames": total_frames,
            "resources": resource_profile,
            "pipeline": pipeline,
        })

        output_pattern = output_directory / "%06d.jpg"

        command = self._build_command(
            video_path,
            output_pattern,
            use_gpu,
            seek_time,
            discard_frames,
            frame_limit,
            threads,
            resume_frame,
        )

        log.info(
            "Exporting %s | pipeline=%s | resume_frame=%d | seek=%.3f discard=%d limit=%s",
            video_path.name, pipeline, resume_frame, seek_time, discard_frames, frame_limit,
        )
        log.debug("Command: %s", command)

        started = time.monotonic()
        result = self._run_ffmpeg(
            command,
            video_path,
            existing_frames,
            total_frames,
            resource_profile,
            pipeline,
            output_directory,
            should_stop,
            get_action,
        )
        status = result["status"]

        if status in ("paused", "stopped", "cancelled"):
            if status == "cancelled":
                shutil.rmtree(output_directory, ignore_errors=True)
            return status

        if status == "disk_full":
            self._error(
                f"Export of {video_path.name} was stopped because the output "
                "drive is almost full. Frames written so far were kept; free "
                "some space and resume."
            )
            return False

        return_code = result["return_code"]
        stderr = result["stderr"]
        written_this_run = result["frames_written"]

        # ------------------------------------------
        # FFmpeg failure
        # ------------------------------------------

        if return_code != 0:
            if use_gpu and written_this_run == 0:
                self.last_fallback_reason = _failure_reason(stderr)
                return "gpu_failed"

            if use_gpu and self.mode == "auto":
                # Failed part-way: let resume validation trim the partial
                # tail and finish on the CPU.
                self.last_fallback_reason = _failure_reason(stderr)
                return "gpu_failed"

            self._error(
                f"FFmpeg failed for {video_path.name} (exit code {return_code}).\n\n"
                f"{_tail(stderr)}"
            )
            return False

        # ------------------------------------------
        # Validate output
        # ------------------------------------------

        final_frames = self.resume_manager.inspect(output_directory).existing_frames

        reached_eof = frame_limit is None or written_this_run < frame_limit
        difference = abs(final_frames - total_frames)

        frames_tol, ratio_tol = (
            EXACT_COUNT_TOLERANCE if info.frame_count_exact else ESTIMATED_COUNT_TOLERANCE
        )
        within_tolerance = difference <= max(frames_tol, total_frames * ratio_tol)

        if final_frames == 0:
            self.resume_manager.remove_complete_marker(output_directory)
            self._error(
                f"No frames could be decoded from {video_path.name}. The file "
                "may be corrupted or use an unsupported codec.\n\n"
                f"{_tail(stderr)}"
            )
            return False

        if difference and not (reached_eof and within_tolerance):
            self.resume_manager.remove_complete_marker(output_directory)
            self._error(
                f"Incomplete export for {video_path.name}\n"
                f"Expected: {total_frames}\n"
                f"Found: {final_frames}\n\n"
                "The file appears truncated or partly corrupted. The frames "
                "that could be decoded were kept and the video was not marked "
                "complete."
            )
            return False

        if difference:
            kind = "reports" if info.frame_count_exact else "was estimated at"
            self._warning(
                f"{video_path.name}: the container {kind} {total_frames} frames; "
                f"{final_frames} were decodable and extracted."
            )

        self.resume_manager.mark_complete(output_directory)

        elapsed = time.monotonic() - started
        log.info(
            "Completed %s: %d frames in %.2fs (%.1f fps) via %s",
            video_path.name,
            final_frames,
            elapsed,
            written_this_run / elapsed if elapsed > 0 else 0.0,
            pipeline,
        )

        self._progress({
            "video": video_path.name,
            "frames": final_frames,
            "fps": 0,
            "speed": 0,
            "time": "complete",
            "status": "completed",
            "total_frames": final_frames,
            "pipeline": pipeline,
        })

        return True

    # ==================================================
    # FFMPEG PROCESS
    # ==================================================

    def _run_ffmpeg(
        self,
        command,
        video_path,
        existing_frames,
        total_frames,
        resource_profile,
        pipeline,
        output_directory,
        should_stop,
        get_action,
    ) -> dict:

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            **proc.popen_kwargs(),
        )

        # stdout carries "-progress" key=value lines; stderr carries
        # warnings/errors. Both are drained on background threads: v2.0 only
        # read stdout, so a chatty stderr (a damaged file logs one line per
        # bad packet) could fill the pipe and deadlock FFmpeg.
        lines: queue.Queue = queue.Queue()
        stderr_tail: collections.deque = collections.deque(maxlen=200)

        def pump_stdout():
            try:
                for line in process.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        def pump_stderr():
            for line in process.stderr:
                stderr_tail.append(line.rstrip())

        threading.Thread(target=pump_stdout, daemon=True, name="ffmpeg-stdout").start()
        stderr_thread = threading.Thread(target=pump_stderr, daemon=True, name="ffmpeg-stderr")
        stderr_thread.start()

        progress_data: dict = {}
        frames_written = 0
        last_disk_check = time.monotonic()
        control_status = None

        while True:

            if should_stop and should_stop():
                action = get_action() if get_action else "pause"
                self._stop_process(process)
                control_status = {
                    "cancel_delete": "cancelled",
                    "stop_keep": "stopped",
                }.get(action, "paused")
                break

            now = time.monotonic()
            if now - last_disk_check > 2.0:
                last_disk_check = now
                if free_space_gb(output_directory) < MIN_FREE_GB / 2:
                    self._stop_process(process)
                    control_status = "disk_full"
                    break

            try:
                line = lines.get(timeout=0.25)
            except queue.Empty:
                continue

            if line is None:
                break

            line = line.strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            progress_data[key] = value

            if key == "progress":
                try:
                    frames_written = int(progress_data.get("frame", frames_written))
                except ValueError:
                    pass
                self._emit_progress(
                    video_path,
                    progress_data,
                    existing_frames,
                    total_frames,
                    resource_profile,
                    pipeline,
                )
                progress_data = {}

        return_code = process.wait()
        stderr_thread.join(timeout=5)

        return {
            "status": control_status or "finished",
            "return_code": return_code,
            "stderr": "\n".join(stderr_tail),
            "frames_written": frames_written,
        }

    @staticmethod
    def _stop_process(process: subprocess.Popen):
        """Ask FFmpeg to finish the current frame and exit; escalate if needed."""
        try:
            if process.stdin:
                process.stdin.write("q\n")
                process.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    # ==================================================
    # PROGRESS
    # ==================================================

    def _emit_progress(
        self,
        video_path: Path,
        data: dict,
        existing_frames: int,
        total_frames: int,
        resource_profile: dict,
        pipeline: str,
    ):

        def number(key):
            text = str(data.get(key, "0")).strip().rstrip("x")
            try:
                value = float(text)
            except ValueError:
                return 0.0
            return value if math.isfinite(value) else 0.0

        # FFmpeg's frame counter restarts at 0 for each run; add the frames
        # that already existed so a resumed export shows absolute progress.
        frame = existing_frames + int(number("frame"))

        self._progress({
            "video": video_path.name,
            "frames": frame,
            "fps": number("fps"),
            "speed": number("speed"),
            "time": data.get("out_time", "00:00:00.000000"),
            "resume_frame": existing_frames + 1,
            "total_frames": total_frames,
            "status": "processing",
            "resources": resource_profile,
            "pipeline": pipeline,
        })
