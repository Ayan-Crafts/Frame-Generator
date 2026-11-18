import os
from dataclasses import dataclass, field
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
    ".ts",
    ".mts",
    ".m2ts",
    ".wmv",
    ".flv",
}


@dataclass
class DatasetInfo:
    video_count: int
    total_bytes: int
    videos: list[Path]
    skipped_directories: list[str] = field(default_factory=list)

    @property
    def total_gb(self) -> float:
        return self.total_bytes / (1024 ** 3)


class DatasetScanner:

    def scan(self, directory: str) -> DatasetInfo:
        root = Path(directory)

        if not root.is_dir():
            raise NotADirectoryError(f"Input directory does not exist: {root}")

        videos: list[Path] = []
        total_bytes = 0
        skipped: list[str] = []

        # os.walk with onerror keeps going past folders the user cannot
        # read (e.g. "System Volume Information"), which made rglob raise.
        for current, dirs, files in os.walk(
            root,
            onerror=lambda error: skipped.append(str(getattr(error, "filename", error))),
        ):
            dirs.sort()
            for name in sorted(files):
                path = Path(current) / name
                if path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    skipped.append(str(path))
                    continue
                videos.append(path)
                total_bytes += size

        videos.sort()

        return DatasetInfo(
            video_count=len(videos),
            total_bytes=total_bytes,
            videos=videos,
            skipped_directories=skipped,
        )


def output_names(videos: list[Path]) -> dict[Path, str]:
    """Map each video to the name of its output sub-directory.

    Unique stems keep the historical layout (``<output>/<stem>/``) so
    existing exports still resume. Videos whose stem collides with another
    video in the same job get their parent folder names prefixed
    (``match1__cam``) instead of silently sharing one output directory.
    """
    by_stem: dict[str, list[Path]] = {}
    for video in videos:
        by_stem.setdefault(video.stem.lower(), []).append(video)

    names: dict[Path, str] = {}
    for group in by_stem.values():
        if len(group) == 1:
            names[group[0]] = group[0].stem
            continue

        def unique(mapping):
            return len({n.lower() for n in mapping.values()}) == len(group)

        max_depth = max(len(video.parent.parts) for video in group)
        candidate = {}
        for depth in range(1, max_depth + 1):
            candidate = {
                video: "__".join(list(video.parent.parts[-depth:]) + [video.stem])
                for video in group
            }
            if unique(candidate):
                break

        if not unique(candidate):
            # Same folder, same stem, different extension (cam.mp4 / cam.mkv).
            candidate = {
                video: f"{name}_{video.suffix.lstrip('.').lower()}"
                for video, name in candidate.items()
            }

        for video, name in candidate.items():
            safe = name.replace(":", "").replace("\\", "_").replace("/", "_")
            names[video] = safe

    return names
