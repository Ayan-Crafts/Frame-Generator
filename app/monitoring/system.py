import psutil

from app.hardware.capabilities import find_nvidia_smi
from app.utils import proc


class SystemMonitor:

    def __init__(self):
        self._smi = find_nvidia_smi()

    def cpu_percent(self):
        return psutil.cpu_percent(interval=None)

    def memory(self):
        memory = psutil.virtual_memory()

        return {
            "used": memory.used,
            "total": memory.total,
            "percent": memory.percent,
        }

    def nvidia(self):
        if not self._smi:
            return None

        base = "name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu"
        result = None
        # utilization.decoder is unknown to older drivers, which then reject
        # the whole query; retry without it.
        for fields in (base + ",utilization.decoder", base):
            result = proc.run(
                [self._smi, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                timeout=3,
            )
            if result is not None and result.returncode == 0:
                break

        if result is None or result.returncode != 0:
            return None

        lines = result.stdout.strip().splitlines()
        if not lines:
            return None

        values = [value.strip() for value in lines[0].split(",")]

        if len(values) < 6:
            return None

        def number(text):
            try:
                return float(text)
            except ValueError:
                return None  # "[N/A]" on some boards

        return {
            "name": values[0],
            "gpu": number(values[1]),
            "memory_controller": number(values[2]),
            "vram_used": number(values[3]),
            "vram_total": number(values[4]),
            "temperature": number(values[5]),
            "decoder": number(values[6]) if len(values) > 6 else None,
        }
