"""Video → frame extraction: correctness, failure handling, resume, cancel."""

from __future__ import annotations

import hashlib
import shutil
import threading
from pathlib import Path

import pytest
from PIL import Image

from app.hardware.capabilities import PIPELINE_CPU, PIPELINE_GPU
from app.processing import exporter as exporter_module
from app.processing.exporter import VideoExporter, VideoProbeError
from conftest import (
    decoded_frame_count,
    has_encoder,
    make_video,
    requires_ffmpeg,
    requires_gpu,
)

pytestmark = requires_ffmpeg


def frames_in(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.jpg"))


def digest(directory: Path) -> list[str]:
    return [hashlib.md5(p.read_bytes()).hexdigest() for p in frames_in(directory)]


def run(video, out, mode="cpu", gpu_ready=False, **kwargs):
    errors, warnings, progress = [], [], []
    exp = VideoExporter(
        mode=mode, gpu_ready=gpu_ready,
        on_error=errors.append, on_warning=warnings.append, on_progress=progress.append,
    )
    result = exp.export_video(video, out, **kwargs)
    return result, exp, errors, warnings, progress


# ----------------------------------------------------------------------
# Valid input
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["clip h264.mp4", "odd size.avi", "mjpeg.mov", "estimate.mkv", "unicode vidéo 测试.mp4"],
)
def test_cpu_extracts_every_decodable_frame(media_dir, out_dir, name):
    video = media_dir / name
    result, exp, errors, _, _ = run(video, out_dir, mode="cpu")
    assert result is True, errors
    target = out_dir / video.stem
    frames = frames_in(target)
    assert len(frames) == decoded_frame_count(video)
    # TrackNet-compatible naming: 000001.jpg ... contiguous, 1-based.
    assert frames[0].name == "000001.jpg"
    assert frames[-1].name == f"{len(frames):06d}.jpg"
    assert (target / ".complete").exists()
    assert exp.last_pipeline == PIPELINE_CPU
    with Image.open(frames[0]) as image:
        width, height = image.size
    probe = exp.get_video_info(video)
    assert (width, height) == (probe.width, probe.height)


def test_mkv_without_frame_count_is_not_marked_complete_empty(media_dir, out_dir):
    """Regression: v2.0 computed 0 frames for MKV/WebM and marked them complete."""
    video = media_dir / "estimate.mkv"
    info = VideoExporter().get_video_info(video)
    assert info.frame_count_exact is False
    assert info.total_frames > 0
    result, *_ = run(video, out_dir)
    assert result is True
    assert len(frames_in(out_dir / "estimate")) == decoded_frame_count(video) > 0


def test_webm_vp9(media_dir, out_dir):
    video = media_dir / "vp9.webm"
    if not video.exists():
        pytest.skip("no VP9 encoder in this FFmpeg build")
    result, *_ = run(video, out_dir)
    assert result is True
    assert len(frames_in(out_dir / "vp9")) == decoded_frame_count(video)


def test_progress_reports_absolute_frames_and_pipeline(media_dir, out_dir):
    _, _, _, _, progress = run(media_dir / "clip h264.mp4", out_dir)
    final = progress[-1]
    assert final["status"] == "completed"
    assert final["frames"] == final["total_frames"] == 50
    assert all("pipeline" in p for p in progress)


# ----------------------------------------------------------------------
# Invalid / corrupted input
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,fragment",
    [
        ("empty.mp4", "empty"),
        ("text.mp4", "corrupted"),
        ("broken_header.mp4", "corrupted"),
        ("audio_only.mp4", "No video stream"),
    ],
)
def test_unreadable_inputs_fail_cleanly(bad_media_dir, out_dir, name, fragment):
    result, _, errors, _, _ = run(bad_media_dir / name, out_dir)
    assert result is False
    assert errors and fragment in errors[0]
    # No frames and no completion marker are left behind.
    target = out_dir / Path(name).stem
    assert not list(target.glob("*.jpg")) and not (target / ".complete").exists()


def test_missing_file(tmp_path, out_dir):
    result, _, errors, _, _ = run(tmp_path / "nope.mp4", out_dir)
    assert result is False and "not found" in errors[0]


def test_truncated_video_keeps_frames_but_is_not_complete(bad_media_dir, out_dir):
    video = bad_media_dir / "truncated.mp4"
    result, _, errors, _, _ = run(video, out_dir)
    target = out_dir / "truncated"
    assert result is False
    assert "Incomplete export" in errors[0]
    assert len(frames_in(target)) > 0
    assert not (target / ".complete").exists()


# ----------------------------------------------------------------------
# Missing FFmpeg
# ----------------------------------------------------------------------


def test_missing_ffmpeg_is_reported(media_dir, out_dir, monkeypatch, tmp_path):
    from app.utils import ffmpeg as ffmpeg_module

    monkeypatch.setenv("TNP_FFPROBE", str(tmp_path / "missing-ffprobe"))
    result, _, errors, _, _ = run(media_dir / "clip h264.mp4", out_dir)
    assert result is False
    assert "does not exist" in errors[0]
    monkeypatch.delenv("TNP_FFPROBE")
    ffmpeg_module.reset_probe_cache()


# ----------------------------------------------------------------------
# GPU / fallback
# ----------------------------------------------------------------------


@requires_gpu
def test_gpu_pipeline_matches_cpu_frame_count(media_dir, out_dir):
    video = media_dir / "clip h264.mp4"
    result, exp, errors, _, _ = run(video, out_dir / "gpu", mode="gpu", gpu_ready=True)
    assert result is True, errors
    assert exp.last_pipeline == PIPELINE_GPU
    run(video, out_dir / "cpu", mode="cpu")
    assert len(frames_in(out_dir / "gpu" / video.stem)) == len(
        frames_in(out_dir / "cpu" / video.stem)
    )


@requires_gpu
def test_auto_falls_back_to_cpu_for_stream_nvdec_cannot_decode(tmp_path, out_dir):
    if not has_encoder("libx264"):
        pytest.skip("needs libx264 to create a 4:4:4 stream")
    # No NVIDIA generation decodes H.264 4:4:4.
    video = make_video(tmp_path / "yuv444.mp4", pix_fmt="yuv444p", seconds=1)
    result, exp, errors, warnings, _ = run(video, out_dir, mode="auto", gpu_ready=True)
    assert result is True, errors
    assert exp.last_pipeline == PIPELINE_CPU
    assert warnings and "GPU decoding failed" in warnings[0]
    assert len(frames_in(out_dir / "yuv444")) == decoded_frame_count(video)


@requires_gpu
def test_forced_gpu_reports_unsupported_stream(tmp_path, out_dir):
    if not has_encoder("libx264"):
        pytest.skip("needs libx264 to create a 4:4:4 stream")
    video = make_video(tmp_path / "yuv444.mp4", pix_fmt="yuv444p", seconds=1)
    result, _, errors, _, _ = run(video, out_dir, mode="gpu", gpu_ready=True)
    assert result is False
    assert "GPU mode was forced" in errors[0]


def test_auto_without_verified_gpu_uses_cpu(media_dir, out_dir):
    _, exp, *_ = run(media_dir / "clip h264.mp4", out_dir, mode="auto", gpu_ready=False)
    assert exp.last_pipeline == PIPELINE_CPU


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        VideoExporter(mode="turbo")


# ----------------------------------------------------------------------
# Interruption, resume, cancel
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def long_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("long") / "long clip.mp4"
    codec = "libx264" if has_encoder("libx264") else "mpeg4"
    # Keyframe every 50 frames so resume must seek back and discard.
    # Large enough that a pause request lands mid-run even on a fast GPU.
    return make_video(path, size="1280x720", rate=50, seconds=30, codec=codec,
                      extra=["-g", "50", "-preset", "ultrafast"] if codec == "libx264"
                      else ["-g", "50"])


def _interrupt_after(out: Path, frames: int):
    """should_stop callback that fires once `frames` JPEGs exist."""
    def should_stop():
        return len(list(out.glob("*.jpg"))) >= frames
    return should_stop


@pytest.mark.parametrize("mode", ["cpu", pytest.param("gpu", marks=requires_gpu)])
def test_pause_then_resume_is_bit_identical(long_video, tmp_path, mode):
    reference = tmp_path / "reference"
    result, *_ = run(long_video, reference, mode=mode, gpu_ready=mode == "gpu")
    assert result is True
    expected = digest(reference / long_video.stem)

    resumed = tmp_path / "resumed"
    target = resumed / long_video.stem
    result, *_ = run(
        long_video, resumed, mode=mode, gpu_ready=mode == "gpu",
        should_stop=_interrupt_after(target, 137), get_action=lambda: "pause",
    )
    assert result == "paused"
    partial = len(frames_in(target))
    assert 0 < partial < len(expected)
    assert not (target / ".complete").exists()

    # Simulate a crash mid-write: the last frame is truncated on disk.
    last = frames_in(target)[-1]
    last.write_bytes(last.read_bytes()[: last.stat().st_size // 2])

    result, _, errors, _, progress = run(long_video, resumed, mode=mode, gpu_ready=mode == "gpu")
    assert result is True, errors
    assert progress[0]["frames"] == partial - 1  # truncated frame was discarded
    assert digest(target) == expected


@pytest.fixture(scope="module")
def seam_videos(tmp_path_factory, media_dir):
    """CFR sources with keyframes far apart so resume must seek + discard."""
    root = tmp_path_factory.mktemp("seam")
    videos = []
    if has_encoder("libx264"):
        # B-frames + 2 s GOP: the case that broke v2.0's exact-boundary seek.
        videos.append(make_video(root / "bframes.mp4", size="320x180", rate=50, seconds=9,
                                 extra=["-g", "100", "-bf", "3"]))
        videos.append(make_video(root / "matroska.mkv", size="320x180", rate=30, seconds=9,
                                 extra=["-g", "60"]))
    videos.append(make_video(root / "mpeg4.avi", size="320x180", rate=25, seconds=9,
                             codec="mpeg4", extra=["-g", "50"]))
    vp9 = media_dir / "vp9.webm"
    if vp9.exists():
        videos.append(make_video(root / "vp9.webm", size="320x180", rate=25, seconds=8,
                                 codec="libvpx-vp9", extra=["-g", "50", "-b:v", "200k"]))
    return videos


@pytest.mark.parametrize("mode", ["cpu", pytest.param("gpu", marks=requires_gpu)])
def test_resume_seam_is_frame_exact(seam_videos, tmp_path, mode):
    """Regression: v2.0 resume skipped one source frame and duplicated the next.

    For every video and several resume points (including points that need a
    keyframe seek far into the file) the resumed output must be bit-identical
    to an uninterrupted extraction.
    """
    for video in seam_videos:
        reference = tmp_path / mode / "reference"
        assert run(video, reference, mode=mode, gpu_ready=mode == "gpu")[0] is True
        expected = digest(reference / video.stem)
        total = len(expected)
        for resume_at in sorted({2, 7, total // 2 + 1, total - 3, total}):
            work = tmp_path / mode / f"resume_{resume_at}"
            target = work / video.stem
            shutil.copytree(reference / video.stem, target)
            (target / ".complete").unlink()
            for frame in frames_in(target)[resume_at - 1:]:
                frame.unlink()
            result, _, errors, _, _ = run(video, work, mode=mode, gpu_ready=mode == "gpu")
            assert result is True, (video.name, resume_at, errors)
            got = digest(target)
            first_bad = next((i for i, (a, b) in enumerate(zip(got, expected)) if a != b), None)
            assert len(got) == total and first_bad is None, (
                f"{video.name}: resume at frame {resume_at} diverged at frame "
                f"{None if first_bad is None else first_bad + 1}"
            )


def test_resume_plan_avoids_exact_boundary():
    seek, discard = exporter_module.resume_plan(379, 50.0, False)
    # Seek lands a quarter frame before frame 129, which is then frame n=0.
    assert seek == pytest.approx(128.75 / 50) and discard == 379 - 129
    assert exporter_module.resume_plan(0, 50.0, False) == (0.0, 0)
    assert exporter_module.resume_plan(100, 50.0, False) == (0.0, 100)  # inside pre-roll
    assert exporter_module.resume_plan(5000, 29.97, True) == (0.0, 5000)  # VFR: no seek


def test_stop_keep_preserves_frames(long_video, out_dir):
    target = out_dir / long_video.stem
    result, *_ = run(long_video, out_dir, should_stop=_interrupt_after(target, 40),
                     get_action=lambda: "stop_keep")
    assert result == "stopped"
    assert len(frames_in(target)) >= 40


def test_cancel_delete_removes_current_output(long_video, out_dir):
    target = out_dir / long_video.stem
    result, *_ = run(long_video, out_dir, should_stop=_interrupt_after(target, 40),
                     get_action=lambda: "cancel_delete")
    assert result == "cancelled"
    assert not target.exists()


def test_completed_video_is_skipped(media_dir, out_dir):
    video = media_dir / "clip h264.mp4"
    run(video, out_dir)
    result, _, _, _, progress = run(video, out_dir)
    assert result is True and progress[-1]["status"] == "skipped"


def test_concurrent_exports_to_separate_dirs(media_dir, tmp_path):
    results = {}

    def work(name):
        results[name] = run(media_dir / "clip h264.mp4", tmp_path / name)[0]

    threads = [threading.Thread(target=work, args=(f"o{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r is True for r in results.values())


# ----------------------------------------------------------------------
# Disk space
# ----------------------------------------------------------------------


def test_refuses_to_start_when_disk_is_full(media_dir, out_dir, monkeypatch):
    monkeypatch.setattr(exporter_module, "free_space_gb", lambda path: 0.1)
    result, _, errors, _, _ = run(media_dir / "clip h264.mp4", out_dir)
    assert result is False
    assert "Not enough disk space" in errors[0]


def test_stops_safely_when_disk_fills_during_export(long_video, out_dir, monkeypatch):
    calls = {"n": 0}

    def shrinking(path):
        calls["n"] += 1
        return 10.0 if calls["n"] <= 1 else 0.01

    monkeypatch.setattr(exporter_module, "free_space_gb", shrinking)
    # Make the in-loop disk check run immediately.
    monkeypatch.setattr(exporter_module.time, "monotonic", _fast_clock())
    result, _, errors, _, _ = run(long_video, out_dir)
    assert result is False
    assert "almost full" in errors[0]
    assert not (out_dir / long_video.stem / ".complete").exists()


def _fast_clock():
    import time as time_module

    real_monotonic = time_module.monotonic  # captured before monkeypatching
    start = real_monotonic()

    def clock():
        return start + (real_monotonic() - start) * 100

    return clock


# ----------------------------------------------------------------------
# Probe details
# ----------------------------------------------------------------------


def test_probe_rejects_non_files(tmp_path):
    with pytest.raises(VideoProbeError):
        VideoExporter().get_video_info(tmp_path)


def test_failure_reason_skips_stats_line():
    stderr = (
        "[hwdownload @ 0x1] Invalid output format nv12 for hwframe download.\n"
        "[vf#0:0 @ 0x2] Task finished with error code: -22\n"
        "frame=    0 fps=0.0 q=0.0 Lsize=0KiB\nConversion failed!\n"
    )
    assert exporter_module._failure_reason(stderr) == (
        "Invalid output format nv12 for hwframe download."
    )
