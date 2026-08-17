import os
import shutil

import psutil


class ResourceManager:

    def __init__(self):
        self.cpu_threads = os.cpu_count() or 4

    def get_profile(self):
        memory = psutil.virtual_memory()

        available_ram_gb = (
            memory.available /
            (1024 ** 3)
        )

        disk = shutil.disk_usage(
            psutil.disk_partitions()[0].mountpoint
        )

        free_disk_gb = (
            disk.free /
            (1024 ** 3)
        )

        cpu_threads = self.cpu_threads

        # Keep some CPU capacity available for
        # the operating system and UI.
        if cpu_threads <= 4:
            workers = 1

        elif cpu_threads <= 8:
            workers = 2

        else:
            workers = min(
                4,
                max(
                    2,
                    cpu_threads // 4,
                ),
            )

        # Reduce processing pressure when
        # available RAM is low.
        if available_ram_gb < 4:
            workers = 1

        elif available_ram_gb < 8:
            workers = min(
                workers,
                2,
            )

        # If the system disk is critically low,
        # don't aggressively queue work.
        if free_disk_gb < 10:
            workers = 1

        return {
            "cpu_threads": cpu_threads,
            "workers": workers,
            "available_ram_gb": available_ram_gb,
            "free_disk_gb": free_disk_gb,
        }

    def ffmpeg_threads(self) -> int:
        profile = self.get_profile()

        threads = profile["cpu_threads"]

        # Leave CPU capacity for Windows,
        # the UI, disk I/O and monitoring.
        if threads <= 4:
            return 2

        if threads <= 8:
            return 4

        return max(
            4,
            threads - 4,
        )