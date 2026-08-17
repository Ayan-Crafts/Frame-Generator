import subprocess
from dataclasses import dataclass


@dataclass
class GPUInfo:
    vendor: str
    name: str
    memory_mb: int | None
    driver: str | None
    available: bool
    acceleration: str | None


class HardwareDetector:

    def detect(self) -> GPUInfo | None:
        # NVIDIA has priority
        nvidia = self._detect_nvidia()

        if nvidia and nvidia.available:
            return nvidia

        # AMD second
        amd = self._detect_amd()

        if amd and amd.available:
            return amd

        return None

    def _detect_nvidia(self) -> GPUInfo | None:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            line = result.stdout.strip().splitlines()[0]

            name, memory, driver = [
                value.strip()
                for value in line.split(",")
            ]

            return GPUInfo(
                vendor="NVIDIA",
                name=name,
                memory_mb=int(float(memory)),
                driver=driver,
                available=True,
                acceleration="NVDEC",
            )

        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            ValueError,
            IndexError,
        ):
            return None

    def _detect_amd(self) -> GPUInfo | None:
        try:
            result = subprocess.run(
                [
                    "wmic",
                    "path",
                    "win32_VideoController",
                    "get",
                    "Name,AdapterRAM,DriverVersion",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            for line in result.stdout.splitlines():

                if "AMD" not in line.upper():
                    continue

                parts = line.split(",")

                if len(parts) < 4:
                    continue

                name = parts[2].strip()
                driver = parts[3].strip()

                return GPUInfo(
                    vendor="AMD",
                    name=name,
                    memory_mb=None,
                    driver=driver,
                    available=True,
                    acceleration="AMF",
                )

        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return None

        return None