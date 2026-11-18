import os
import shutil
from pathlib import Path

import psutil

from app.hardware.capabilities import find_nvidia_smi
from app.utils import proc
from app.utils.ffmpeg import FFmpegNotFoundError, probe_ffmpeg


class ResourceManager:

    def __init__(self):
        self.cpu_threads = os.cpu_count() or 4

    # --------------------------------------------------
    # NVIDIA
    # --------------------------------------------------

    def nvidia_info(self):

        smi = find_nvidia_smi()

        if not smi:
            return None

        try:

            result = proc.run(
                [
                    smi,
                    "--query-gpu="
                    "name,"
                    "utilization.gpu,"
                    "memory.used,"
                    "memory.total,"
                    "temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                timeout=3,
            )

            if result is None or result.returncode != 0:
                return None

            line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""

            if not line:
                return None

            values = [
                x.strip()
                for x in line.split(",")
            ]

            if len(values) < 5:
                return None

            return {
                "vendor": "NVIDIA",
                "name": values[0],
                "gpu_percent": float(values[1]),
                "vram_used_mb": float(values[2]),
                "vram_total_mb": float(values[3]),
                "temperature": float(values[4]),
            }

        except (
            ValueError,
            IndexError,
        ):
            return None

    # --------------------------------------------------
    # AMD
    # --------------------------------------------------

    def amd_available(self):

        # Uses the cached FFmpeg probe instead of spawning
        # "ffmpeg -encoders" for every video.
        try:
            return "amf" in probe_ffmpeg().hwaccels
        except FFmpegNotFoundError:
            return False

    # --------------------------------------------------
    # GPU selection
    # --------------------------------------------------

    def detect_gpu(self):

        # NVIDIA gets priority.
        nvidia = self.nvidia_info()

        if nvidia:
            return nvidia

        # AMD fallback.
        if self.amd_available():

            return {
                "vendor": "AMD",
                "name": "AMD GPU",
                "gpu_percent": 0,
                "vram_used_mb": 0,
                "vram_total_mb": 0,
                "temperature": 0,
            }

        return {
            "vendor": "CPU",
            "name": "CPU",
            "gpu_percent": 0,
            "vram_used_mb": 0,
            "vram_total_mb": 0,
            "temperature": 0,
        }

    # --------------------------------------------------
    # System resources
    # --------------------------------------------------

    def system_info(self, disk_path=None):

        memory = psutil.virtual_memory()

        available_ram_gb = (
            memory.available /
            (1024 ** 3)
        )

        cpu_percent = (
            psutil.cpu_percent(
                interval=None
            )
        )

        # Measure the disk that frames are written to. (Previously the
        # current working directory was used, which in an installed app is
        # usually the install drive, not the output drive.)
        free_disk_gb = free_space_gb(
            disk_path or os.getcwd()
        )

        return {
            "cpu_percent": cpu_percent,
            "cpu_threads": self.cpu_threads,
            "ram_available_gb": available_ram_gb,
            "ram_percent": memory.percent,
            "disk_free_gb": free_disk_gb,
        }

    # --------------------------------------------------
    # Dynamic profile
    # --------------------------------------------------

    def get_profile(self, output_directory=None):

        system = self.system_info(output_directory)
        gpu = self.detect_gpu()

        threads = system["cpu_threads"]
        ram = system["ram_available_gb"]
        cpu = system["cpu_percent"]
        disk = system["disk_free_gb"]

        # ----------------------------------------------
        # Base CPU allocation
        # ----------------------------------------------

        if threads <= 4:
            ffmpeg_threads = 2

        elif threads <= 8:
            ffmpeg_threads = 4

        elif threads <= 12:
            ffmpeg_threads = 6

        else:
            ffmpeg_threads = max(
                6,
                threads - 4,
            )

        # ----------------------------------------------
        # Protect heavily loaded systems
        # ----------------------------------------------

        if cpu >= 85:
            ffmpeg_threads = max(
                2,
                ffmpeg_threads // 2,
            )

        elif cpu >= 70:
            ffmpeg_threads = max(
                2,
                int(
                    ffmpeg_threads * 0.75
                ),
            )

        # ----------------------------------------------
        # Protect low-memory systems
        # ----------------------------------------------

        if ram < 4:
            ffmpeg_threads = 2

        elif ram < 8:
            ffmpeg_threads = min(
                ffmpeg_threads,
                4,
            )

        # ----------------------------------------------
        # Disk pressure
        # ----------------------------------------------

        if disk < 20:
            ffmpeg_threads = min(
                ffmpeg_threads,
                4,
            )

        if disk < 10:
            ffmpeg_threads = 2

        # ----------------------------------------------
        # GPU pressure
        # ----------------------------------------------

        if gpu["vendor"] == "NVIDIA":

            gpu_util = gpu["gpu_percent"]
            temperature = gpu["temperature"]

            # Don't aggressively increase CPU-side
            # work when the GPU is already saturated.
            if gpu_util >= 95:
                ffmpeg_threads = min(
                    ffmpeg_threads,
                    4,
                )

            # Protect a hot GPU.
            if temperature >= 82:
                ffmpeg_threads = min(
                    ffmpeg_threads,
                    4,
                )

            if temperature >= 88:
                ffmpeg_threads = 2

        # ----------------------------------------------
        # Queue size
        # ----------------------------------------------

        if ram >= 32:
            queue_size = 256

        elif ram >= 16:
            queue_size = 128

        elif ram >= 8:
            queue_size = 64
        else:
            queue_size = 32
        if disk < 20:
            queue_size //= 2
        if disk < 10:
            queue_size = 16
        return {
            "gpu": gpu,
            "cpu_threads": threads,
            "ffmpeg_threads": ffmpeg_threads,
            "queue_size": queue_size,
            "ram_available_gb": ram,
            "ram_percent": system["ram_percent"],
            "cpu_percent": cpu,
            "disk_free_gb": disk,
        }
    def ffmpeg_threads(self, output_directory=None):

        profile = self.get_profile(output_directory)

        return profile["ffmpeg_threads"]


def free_space_gb(path) -> float:
    """Free space on the volume containing ``path`` (walks up to an existing parent)."""
    candidate = Path(path)
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    try:
        return shutil.disk_usage(candidate).free / (1024 ** 3)
    except OSError:
        return float("inf")