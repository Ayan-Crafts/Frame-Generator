"""Scanner, output naming, resume inspection and job persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from app.jobs.job_manager import JobManager
from app.processing.resume import ResumeManager
from app.processing.scanner import DatasetScanner, output_names


def touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ----------------------------------------------------------------------
# Scanner
# ----------------------------------------------------------------------


def test_scanner_filters_extensions_recursively(tmp_path):
    touch(tmp_path / "a.mp4")
    touch(tmp_path / "sub dir" / "B.MKV")
    touch(tmp_path / "sub dir" / "deeper" / "c.webm")
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "frame.jpg")
    info = DatasetScanner().scan(str(tmp_path))
    assert [p.name for p in info.videos] == ["a.mp4", "B.MKV", "c.webm"]
    assert info.video_count == 3
    assert info.total_bytes == 3


def test_scanner_empty_directory(tmp_path):
    info = DatasetScanner().scan(str(tmp_path))
    assert info.video_count == 0 and info.videos == []


def test_scanner_missing_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        DatasetScanner().scan(str(tmp_path / "missing"))


def test_output_names_unique_stems_unchanged(tmp_path):
    videos = [tmp_path / "x" / "rally1.mp4", tmp_path / "y" / "rally2.mp4"]
    assert output_names(videos) == {videos[0]: "rally1", videos[1]: "rally2"}


def test_output_names_disambiguate_collisions(tmp_path):
    """Regression: same-named videos in different folders shared one output dir."""
    videos = [
        tmp_path / "match1" / "cam.mp4",
        tmp_path / "match2" / "cam.mp4",
        tmp_path / "match2" / "cam.mkv",
        tmp_path / "solo.mp4",
    ]
    names = output_names(videos)
    assert names[videos[3]] == "solo"
    assert len({n.lower() for n in names.values()}) == 4
    assert names[videos[0]] == "match1__cam"
    assert all("/" not in n and "\\" not in n for n in names.values())


def test_output_names_case_insensitive_collision(tmp_path):
    videos = [tmp_path / "a" / "Clip.mp4", tmp_path / "b" / "clip.mp4"]
    names = output_names(videos)
    assert names[videos[0]].lower() != names[videos[1]].lower()


# ----------------------------------------------------------------------
# Resume inspection
# ----------------------------------------------------------------------


def jpeg(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(path, "JPEG")


def test_resume_empty_and_missing(tmp_path):
    rm = ResumeManager()
    assert rm.inspect(tmp_path / "missing").existing_frames == 0
    assert rm.inspect(tmp_path).resume_frame == 1


def test_resume_truncates_after_gap(tmp_path):
    for n in (1, 2, 3, 5, 6):
        jpeg(tmp_path / f"{n:06d}.jpg")
    info = ResumeManager().inspect(tmp_path)
    assert info.existing_frames == 3 and info.resume_frame == 4
    assert sorted(p.name for p in tmp_path.glob("*.jpg")) == [
        "000001.jpg", "000002.jpg", "000003.jpg"
    ]


def test_resume_discards_truncated_tail_frame(tmp_path):
    """PIL verify() accepts truncated JPEGs; the EOI check must not."""
    for n in range(1, 5):
        jpeg(tmp_path / f"{n:06d}.jpg")
    last = tmp_path / "000004.jpg"
    last.write_bytes(last.read_bytes()[:-10])
    info = ResumeManager().inspect(tmp_path)
    assert info.existing_frames == 3
    assert not last.exists()


def test_resume_respects_complete_marker(tmp_path):
    jpeg(tmp_path / "000001.jpg")
    rm = ResumeManager()
    rm.mark_complete(tmp_path)
    assert rm.inspect(tmp_path).completed
    rm.remove_complete_marker(tmp_path)
    assert not rm.inspect(tmp_path).completed


def test_resume_ignores_non_numeric_files(tmp_path):
    jpeg(tmp_path / "000001.jpg")
    jpeg(tmp_path / "preview.jpg")
    assert ResumeManager().inspect(tmp_path).existing_frames == 1
    assert (tmp_path / "preview.jpg").exists()


# ----------------------------------------------------------------------
# Jobs
# ----------------------------------------------------------------------


def test_job_lifecycle(tmp_path):
    jm = JobManager()
    job = jm.create_job(str(tmp_path), str(tmp_path / "out"), [tmp_path / "v.mp4"])
    jm.update_job(job["job_id"], status="paused", current_video="v.mp4")
    assert jm.load_job(job["job_id"])["status"] == "paused"
    assert any(j["job_id"] == job["job_id"] for j in jm.unfinished_jobs())
    jm.complete_job(job["job_id"])
    assert jm.load_job(job["job_id"])["status"] == "completed"
    jm.cancel_job(job["job_id"])
    assert jm.load_job(job["job_id"]) is None


def test_job_files_are_valid_json_and_isolated(tmp_path):
    jm = JobManager()
    job = jm.create_job("in", "out", [])
    path = jm.jobs_directory / f"{job['job_id']}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["job_id"] == job["job_id"]
    # conftest redirects job storage away from the real home directory.
    assert Path.home() / ".frame-generator" not in path.parents


def test_corrupt_job_file_is_ignored():
    jm = JobManager()
    (jm.jobs_directory / "broken.json").write_text("{not json", encoding="utf-8")
    assert jm.load_job("broken") is None
    jm.unfinished_jobs()  # must not raise
