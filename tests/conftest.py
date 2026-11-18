"""Shared fixtures.

All media is synthetic (FFmpeg test patterns) and generated into a temp
directory; the user's datasets, logs and job files are never touched:
TNP_DATA_DIR / TNP_JOBS_DIR are redirected before any app module runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_SESSION_TMP = Path(tempfile.mkdtemp(prefix="tnp-tests-"))
os.environ["TNP_DATA_DIR"] = str(_SESSION_TMP / "appdata")
os.environ["TNP_JOBS_DIR"] = str(_SESSION_TMP / "jobs")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.utils import proc  # noqa: E402
from app.utils.ffmpeg import FFmpegNotFoundError, probe_ffmpeg  # noqa: E402


def _ffmpeg_info():
    try:
        return probe_ffmpeg()
    except FFmpegNotFoundError:
        return None


FFMPEG = _ffmpeg_info()

requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg not available")


def _gpu_ready() -> bool:
    if FFMPEG is None or os.environ.get("TNP_TEST_NO_GPU"):
        return False
    from app.hardware.capabilities import get_report

    return get_report().gpu_pipeline_ready


GPU_READY = _gpu_ready()
requires_gpu = pytest.mark.skipif(
    not GPU_READY, reason="NVDEC pipeline not verified on this machine (no usable NVIDIA GPU)"
)


def has_encoder(name: str) -> bool:
    if FFMPEG is None:
        return False
    result = proc.run([FFMPEG.ffmpeg_path, "-hide_banner", "-encoders"], timeout=20)
    return result is not None and any(
        len(line.split()) > 1 and line.split()[1] == name for line in result.stdout.splitlines()
    )


def make_video(path: Path, *, size="320x180", rate=25, seconds=2.0, codec="libx264",
               pix_fmt="yuv420p", extra=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        FFMPEG.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}",
        "-t", str(seconds), "-c:v", codec,
    ]
    if pix_fmt:
        command += ["-pix_fmt", pix_fmt]
    command += list(extra or []) + [str(path)]
    subprocess.run(command, check=True, capture_output=True, **proc.popen_kwargs())
    return path


def decoded_frame_count(path: Path) -> int:
    """Ground truth: frames FFprobe actually decodes (not container metadata)."""
    result = subprocess.run(
        [
            FFMPEG.ffprobe_path, "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path),
        ],
        capture_output=True, check=True, **proc.popen_kwargs(),
    )
    return int(result.stdout.strip().split(",")[0])


@pytest.fixture(scope="session")
def media_dir() -> Path:
    if FFMPEG is None:
        pytest.skip("FFmpeg not available")
    root = _SESSION_TMP / "media"
    h264 = "libx264" if has_encoder("libx264") else "mpeg4"
    pix = "yuv420p"
    make_video(root / "clip h264.mp4", codec=h264, pix_fmt=pix, seconds=2, rate=25)
    make_video(root / "odd size.avi", codec="mpeg4", size="321x181", seconds=1, rate=24, pix_fmt=pix)
    make_video(root / "mjpeg.mov", codec="mjpeg", seconds=1, rate=30, pix_fmt="yuvj420p")
    make_video(root / "estimate.mkv", codec=h264, seconds=2, rate=30, pix_fmt=pix)
    make_video(root / "unicode vidéo 测试.mp4", codec=h264, seconds=1, rate=25, pix_fmt=pix)
    if has_encoder("libvpx-vp9"):
        make_video(root / "vp9.webm", codec="libvpx-vp9", seconds=1, rate=25, pix_fmt=pix,
                   extra=["-b:v", "300k"])
    return root


@pytest.fixture(scope="session")
def bad_media_dir() -> Path:
    if FFMPEG is None:
        pytest.skip("FFmpeg not available")
    root = _SESSION_TMP / "bad_media"
    root.mkdir(parents=True, exist_ok=True)
    good = make_video(root / "_source.mp4", seconds=4, rate=30, extra=["-movflags", "+faststart"])
    data = good.read_bytes()
    # faststart puts the index (moov) first: cutting the file in half keeps
    # the index but loses half the frames (decodable, truncated); keeping
    # only 4 KB cuts the index itself (unreadable header).
    (root / "truncated.mp4").write_bytes(data[: len(data) // 2])
    (root / "broken_header.mp4").write_bytes(data[:4000])
    (root / "empty.mp4").write_bytes(b"")
    (root / "text.mp4").write_text("this is not a video", encoding="utf-8")
    subprocess.run(
        [FFMPEG.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=d=1", "-c:a", "aac", str(root / "audio_only.mp4")],
        check=True, capture_output=True, **proc.popen_kwargs(),
    )
    good.unlink()
    return root


@pytest.fixture
def out_dir(tmp_path) -> Path:
    path = tmp_path / "output with spaces"
    path.mkdir()
    return path


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def wait_until(qapp, predicate, timeout=60.0, interval_ms=50):
    """Spin the Qt event loop until predicate() is true."""
    import time

    from PySide6.QtCore import QEventLoop, QTimer

    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError("condition not met in time")
        loop = QEventLoop()
        QTimer.singleShot(interval_ms, loop.quit)
        loop.exec()
