"""System and acceleration capability report.

The report deliberately separates layers that are often conflated:

* **GPU detected**   - ``nvidia-smi`` lists an NVIDIA GPU.
* **Driver present** - the driver answered and reported a version.
* **FFmpeg support** - the FFmpeg build lists the ``cuda`` hwaccel.
* **NVDEC verified** - the *exact* decode pipeline used for frame extraction
  (``-hwaccel cuda -hwaccel_output_format cuda`` + ``hwdownload``) was run
  on a bundled H.264 clip and succeeded.
* **NVENC verified** - an H.264 NVENC encode of a test pattern succeeded.
  Reported for completeness only: frame extraction writes JPEGs and never
  uses NVENC.

GPU extraction is only offered in *Auto* mode when NVDEC is verified, so
the UI never claims acceleration that the pipeline cannot deliver.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

from app.utils import proc
from app.utils.ffmpeg import (
    FFmpegInfo,
    FFmpegNotFoundError,
    failure_reason,
    nvdec_hint,
    probe_ffmpeg,
)
from app.utils.logging_setup import get_logger
from app.utils.paths import resource_path

log = get_logger("capabilities")

# Pipeline stage descriptions shown in the UI and logs.
PIPELINE_GPU = "GPU decode (NVDEC) → CPU JPEG encode"
PIPELINE_CPU = "CPU decode → CPU JPEG encode"


@dataclass
class NvidiaGPU:
    index: int
    name: str
    memory_total_mb: int | None
    memory_free_mb: int | None
    driver_version: str | None
    compute_capability: str | None


@dataclass
class AccelerationReport:
    os_name: str = ""
    os_version: str = ""
    architecture: str = ""
    cpu_threads: int = 0
    ram_total_gb: float = 0.0

    ffmpeg: dict | None = None
    ffmpeg_error: str | None = None
    ffmpeg_problems: list[str] = field(default_factory=list)

    nvidia_smi_path: str | None = None
    gpus: list[NvidiaGPU] = field(default_factory=list)
    driver_version: str | None = None
    cuda_driver_api: str | None = None

    ffmpeg_cuda_hwaccel: bool = False
    nvdec_state: str = "untested"   # verified | failed | unavailable | untested
    nvdec_detail: str = ""
    nvenc_state: str = "untested"
    nvenc_detail: str = ""

    @property
    def ffmpeg_ok(self) -> bool:
        return self.ffmpeg is not None and not self.ffmpeg_problems

    @property
    def gpu_detected(self) -> bool:
        return bool(self.gpus)

    @property
    def gpu_pipeline_ready(self) -> bool:
        return self.ffmpeg_ok and self.nvdec_state == "verified"

    def summary_lines(self) -> list[str]:
        lines = [
            f"OS: {self.os_name} {self.os_version} ({self.architecture})",
            f"CPU threads: {self.cpu_threads}   RAM: {self.ram_total_gb:.1f} GB",
        ]
        if self.ffmpeg:
            lines.append(
                f"FFmpeg: {self.ffmpeg['version']} ({self.ffmpeg['source']}) "
                f"- {self.ffmpeg['ffmpeg_path']}"
            )
        else:
            lines.append(f"FFmpeg: NOT AVAILABLE - {self.ffmpeg_error}")
        lines.extend(f"FFmpeg problem: {p}" for p in self.ffmpeg_problems)

        if self.gpus:
            for gpu in self.gpus:
                mem = f"{gpu.memory_total_mb} MiB" if gpu.memory_total_mb else "? MiB"
                cc = f", compute {gpu.compute_capability}" if gpu.compute_capability else ""
                lines.append(f"NVIDIA GPU {gpu.index}: {gpu.name} ({mem}{cc})")
            lines.append(
                f"NVIDIA driver: {self.driver_version or 'unknown'}"
                + (f"   CUDA driver API: {self.cuda_driver_api}" if self.cuda_driver_api else "")
            )
        else:
            lines.append("NVIDIA GPU: not detected")

        lines.append(f"FFmpeg CUDA hwaccel compiled in: {'yes' if self.ffmpeg_cuda_hwaccel else 'no'}")
        lines.append(f"NVDEC frame-extraction pipeline: {self.nvdec_state.upper()} {self.nvdec_detail}".rstrip())
        lines.append(f"NVENC encoder (not used by extraction): {self.nvenc_state.upper()} {self.nvenc_detail}".rstrip())
        lines.append(
            "Extraction pipeline in Auto mode: "
            + (PIPELINE_GPU if self.gpu_pipeline_ready else PIPELINE_CPU)
        )
        return lines

    def to_dict(self) -> dict:
        data = asdict(self)
        data["gpu_detected"] = self.gpu_detected
        data["gpu_pipeline_ready"] = self.gpu_pipeline_ready
        data["ffmpeg_ok"] = self.ffmpeg_ok
        return data


# ----------------------------------------------------------------------
# NVIDIA driver / GPU detection
# ----------------------------------------------------------------------


def find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    candidates = []
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        candidates += [
            Path(system_root) / "System32" / "nvidia-smi.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe",
        ]
    else:
        candidates += [Path("/usr/bin/nvidia-smi"), Path("/usr/lib/wsl/lib/nvidia-smi")]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _int_or_none(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def detect_nvidia(smi: str | None) -> tuple[list[NvidiaGPU], str | None, str | None]:
    if not smi:
        return [], None, None

    gpus: list[NvidiaGPU] = []
    fields_with_cc = "index,name,memory.total,memory.free,driver_version,compute_cap"
    result = proc.run(
        [smi, f"--query-gpu={fields_with_cc}", "--format=csv,noheader,nounits"], timeout=10
    )
    has_cc = True
    if result is None or result.returncode != 0:
        # Older drivers do not know compute_cap.
        has_cc = False
        result = proc.run(
            [
                smi,
                "--query-gpu=index,name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            timeout=10,
        )
    if result is None or result.returncode != 0:
        return [], None, None

    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        gpus.append(
            NvidiaGPU(
                index=_int_or_none(parts[0]) or len(gpus),
                name=parts[1],
                memory_total_mb=_int_or_none(parts[2]),
                memory_free_mb=_int_or_none(parts[3]),
                driver_version=parts[4] or None,
                compute_capability=(parts[5] if has_cc and len(parts) > 5 else None),
            )
        )

    driver = gpus[0].driver_version if gpus else None
    cuda_api = None
    plain = proc.run([smi], timeout=10)
    if plain is not None and plain.returncode == 0:
        # "CUDA Version: 12.4" (older drivers) or "CUDA UMD Version: 13.5".
        match = re.search(r"CUDA (?:UMD )?Version:\s*([\d.]+)", plain.stdout)
        if match:
            cuda_api = match.group(1)
    return gpus, driver, cuda_api


# ----------------------------------------------------------------------
# Functional verification
# ----------------------------------------------------------------------


def verify_nvdec(info: FFmpegInfo) -> tuple[str, str]:
    if not info.cuda_hwaccel:
        return "unavailable", "(this FFmpeg build has no CUDA hwaccel)"
    if not info.has_hwdownload_filter:
        return "unavailable", "(this FFmpeg build has no hwdownload filter)"
    sample = resource_path("selftest_h264.mp4")
    if not sample.is_file():
        return "untested", f"(self-test clip missing: {sample})"
    result = proc.run(
        [
            info.ffmpeg_path, "-hide_banner", "-v", "error",
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
            "-i", str(sample),
            "-vf", "hwdownload,format=nv12",
            "-f", "null", "-",
        ],
        timeout=45,
    )
    if result is None:
        return "failed", "(test decode timed out or could not start)"
    if result.returncode == 0:
        return "verified", "(H.264 test clip decoded on GPU)"
    hint = nvdec_hint(result.stderr)
    return "failed", f"({failure_reason(result.stderr)})" + (f" - {hint}" if hint else "")


def verify_nvenc(info: FFmpegInfo) -> tuple[str, str]:
    if "h264_nvenc" not in info.nvenc_encoders:
        return "unavailable", "(this FFmpeg build has no h264_nvenc encoder)"
    result = proc.run(
        [
            info.ffmpeg_path, "-hide_banner", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25",
            "-t", "0.2", "-c:v", "h264_nvenc", "-f", "null", "-",
        ],
        timeout=45,
    )
    if result is None:
        return "failed", "(test encode timed out or could not start)"
    if result.returncode == 0:
        return "verified", "(H.264 test encode succeeded)"
    return "failed", f"({failure_reason(result.stderr)})"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

_report_lock = threading.Lock()
_report_cache: AccelerationReport | None = None


def build_report(verify_gpu: bool = True) -> AccelerationReport:
    report = AccelerationReport(
        os_name=platform.system(),
        os_version=_os_version(),
        architecture=platform.machine(),
        cpu_threads=os.cpu_count() or 1,
        ram_total_gb=psutil.virtual_memory().total / (1024 ** 3),
    )

    info: FFmpegInfo | None = None
    try:
        info = probe_ffmpeg()
        report.ffmpeg = info.to_dict()
        report.ffmpeg_problems = info.usable_problems()
        report.ffmpeg_cuda_hwaccel = info.cuda_hwaccel
    except FFmpegNotFoundError as exc:
        report.ffmpeg_error = str(exc)

    report.nvidia_smi_path = find_nvidia_smi()
    report.gpus, report.driver_version, report.cuda_driver_api = detect_nvidia(
        report.nvidia_smi_path
    )

    if info is None:
        report.nvdec_state = report.nvenc_state = "unavailable"
        report.nvdec_detail = report.nvenc_detail = "(FFmpeg not available)"
    elif not report.gpus:
        report.nvdec_state = report.nvenc_state = "unavailable"
        detail = (
            "(no NVIDIA GPU/driver detected)"
            if report.nvidia_smi_path is None
            else "(nvidia-smi found but reported no GPU)"
        )
        report.nvdec_detail = report.nvenc_detail = detail
    elif verify_gpu:
        report.nvdec_state, report.nvdec_detail = verify_nvdec(info)
        report.nvenc_state, report.nvenc_detail = verify_nvenc(info)

    for line in report.summary_lines():
        log.info(line)
    return report


def get_report(refresh: bool = False) -> AccelerationReport:
    """Cached report for this session (GPU checks take ~1-3 s)."""
    global _report_cache
    with _report_lock:
        if _report_cache is None or refresh:
            if refresh:
                from app.utils.ffmpeg import reset_probe_cache

                reset_probe_cache()
            _report_cache = build_report()
        return _report_cache


def _os_version() -> str:
    if sys.platform.startswith("linux"):
        try:
            data = Path("/etc/os-release").read_text(encoding="utf-8")
            match = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', data, re.MULTILINE)
            if match:
                return match.group(1)
        except OSError:
            pass
    if sys.platform == "win32":
        return f"{platform.release()} (build {platform.version()})"
    return platform.release()
