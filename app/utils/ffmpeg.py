import sys
from pathlib import Path


def _base_directory() -> Path:

    if getattr(sys, "frozen", False):
        return Path(
            sys.executable
        ).resolve().parent

    return (
        Path(__file__)
        .resolve()
        .parents[2]
    )


def _ffmpeg_directory() -> Path:

    base = _base_directory()

    if getattr(sys, "frozen", False):
        return base / "ffmpeg"

    return base / "packaging" / "ffmpeg"


def get_ffmpeg_path() -> str:

    path = (
        _ffmpeg_directory()
        / "ffmpeg.exe"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"FFmpeg executable not found:\n{path}"
        )

    return str(path)


def get_ffprobe_path() -> str:

    path = (
        _ffmpeg_directory()
        / "ffprobe.exe"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"FFprobe executable not found:\n{path}"
        )

    return str(path)