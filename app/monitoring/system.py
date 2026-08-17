import subprocess

import psutil


class SystemMonitor:

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
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu="
                    "name,"
                    "utilization.gpu,"
                    "utilization.memory,"
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

            values = [
                value.strip()
                for value in result.stdout.strip().split(",")
            ]

            if len(values) < 6:
                return None

            return {
                "name": values[0],
                "gpu": float(values[1]),
                "memory_controller": float(values[2]),
                "vram_used": float(values[3]),
                "vram_total": float(values[4]),
                "temperature": float(values[5]),
            }

        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            ValueError,
        ):
            return None