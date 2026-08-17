from dataclasses import dataclass
from pathlib import Path


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".webm",
    ".mpeg",
    ".mpg",
}


@dataclass
class DatasetInfo:
    video_count: int
    total_bytes: int
    videos: list[Path]

    @property
    def total_gb(self) -> float:
        return self.total_bytes / (1024 ** 3)


class DatasetScanner:

    def scan(self, directory: str) -> DatasetInfo:
        root = Path(directory)

        videos = [
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
        ]

        total_bytes = sum(
            path.stat().st_size
            for path in videos
        )

        return DatasetInfo(
            video_count=len(videos),
            total_bytes=total_bytes,
            videos=sorted(videos),
        )