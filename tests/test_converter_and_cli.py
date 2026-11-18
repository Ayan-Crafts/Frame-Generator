"""TrackNet converter and command-line interface."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from app.cli import main as cli_main
from app.tools import convert_to_tracknet as conv
from conftest import ROOT, requires_ffmpeg


def annotated_folder(root: Path, count=10, size=(1280, 720)) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for n in range(1, count + 1):
        name = f"{n:06d}.jpg"
        Image.new("RGB", size, (n, n, n)).save(root / name, "JPEG")
        visible = n % 3 != 0
        rows.append({
            "frame": name, "x": 640 if visible else 0, "y": 360 if visible else 0,
            "visibility": 1 if visible else 0, "x1": 0, "y1": 0, "x2": 0, "y2": 0,
            "source": "MANUAL", "confidence": 1.0,
            "status": "ACCEPTED" if visible else "FULLY_OCCLUDED",
        })
    with open(root / "annotations.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return root


def read_rows(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_validation_ratio_is_respected(tmp_path):
    """Regression: v2.0 ignored --validation-ratio and always split 80/20."""
    src = annotated_folder(tmp_path / "frames", count=10)
    out = tmp_path / "dataset"
    assert conv.main(["--input", str(src), "--output", str(out), "--validation-ratio", "0.5"]) == 0
    assert len(read_rows(out / "training_model1.csv")) == 5
    assert len(read_rows(out / "testing_model1.csv")) == 5


def test_tracknet_csv_layout_and_heatmaps(tmp_path):
    src = annotated_folder(tmp_path / "frames", count=6)
    out = tmp_path / "dataset"
    conv.main(["--input", str(src), "--output", str(out), "--copy-images"])
    rows = read_rows(out / "training_model1.csv") + read_rows(out / "testing_model1.csv")
    assert len(rows) == 6
    for image_path, frame, visibility, heatmap_path in rows:
        # TrackNet V1 loader reads column 0 (image) and column 3 (heatmap).
        assert Path(image_path).is_file() and Path(heatmap_path).is_file()
        with Image.open(image_path) as image:
            assert image.size == (640, 360)
        with Image.open(heatmap_path) as heatmap:
            assert heatmap.size == (640, 360) and heatmap.mode == "L"
            peak = max(heatmap.getdata())
        assert (peak > 200) == (visibility == "1")
    report = json.loads((out / "conversion_report.json").read_text(encoding="utf-8"))
    assert report["visible"] == 4 and report["fully_occluded"] == 2


def test_png_heatmaps_are_lossless(tmp_path):
    src = annotated_folder(tmp_path / "frames", count=3)
    out = tmp_path / "dataset"
    conv.main(["--input", str(src), "--output", str(out), "--heatmap-format", "png"])
    heatmaps = sorted((out / "heatmaps").iterdir())
    assert all(p.suffix == ".png" for p in heatmaps)
    with Image.open(heatmaps[0]) as image:
        assert max(image.getdata()) == 255  # exact Gaussian peak preserved


def test_missing_images_are_counted(tmp_path):
    src = annotated_folder(tmp_path / "frames", count=4)
    (src / "000002.jpg").unlink()
    out = tmp_path / "dataset"
    conv.main(["--input", str(src), "--output", str(out)])
    report = json.loads((out / "conversion_report.json").read_text(encoding="utf-8"))
    assert report["missing_images"] == 1


def test_missing_csv_is_a_usage_error(tmp_path):
    (tmp_path / "frames").mkdir()
    with pytest.raises(SystemExit) as info:
        conv.main(["--input", str(tmp_path / "frames"), "--output", str(tmp_path / "o")])
    assert info.value.code == 2


def test_heatmap_peak_position():
    image = conv.generate_heatmap(100, 50)
    assert image.getpixel((100, 50)) == 255
    assert image.getpixel((0, 0)) == 0
    assert conv.convert_coordinate(1280, 720, 1280, 720) == (639, 359)


def test_legacy_script_location_still_works(tmp_path):
    src = annotated_folder(tmp_path / "frames", count=3)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "convert_to_tracknet.py"),
         "--input", str(src), "--output", str(tmp_path / "out")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "training_model1.csv").exists()


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


@requires_ffmpeg
def test_cli_doctor_json(tmp_path):
    target = tmp_path / "report.json"
    code = cli_main(["doctor", "--json", str(target)])
    data = json.loads(target.read_text(encoding="utf-8"))
    assert code == 0 and data["ffmpeg_ok"] is True
    assert data["nvdec_state"] in {"verified", "failed", "unavailable", "untested"}
    assert data["gpu_pipeline_ready"] == (data["nvdec_state"] == "verified")


@requires_ffmpeg
def test_cli_extract_folder(media_dir, tmp_path, capsys):
    out = tmp_path / "frames"
    results = tmp_path / "results.json"
    code = cli_main(["extract", str(media_dir), str(out), "--mode", "cpu", "--json", str(results)])
    assert code == 0, capsys.readouterr().err
    data = json.loads(results.read_text(encoding="utf-8"))
    assert all(r["ok"] for r in data)
    assert {Path(r["output"]).name for r in data} >= {"clip h264", "estimate"}


@requires_ffmpeg
def test_cli_extract_reports_failures(bad_media_dir, tmp_path):
    assert cli_main(["extract", str(bad_media_dir), str(tmp_path / "o"), "--mode", "cpu"]) == 1


def test_cli_extract_missing_input(tmp_path):
    assert cli_main(["extract", str(tmp_path / "missing"), str(tmp_path / "o")]) == 2


def test_cli_convert_delegates(tmp_path):
    src = annotated_folder(tmp_path / "frames", count=3)
    assert cli_main(["convert-tracknet", "--input", str(src), "--output", str(tmp_path / "o")]) == 0


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as info:
        cli_main(["--version"])
    assert info.value.code == 0
    assert "2." in capsys.readouterr().out
