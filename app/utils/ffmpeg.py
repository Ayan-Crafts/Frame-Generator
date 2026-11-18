"""FFmpeg / FFprobe discovery and capability probing.

Resolution order (first match wins):

1. ``TNP_FFMPEG`` / ``TNP_FFPROBE`` environment variables (explicit override).
2. A bundled copy shipped with the application:
   * frozen build: ``<install dir>/ffmpeg/`` or ``<bundle>/ffmpeg/``
   * source checkout: ``packaging/ffmpeg/`` (v1/v2.0 layout, still honoured)
3. The system ``PATH`` (e.g. Ubuntu's ``apt install ffmpeg``).

An executable merely existing is not trusted: :func:`probe_ffmpeg` runs it
and records the version and the hardware-acceleration features the build
actually contains.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.utils import proc
from app.utils.paths import app_base_dir

EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

# ``-fps_mode`` (used by the extraction pipeline) appeared in FFmpeg 5.1,
# which shipped libavcodec 59.37. Release strings are not always numeric
# (git builds print "N-1234-gabcdef"), so the library version is used.
MIN_LIBAVCODEC = (59, 37)
MIN_VERSION_TEXT = "5.1"


class FFmpegNotFoundError(FileNotFoundError):
    pass


def _candidate_directories() -> list[tuple[str, Path]]:
    dirs: list[tuple[str, Path]] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(("bundled", exe_dir / "ffmpeg"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(("bundled", Path(meipass) / "ffmpeg"))
    else:
        dirs.append(("bundled", app_base_dir() / "packaging" / "ffmpeg"))
    return dirs


def _find_tool(tool: str) -> tuple[str, str]:
    """Return ``(path, source)`` for ``ffmpeg`` or ``ffprobe``."""
    override = os.environ.get(f"TNP_{tool.upper()}")
    if override:
        if Path(override).is_file():
            return str(Path(override)), "override"
        raise FFmpegNotFoundError(
            f"TNP_{tool.upper()} is set to '{override}', but that file does not exist."
        )

    for source, directory in _candidate_directories():
        path = directory / f"{tool}{EXE_SUFFIX}"
        if path.is_file():
            return str(path), source

    found = shutil.which(tool)
    if found:
        return found, "system"

    raise FFmpegNotFoundError(missing_ffmpeg_message(tool))


def missing_ffmpeg_message(tool: str = "ffmpeg") -> str:
    if sys.platform == "win32":
        hint = (
            "Reinstall TrackNetV1 Dataset Prepper with the 'Bundled FFmpeg' "
            "component selected, or install FFmpeg (for example "
            "'winget install Gyan.FFmpeg') and make sure it is on PATH."
        )
    else:
        hint = "Install it with:  sudo apt install ffmpeg"
    return f"{tool} was not found.\n\n{hint}"


def get_ffmpeg_path() -> str:
    return _find_tool("ffmpeg")[0]


def get_ffprobe_path() -> str:
    return _find_tool("ffprobe")[0]


# ----------------------------------------------------------------------
# Capability probing
# ----------------------------------------------------------------------


@dataclass
class FFmpegInfo:
    ffmpeg_path: str
    ffprobe_path: str
    source: str
    version: str = "unknown"
    libavcodec: tuple[int, int] = (0, 0)
    hwaccels: list[str] = field(default_factory=list)
    cuvid_decoders: list[str] = field(default_factory=list)
    nvenc_encoders: list[str] = field(default_factory=list)
    has_mjpeg_encoder: bool = False
    has_hwdownload_filter: bool = False
    configuration: str = ""

    @property
    def version_ok(self) -> bool:
        return self.libavcodec >= MIN_LIBAVCODEC

    @property
    def cuda_hwaccel(self) -> bool:
        return "cuda" in self.hwaccels

    def usable_problems(self) -> list[str]:
        problems = []
        if not self.version_ok:
            problems.append(
                f"FFmpeg {self.version} is too old (libavcodec "
                f"{self.libavcodec[0]}.{self.libavcodec[1]}); version "
                f"{MIN_VERSION_TEXT} or newer is required."
            )
        if not self.has_mjpeg_encoder:
            problems.append("This FFmpeg build has no MJPEG (JPEG) encoder.")
        return problems

    def to_dict(self) -> dict:
        return {
            "ffmpeg_path": self.ffmpeg_path,
            "ffprobe_path": self.ffprobe_path,
            "source": self.source,
            "version": self.version,
            "libavcodec": f"{self.libavcodec[0]}.{self.libavcodec[1]}",
            "version_ok": self.version_ok,
            "hwaccels": self.hwaccels,
            "cuda_hwaccel": self.cuda_hwaccel,
            "cuvid_decoders": self.cuvid_decoders,
            "nvenc_encoders": self.nvenc_encoders,
            "has_mjpeg_encoder": self.has_mjpeg_encoder,
            "has_hwdownload_filter": self.has_hwdownload_filter,
        }


_probe_lock = threading.Lock()
_probe_cache: FFmpegInfo | None = None


def _parse_version(text: str) -> tuple[str, tuple[int, int], str]:
    version = "unknown"
    match = re.search(r"ffmpeg version (\S+)", text)
    if match:
        version = match.group(1)
    lib = (0, 0)
    match = re.search(r"libavcodec\s+(\d+)\.\s*(\d+)", text)
    if match:
        lib = (int(match.group(1)), int(match.group(2)))
    config = ""
    match = re.search(r"configuration:(.*)", text)
    if match:
        config = match.group(1).strip()
    return version, lib, config


def _list_names(output: str, pattern: str) -> list[str]:
    names = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(pattern, parts[1]):
            names.append(parts[1])
    return names


def probe_ffmpeg(refresh: bool = False) -> FFmpegInfo:
    """Locate FFmpeg and record what the build can actually do.

    Raises :class:`FFmpegNotFoundError` if FFmpeg/FFprobe are missing or
    cannot be executed.
    """
    global _probe_cache
    with _probe_lock:
        if _probe_cache is not None and not refresh:
            return _probe_cache

        ffmpeg, source = _find_tool("ffmpeg")
        ffprobe, _ = _find_tool("ffprobe")

        result = proc.run([ffmpeg, "-hide_banner", "-version"], timeout=15)
        if result is None or result.returncode != 0:
            raise FFmpegNotFoundError(
                f"FFmpeg was found at {ffmpeg} but could not be executed."
            )
        probe_check = proc.run([ffprobe, "-version"], timeout=15)
        if probe_check is None or probe_check.returncode != 0:
            raise FFmpegNotFoundError(
                f"FFprobe was found at {ffprobe} but could not be executed."
            )

        version, lib, config = _parse_version(result.stdout)
        info = FFmpegInfo(
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            source=source,
            version=version,
            libavcodec=lib,
            configuration=config,
        )

        hw = proc.run([ffmpeg, "-hide_banner", "-hwaccels"], timeout=15)
        if hw is not None and hw.returncode == 0:
            lines = [line.strip() for line in hw.stdout.splitlines()]
            info.hwaccels = [
                line for line in lines if line and not line.lower().startswith("hardware")
            ]

        dec = proc.run([ffmpeg, "-hide_banner", "-decoders"], timeout=15)
        if dec is not None and dec.returncode == 0:
            info.cuvid_decoders = _list_names(dec.stdout, r"\w+_cuvid")

        enc = proc.run([ffmpeg, "-hide_banner", "-encoders"], timeout=15)
        if enc is not None and enc.returncode == 0:
            info.nvenc_encoders = _list_names(enc.stdout, r"\w+_nvenc")
            info.has_mjpeg_encoder = bool(_list_names(enc.stdout, r"mjpeg"))

        flt = proc.run([ffmpeg, "-hide_banner", "-filters"], timeout=15)
        if flt is not None and flt.returncode == 0:
            info.has_hwdownload_filter = bool(_list_names(flt.stdout, r"hwdownload"))

        _probe_cache = info
        return info


_NOISE = ("frame=", "Conversion failed", "Terminating thread", "Task finished")
_CAUSE_HINTS = (
    "Cannot load", "not supported", "unsupported", "Invalid output format",
    "Impossible to convert", "No decoder", "CUDA_ERROR", "No device", "Invalid data",
    "Invalid pts", "Error", "error", "failed", "Failed",
)
_LOG_PREFIX = re.compile(r"^\[[^\]]+ @ [0-9a-fA-Fx]+\]\s*")


def failure_reason(stderr: str) -> str:
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


def nvdec_hint(stderr: str) -> str:
    """Actionable advice for the most common NVDEC set-up failures."""
    text = stderr or ""
    if "nvcuvid" in text:
        if sys.platform.startswith("linux"):
            return (
                "The NVIDIA video decode library (libnvcuvid) is missing. Native "
                "Ubuntu: install the matching libnvidia-decode-<driver> package "
                "(included with nvidia-driver-<version>). Docker: run with "
                "--gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video."
            )
        return "The NVIDIA video decode library (nvcuvid.dll) is missing; reinstall/update the NVIDIA driver."
    if "libcuda" in text or "nvcuda" in text or "CUDA_ERROR_NO_DEVICE" in text:
        return "The CUDA driver library could not be used; update the NVIDIA driver."
    if "CUDA_ERROR_UNSUPPORTED_PTX_VERSION" in text or "too old" in text:
        return "The NVIDIA driver is too old for this FFmpeg build; update the driver."
    return ""


def reset_probe_cache() -> None:
    global _probe_cache
    with _probe_lock:
        _probe_cache = None
