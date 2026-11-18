"""GUI behaviour, driven headlessly (QT_QPA_PLATFORM=offscreen).

Dialogs are replaced with recorders so tests never block.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from conftest import requires_ffmpeg, wait_until


@pytest.fixture
def silence_dialogs(monkeypatch):
    shown = []

    def record(kind, answer=QMessageBox.Yes):
        def fn(*args, **kwargs):
            shown.append((kind, args[2] if len(args) > 2 else ""))
            return answer
        return fn

    monkeypatch.setattr(QMessageBox, "warning", record("warning", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", record("critical", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", record("information", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", record("question", QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(("box", self.text())) or 0)
    return shown


@pytest.fixture
def window(qapp, silence_dialogs):
    from app.ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    wait_until(qapp, lambda: win.capabilities is not None, timeout=120)
    yield win
    win.close()
    qapp.processEvents()


def test_window_starts_and_reports_honest_acceleration(window):
    report = window.capabilities
    header = window.hardware_header.text()
    if report.gpu_pipeline_ready:
        assert "VERIFIED" in header
    else:
        assert "VERIFIED" not in header and "ACCELERATION" not in header.replace(
            "CHECKING ACCELERATION", ""
        )
    assert window.mode_combo.count() == 3


@requires_ffmpeg
def test_full_export_through_gui(qapp, window, media_dir, tmp_path):
    out = tmp_path / "gui out"
    out.mkdir()
    window.input_directory = str(media_dir)
    window.output_directory = str(out)
    from app.processing.scanner import DatasetScanner

    window.dataset_info = DatasetScanner().scan(str(media_dir))
    window.mode_combo.setCurrentIndex(0)  # AUTO
    window.start_export()
    assert window.worker is not None
    wait_until(qapp, lambda: window.worker is None, timeout=240)
    assert window.start_button.isEnabled()
    assert window.progress_card.value_label.text() == "100%"
    for video in window.dataset_info.videos:
        assert (out / video.stem / ".complete").exists(), video.name
    assert window.pipeline_label.text().startswith("Pipeline:")


@requires_ffmpeg
def test_failed_video_does_not_stop_batch(qapp, window, media_dir, bad_media_dir, tmp_path,
                                          silence_dialogs):
    src = tmp_path / "mixed"
    src.mkdir()
    shutil.copy(media_dir / "clip h264.mp4", src / "a_good.mp4")
    shutil.copy(bad_media_dir / "text.mp4", src / "b_bad.mp4")
    shutil.copy(media_dir / "mjpeg.mov", src / "c_good.mov")
    out = tmp_path / "out"
    window.input_directory = str(src)
    window.output_directory = str(out)
    from app.processing.scanner import DatasetScanner

    window.dataset_info = DatasetScanner().scan(str(src))
    window.mode_combo.setCurrentIndex(2)  # CPU
    window.start_export()
    wait_until(qapp, lambda: window.worker is None, timeout=180)
    assert (out / "a_good" / ".complete").exists()
    assert (out / "c_good" / ".complete").exists()
    assert "b_bad.mp4" in window.failed_videos
    assert any(kind == "box" and "1 could not be processed" in text
               for kind, text in silence_dialogs)


@pytest.fixture(scope="module")
def slow_video_dir(tmp_path_factory):
    from conftest import has_encoder, make_video

    root = tmp_path_factory.mktemp("slow")
    codec = "libx264" if has_encoder("libx264") else "mpeg4"
    make_video(root / "long one.mp4", size="1280x720", rate=50, seconds=30, codec=codec,
               extra=["-g", "50"] + (["-preset", "ultrafast"] if codec == "libx264" else []))
    return root


def _start(window, src, out, mode_index=2):
    from app.processing.scanner import DatasetScanner

    window.input_directory = str(src)
    window.output_directory = str(out)
    window.dataset_info = DatasetScanner().scan(str(src))
    window.mode_combo.setCurrentIndex(mode_index)
    window.start_export()


@requires_ffmpeg
def test_pause_and_resume_through_gui(qapp, window, slow_video_dir, tmp_path):
    out = tmp_path / "out"
    target = out / "long one"
    _start(window, slow_video_dir, out)
    wait_until(qapp, lambda: len(list(target.glob("*.jpg"))) > 50, timeout=60)
    window.toggle_pause()
    wait_until(qapp, lambda: window.pause_button.text() == "RESUME EXPORT", timeout=30)
    assert not window.worker.isRunning()
    paused_frames = len(list(target.glob("*.jpg")))
    assert 0 < paused_frames < 1500
    window.toggle_pause()  # RESUME
    wait_until(qapp, lambda: window.worker is None, timeout=240)
    assert (target / ".complete").exists()
    assert len(list(target.glob("*.jpg"))) == 1500


@requires_ffmpeg
def test_cancel_delete_while_paused(qapp, window, slow_video_dir, tmp_path, monkeypatch):
    """Regression: CANCEL & DELETE after PAUSE was a silent no-op in v2.0."""
    out = tmp_path / "out"
    target = out / "long one"
    _start(window, slow_video_dir, out)
    wait_until(qapp, lambda: len(list(target.glob("*.jpg"))) > 20, timeout=60)
    window.toggle_pause()
    wait_until(qapp, lambda: window.pause_button.text() == "RESUME EXPORT", timeout=30)

    class FakeDialog:
        def __init__(self, *a, **k):
            self.buttons = []

        def setWindowTitle(self, *a): pass
        def setText(self, *a): pass

        def addButton(self, text, role):
            self.buttons.append(text)
            return text

        def exec(self): pass

        def clickedButton(self):
            return "CANCEL & DELETE"

    import app.ui.main_window as mw

    monkeypatch.setattr(mw, "QMessageBox", type("MB", (), {
        **{k: getattr(QMessageBox, k) for k in ("Yes", "No", "AcceptRole", "DestructiveRole",
                                               "RejectRole")},
        "question": staticmethod(lambda *a, **k: QMessageBox.Yes),
        "__new__": lambda cls, *a, **k: FakeDialog(),
    }))
    window.show_cancel_options()
    assert not target.exists()
    assert window.start_button.isEnabled()
    assert window.worker is None and window.job_id is None


def test_start_without_directories_warns(window, silence_dialogs):
    window.start_export()
    assert silence_dialogs and silence_dialogs[0][0] == "warning"
    assert window.worker is None


def test_output_equal_to_input_rejected(window, tmp_path, silence_dialogs):
    window.input_directory = str(tmp_path)
    assert "different from the input" in window._output_directory_problem(tmp_path)


# ----------------------------------------------------------------------
# Annotation tab
# ----------------------------------------------------------------------


@pytest.fixture
def frames_dir(tmp_path):
    root = tmp_path / "frames dir"
    root.mkdir()
    for n in range(1, 31):
        Image.new("RGB", (320, 180), (n * 5, 0, 0)).save(root / f"{n:06d}.jpg", "JPEG")
    return root


@pytest.fixture
def tab(qapp, window, frames_dir):
    annotation = window.annotation_tab
    window.tabs.setCurrentWidget(annotation)
    annotation.frame_directory = frames_dir
    annotation.load_frames()
    qapp.processEvents()
    return annotation


def press(widget, key, modifiers=Qt.NoModifier):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key, modifiers))


def test_keyboard_shortcuts_restored(tab):
    """Regression: documented ←/→/Shift/Space shortcuts were lost in v2.0."""
    viewer = tab.image_viewer
    assert tab.current_index == 0
    press(viewer, Qt.Key_Right)
    assert tab.current_index == 1
    press(viewer, Qt.Key_Right, Qt.ShiftModifier)
    assert tab.current_index == 11
    press(viewer, Qt.Key_Left)
    assert tab.current_index == 10
    press(viewer, Qt.Key_Space)
    assert tab.play_button.isChecked()
    press(viewer, Qt.Key_Space)
    assert not tab.play_button.isChecked()


def test_play_button_advances_frames(qapp, tab):
    """Regression: PLAY raised AttributeError (timer was None)."""
    tab.play_button.setChecked(True)
    wait_until(qapp, lambda: tab.current_index >= 3, timeout=10)
    tab.play_button.setChecked(False)


def test_click_annotate_save_and_csv(qapp, tab, frames_dir):
    tab.ball_clicked(100, 50)
    assert tab.has_unsaved_changes()
    tab.save_and_next()
    assert not tab.has_unsaved_changes()
    assert tab.current_index == 1
    tab.mark_occluded()
    tab.save_current()
    with open(frames_dir / "annotations.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["frame"] == "000001.jpg" and rows[0]["x"] == "100" and rows[0]["visibility"] == "1"
    assert rows[1]["status"] == "FULLY_OCCLUDED" and rows[1]["visibility"] == "0"
    assert not (frames_dir / "annotations.csv.tmp").exists()


def test_annotations_reload(qapp, tab, frames_dir):
    tab.ball_clicked(10, 20)
    tab.save_current()
    tab.load_frames()
    assert tab.annotations["000001.jpg"]["x"] == 10
    assert tab.current_index == 1  # first unannotated frame


def test_csv_table_refreshes_when_opened(qapp, tab):
    tab.ball_clicked(5, 5)
    tab.tabs.setCurrentWidget(tab.csv_page)
    qapp.processEvents()
    assert tab.csv_table.rowCount() == 1
    tab.tabs.setCurrentWidget(tab.ranges_page)
    assert tab.ranges_table.rowCount() >= 1


def test_empty_frame_folder_warns(tab, tmp_path, silence_dialogs):
    empty = tmp_path / "empty"
    empty.mkdir()
    previous = list(tab.frames)
    tab.frame_directory = empty
    tab.load_frames()
    assert tab.frames == previous
    assert any("No image frames" in text for _, text in silence_dialogs)
