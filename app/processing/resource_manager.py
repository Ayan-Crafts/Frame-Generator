import os
import shutil
import subprocess
from app.utils.ffmpeg import get_ffmpeg_path
import psutil


class ResourceManager:

    def __init__(self):
        self.cpu_threads = os.cpu_count() or 4

    # --------------------------------------------------
    # NVIDIA
    # --------------------------------------------------

    def nvidia_info(self):

        try:

            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu="
                    "name,"
                    "utilization.gpu,"
                    "memory.used,"
                    "memory.total,"
                    "temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode != 0:
                return None

            line = result.stdout.strip()

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
            FileNotFoundError,
            subprocess.TimeoutExpired,
            ValueError,
        ):
            return None

    # --------------------------------------------------
    # AMD
    # --------------------------------------------------

    def amd_available(self):

        try:

            result = subprocess.run(
                [
                    get_ffmpeg_path(),
                    "-hide_banner",
                    "-encoders",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )

            return (
                "amf" in
                result.stdout.lower()
            )

        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
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

    def system_info(self):

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

        # Determine the disk containing the
        # current Python process.
        disk_path = os.getcwd()

        disk = shutil.disk_usage(
            disk_path
        )

        free_disk_gb = (
            disk.free /
            (1024 ** 3)
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

    def get_profile(self):

        system = self.system_info()
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
    def ffmpeg_threads(self):

        profile = self.get_profile()

        return profile["ffmpeg_threads"]