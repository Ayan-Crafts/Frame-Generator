"""FFmpeg discovery, version parsing, GPU capability detection, paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.hardware import capabilities
from app.utils import ffmpeg as ff
from app.utils import paths
from conftest import FFMPEG, requires_ffmpeg


@pytest.fixture(autouse=True)
def fresh_probe():
    ff.reset_probe_cache()
    yield
    ff.reset_probe_cache()


def test_parse_release_and_git_versions():
    text = "ffmpeg version 6.1.1-3ubuntu5 Copyright\nconfiguration: --enable-gpl\nlibavcodec     60. 31.102 / 60. 31.102\n"
    version, lib, config = ff._parse_version(text)
    assert version == "6.1.1-3ubuntu5" and lib == (60, 31) and "--enable-gpl" in config
    version, lib, _ = ff._parse_version("ffmpeg version N-118000-gabc\nlibavcodec     62.  3.100\n")
    assert version.startswith("N-") and lib == (62, 3)


def test_minimum_version_gate():
    old = ff.FFmpegInfo("f", "p", "system", version="4.4.2", libavcodec=(58, 134), has_mjpeg_encoder=True)
    assert not old.version_ok and "too old" in old.usable_problems()[0]
    new = ff.FFmpegInfo("f", "p", "system", version="5.1", libavcodec=(59, 37), has_mjpeg_encoder=True)
    assert new.version_ok and new.usable_problems() == []


def test_list_names_parses_ffmpeg_tables():
    output = " V....D h264_nvenc   NVIDIA NVENC\n V..... h264_cuvid   CUVID\n V....D mjpeg  MJPEG\n"
    assert ff._list_names(output, r"\w+_nvenc") == ["h264_nvenc"]
    assert ff._list_names(output, r"mjpeg") == ["mjpeg"]


def test_override_pointing_nowhere_is_actionable(monkeypatch, tmp_path):
    monkeypatch.setenv("TNP_FFMPEG", str(tmp_path / "nope"))
    with pytest.raises(ff.FFmpegNotFoundError, match="TNP_FFMPEG"):
        ff.get_ffmpeg_path()


def test_missing_everywhere_gives_install_hint(monkeypatch, tmp_path):
    monkeypatch.delenv("TNP_FFMPEG", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(ff, "_candidate_directories", lambda: [("bundled", tmp_path)])
    with pytest.raises(ff.FFmpegNotFoundError) as info:
        ff.get_ffmpeg_path()
    hint = "winget" if sys.platform == "win32" else "apt install ffmpeg"
    assert hint in str(info.value)


def test_bundled_copy_preferred_over_path(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    exe = bundled / f"ffmpeg{ff.EXE_SUFFIX}"
    exe.write_bytes(b"")
    monkeypatch.delenv("TNP_FFMPEG", raising=False)
    monkeypatch.setattr(ff, "_candidate_directories", lambda: [("bundled", bundled)])
    path, source = ff._find_tool("ffmpeg")
    assert Path(path) == exe and source == "bundled"


@requires_ffmpeg
def test_real_ffmpeg_probe():
    info = ff.probe_ffmpeg()
    assert info.version_ok, info.usable_problems()
    assert info.has_mjpeg_encoder


def test_report_without_nvidia(monkeypatch):
    monkeypatch.setattr(capabilities, "find_nvidia_smi", lambda: None)
    report = capabilities.build_report()
    assert not report.gpu_detected
    assert report.nvdec_state == "unavailable"
    assert not report.gpu_pipeline_ready
    assert report.summary_lines()[-1].endswith(capabilities.PIPELINE_CPU)


def test_report_gpu_present_but_ffmpeg_lacks_cuda(monkeypatch):
    if FFMPEG is None:
        pytest.skip("FFmpeg not available")
    fake_gpu = capabilities.NvidiaGPU(0, "Fake GPU", 4096, 4000, "550.00", "7.5")
    monkeypatch.setattr(capabilities, "find_nvidia_smi", lambda: "nvidia-smi")
    monkeypatch.setattr(capabilities, "detect_nvidia", lambda smi: ([fake_gpu], "550.00", "12.4"))
    real_probe = ff.probe_ffmpeg()
    no_cuda = ff.FFmpegInfo(**{**real_probe.__dict__, "hwaccels": []})
    monkeypatch.setattr(capabilities, "probe_ffmpeg", lambda: no_cuda)
    report = capabilities.build_report()
    assert report.gpu_detected
    assert report.nvdec_state == "unavailable"
    assert "no CUDA hwaccel" in report.nvdec_detail
    assert not report.gpu_pipeline_ready


def test_nvidia_smi_parsing(monkeypatch):
    class R:
        def __init__(self, out):
            self.returncode, self.stdout, self.stderr = 0, out, ""

    outputs = iter([
        R("0, NVIDIA GeForce RTX 4050 Laptop GPU, 6141, 6000, 621.24, 8.9\n"
          "1, Tesla T4, 15360, [N/A], 550.54, 7.5\n"),
        R("| NVIDIA-SMI 621.24   KMD Version: 621.24   CUDA UMD Version: 13.5 |"),
    ])
    monkeypatch.setattr(capabilities.proc, "run", lambda *a, **k: next(outputs))
    gpus, driver, cuda = capabilities.detect_nvidia("nvidia-smi")
    assert [g.name for g in gpus] == ["NVIDIA GeForce RTX 4050 Laptop GPU", "Tesla T4"]
    assert gpus[1].memory_free_mb is None and gpus[0].compute_capability == "8.9"
    assert driver == "621.24" and cuda == "13.5"


def test_paths_are_per_user_and_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("TNP_DATA_DIR", str(tmp_path / "d"))
    assert paths.log_dir() == tmp_path / "d" / "logs"
    assert paths.log_dir().is_dir()


def test_default_data_dir_location(monkeypatch, tmp_path):
    monkeypatch.delenv("TNP_DATA_DIR", raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert paths.user_data_dir() == tmp_path / "TrackNetPrepper"
    else:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        assert paths.user_data_dir() == tmp_path / "tracknet-prepper"


def test_selftest_clip_is_bundled():
    clip = paths.resource_path("selftest_h264.mp4")
    assert clip.is_file() and clip.stat().st_size > 1000


def test_subprocess_helper_hides_console_on_windows():
    from app.utils.proc import popen_kwargs

    kwargs = popen_kwargs()
    assert kwargs["encoding"] == "utf-8"
    if sys.platform == "win32":
        assert kwargs["creationflags"] & 0x08000000  # CREATE_NO_WINDOW
    else:
        assert "creationflags" not in kwargs


def test_proc_run_missing_tool_returns_none():
    from app.utils.proc import run

    assert run(["definitely-not-a-real-tool-xyz"]) is None


def test_env_isolation_active():
    assert "tnp-tests-" in os.environ["TNP_DATA_DIR"]
