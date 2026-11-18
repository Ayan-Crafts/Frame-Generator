"""GPU presence detection (display only).

Presence of a GPU does not imply the extraction pipeline can use it; see
:mod:`app.hardware.capabilities` for functional verification.
"""

import sys
from dataclasses import dataclass

from app.hardware.capabilities import find_nvidia_smi
from app.utils import proc


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

        # AMD second (informational: the pipeline has no AMD path)
        amd = self._detect_amd()

        if amd and amd.available:
            return amd

        return None

    def _detect_nvidia(self) -> GPUInfo | None:
        smi = find_nvidia_smi()
        if not smi:
            return None

        result = proc.run(
            [
                smi,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
        )

        if result is None or result.returncode != 0:
            return None

        try:
            line = result.stdout.strip().splitlines()[0]
            name, memory, driver = [value.strip() for value in line.split(",")[:3]]
            return GPUInfo(
                vendor="NVIDIA",
                name=name,
                memory_mb=int(float(memory)),
                driver=driver,
                available=True,
                acceleration="NVDEC",
            )
        except (ValueError, IndexError):
            return None

    def _detect_amd(self) -> GPUInfo | None:
        if sys.platform != "win32":
            return None

        names = []
        result = proc.run(
            ["wmic", "path", "win32_VideoController", "get", "Name,DriverVersion", "/format:csv"],
            timeout=5,
        )
        if result is not None and result.returncode == 0:
            # Node,DriverVersion,Name
            for line in result.stdout.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3 and "AMD" in parts[2].upper():
                    names.append((parts[2], parts[1]))
        else:
            # wmic is removed from recent Windows 11 builds.
            result = proc.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "ForEach-Object { $_.Name + '|' + $_.DriverVersion }",
                ],
                timeout=10,
            )
            if result is not None and result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "|" in line and "AMD" in line.upper():
                        name, driver = line.split("|", 1)
                        names.append((name.strip(), driver.strip()))

        if not names:
            return None
        name, driver = names[0]
        return GPUInfo(
            vendor="AMD",
            name=name,
            memory_mb=None,
            driver=driver,
            available=True,
            acceleration=None,
        )
