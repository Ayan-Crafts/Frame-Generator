from pathlib import Path
import csv

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QFrame,
    QMessageBox,
    QProgressBar,
)


class AnnotationImage(QLabel):
    """
    Displays the current frame and converts mouse clicks
    from displayed coordinates back to original image coordinates.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(700, 450)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            """
            QLabel {
                background: #020617;
                border: 1px solid #263244;
                border-radius: 8px;
            }
            """
        )

        self.original_pixmap = None
        self.displayed_pixmap = None

        self.image_x = 0
        self.image_y = 0
        self.image_width = 0
        self.image_height = 0

        self.ball_x = None
        self.ball_y = None

    def set_frame(self, pixmap, ball_x=None, ball_y=None):
        self.original_pixmap = pixmap
        self.ball_x = ball_x
        self.ball_y = ball_y

        self.update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_display()

    def update_display(self):
        if self.original_pixmap is None:
            self.clear()
            return

        scaled = self.original_pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        self.displayed_pixmap = scaled

        self.image_width = scaled.width()
        self.image_height = scaled.height()

        self.image_x = (
            self.width() - self.image_width
        ) // 2

        self.image_y = (
            self.height() - self.image_height
        ) // 2

        canvas = QPixmap(self.size())
        canvas.fill(Qt.black)

        painter = QPainter(canvas)

        painter.drawPixmap(
            self.image_x,
            self.image_y,
            scaled,
        )

        if (
            self.ball_x is not None
            and self.ball_y is not None
        ):
            original_width = (
                self.original_pixmap.width()
            )

            original_height = (
                self.original_pixmap.height()
            )

            display_x = (
                self.ball_x
                * self.image_width
                / original_width
            )

            display_y = (
                self.ball_y
                * self.image_height
                / original_height
            )

            draw_x = (
                self.image_x + display_x
            )

            draw_y = (
                self.image_y + display_y
            )

            pen = QPen(
                Qt.red,
                3,
            )

            painter.setPen(pen)

            painter.drawEllipse(
                int(draw_x - 7),
                int(draw_y - 7),
                14,
                14,
            )

            painter.drawLine(
                int(draw_x - 12),
                int(draw_y),
                int(draw_x + 12),
                int(draw_y),
            )

            painter.drawLine(
                int(draw_x),
                int(draw_y - 12),
                int(draw_x),
                int(draw_y + 12),
            )

        painter.end()

        self.setPixmap(canvas)

    def mousePressEvent(self, event):
        if (
            self.original_pixmap is None
            or self.displayed_pixmap is None
        ):
            return

        if event.button() != Qt.LeftButton:
            return

        x = event.position().x()
        y = event.position().y()

        # Ignore clicks outside the actual image.
        if not (
            self.image_x
            <= x
            <= self.image_x + self.image_width
        ):
            return

        if not (
            self.image_y
            <= y
            <= self.image_y + self.image_height
        ):
            return

        relative_x = (
            x - self.image_x
        )

        relative_y = (
            y - self.image_y
        )

        original_width = (
            self.original_pixmap.width()
        )

        original_height = (
            self.original_pixmap.height()
        )

        self.ball_x = int(
            relative_x
            * original_width
            / self.image_width
        )

        self.ball_y = int(
            relative_y
            * original_height
            / self.image_height
        )

        self.update_display()

        parent = self.parent()

        while parent is not None:
            if hasattr(
                parent,
                "ball_clicked",
            ):
                parent.ball_clicked(
                    self.ball_x,
                    self.ball_y,
                )
                break

            parent = parent.parent()


class AnnotationTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.frame_directory = None
        self.frames = []

        self.current_index = 0

        self.annotations = {}

        self.csv_path = None

        self.build_ui()

    # ==================================================
    # UI
    # ==================================================

    def build_ui(self):

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        main_layout.setSpacing(12)

        # ----------------------------------------------
        # Header
        # ----------------------------------------------

        header = QHBoxLayout()

        title = QLabel(
            "TRACKNET ANNOTATION"
        )

        title.setStyleSheet(
            """
            QLabel {
                font-size: 18pt;
                font-weight: 800;
                color: #f8fafc;
            }
            """
        )

        header.addWidget(title)

        header.addStretch()

        self.folder_button = QPushButton(
            "SELECT FRAME DIRECTORY"
        )

        self.folder_button.clicked.connect(
            self.select_directory
        )

        header.addWidget(
            self.folder_button
        )

        main_layout.addLayout(header)

        # ----------------------------------------------
        # Statistics
        # ----------------------------------------------

        stats = QGridLayout()

        stats.setSpacing(10)

        self.total_card = self.create_card(
            "TOTAL FRAMES",
            "0",
            "frames loaded",
        )

        self.annotated_card = self.create_card(
            "ANNOTATED",
            "0",
            "frames labeled",
        )

        self.remaining_card = self.create_card(
            "REMAINING",
            "0",
            "frames remaining",
        )

        self.progress_card = self.create_card(
            "PROGRESS",
            "0%",
            "annotation progress",
        )

        stats.addWidget(
            self.total_card,
            0,
            0,
        )

        stats.addWidget(
            self.annotated_card,
            0,
            1,
        )

        stats.addWidget(
            self.remaining_card,
            0,
            2,
        )

        stats.addWidget(
            self.progress_card,
            0,
            3,
        )

        main_layout.addLayout(stats)

        # ----------------------------------------------
        # Image
        # ----------------------------------------------

        self.image_viewer = AnnotationImage(
            self
        )

        main_layout.addWidget(
            self.image_viewer,
            1,
        )

        # ----------------------------------------------
        # Current frame information
        # ----------------------------------------------

        info = QGridLayout()

        self.frame_label = QLabel(
            "Frame: --"
        )

        self.status_label = QLabel(
            "Status: No annotation"
        )

        self.coordinate_label = QLabel(
            "X: --    Y: --"
        )

        for label in (
            self.frame_label,
            self.status_label,
            self.coordinate_label,
        ):
            label.setStyleSheet(
                """
                QLabel {
                    background: #111827;
                    border: 1px solid #263244;
                    border-radius: 7px;
                    padding: 9px;
                    color: #e5e7eb;
                    font-weight: 600;
                }
                """
            )

        info.addWidget(
            self.frame_label,
            0,
            0,
        )

        info.addWidget(
            self.status_label,
            0,
            1,
        )

        info.addWidget(
            self.coordinate_label,
            0,
            2,
        )

        main_layout.addLayout(info)

        # ----------------------------------------------
        # Annotation buttons
        # ----------------------------------------------

        annotation_buttons = QHBoxLayout()

        self.visible_button = QPushButton(
            "BALL VISIBLE"
        )

        self.visible_button.clicked.connect(
            self.mark_visible
        )

        self.not_visible_button = QPushButton(
            "NOT VISIBLE"
        )

        self.not_visible_button.clicked.connect(
            self.mark_not_visible
        )

        self.occluded_button = QPushButton(
            "OCCLUDED"
        )

        self.occluded_button.clicked.connect(
            self.mark_occluded
        )

        annotation_buttons.addWidget(
            self.visible_button
        )

        annotation_buttons.addWidget(
            self.not_visible_button
        )

        annotation_buttons.addWidget(
            self.occluded_button
        )

        main_layout.addLayout(
            annotation_buttons
        )

        # ----------------------------------------------
        # Navigation
        # ----------------------------------------------

        navigation = QHBoxLayout()

        self.previous_button = QPushButton(
            "← PREVIOUS"
        )

        self.previous_button.clicked.connect(
            self.previous_frame
        )

        self.save_button = QPushButton(
            "SAVE ANNOTATION"
        )

        self.save_button.clicked.connect(
            self.save_current
        )

        self.next_button = QPushButton(
            "NEXT →"
        )

        self.next_button.clicked.connect(
            self.next_frame
        )

        navigation.addWidget(
            self.previous_button
        )

        navigation.addWidget(
            self.save_button
        )

        navigation.addWidget(
            self.next_button
        )

        main_layout.addLayout(
            navigation
        )

        # ----------------------------------------------
        # Progress
        # ----------------------------------------------

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100,
        )

        self.progress_bar.setValue(
            0
        )

        main_layout.addWidget(
            self.progress_bar
        )

        self.setStyleSheet(
            """
            QWidget {
                background: #0f172a;
                color: #e5e7eb;
                font-family: Segoe UI;
                font-size: 10pt;
            }

            QPushButton {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 10px 16px;
                color: #f8fafc;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #273449;
            }
            """
        )

        self.update_buttons()

    # ==================================================
    # STAT CARD
    # ==================================================

    def create_card(
        self,
        title,
        value,
        subtitle,
    ):

        frame = QFrame()

        frame.setStyleSheet(
            """
            QFrame {
                background: #111827;
                border: 1px solid #263244;
                border-radius: 10px;
                min-height: 85px;
            }
            """
        )

        layout = QVBoxLayout(frame)

        title_label = QLabel(title)

        title_label.setStyleSheet(
            """
            color: #94a3b8;
            font-size: 9pt;
            font-weight: 600;
            """
        )

        value_label = QLabel(value)

        value_label.setStyleSheet(
            """
            color: #f8fafc;
            font-size: 20pt;
            font-weight: 700;
            """
        )

        subtitle_label = QLabel(
            subtitle
        )

        subtitle_label.setStyleSheet(
            """
            color: #64748b;
            font-size: 8pt;
            """
        )

        layout.addWidget(
            title_label
        )

        layout.addWidget(
            value_label
        )

        layout.addWidget(
            subtitle_label
        )

        frame.value_label = value_label

        return frame

    def set_card(
        self,
        card,
        value,
    ):

        card.value_label.setText(
            str(value)
        )

    # ==================================================
    # SELECT DIRECTORY
    # ==================================================

    def select_directory(self):

        directory = (
            QFileDialog.getExistingDirectory(
                self,
                "Select Frame Directory",
            )
        )

        if not directory:
            return

        self.frame_directory = Path(
            directory
        )

        self.load_frames()

    # ==================================================
    # LOAD FRAMES
    # ==================================================

    def load_frames(self):

        self.frames = sorted(
            [
                path
                for path in
                self.frame_directory.iterdir()
                if path.is_file()
                and path.suffix.lower()
                in {
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".bmp",
                }
            ],
            key=lambda p: p.name,
        )

        if not self.frames:
            QMessageBox.warning(
                self,
                "Annotation",
                "No image frames were found.",
            )

            return

        self.csv_path = (
            self.frame_directory
            / "annotations.csv"
        )

        self.load_annotations()

        self.current_index = 0

        self.update_statistics()

        self.show_current_frame()

    # ==================================================
    # LOAD EXISTING CSV
    # ==================================================

    def load_annotations(self):

        self.annotations = {}

        if not self.csv_path.exists():
            return

        try:

            with open(
                self.csv_path,
                "r",
                newline="",
                encoding="utf-8",
            ) as file:

                reader = csv.DictReader(
                    file
                )

                for row in reader:

                    frame = row[
                        "frame"
                    ]

                    visibility = int(
                        row["visibility"]
                    )

                    x = int(
                        row["x"]
                    )

                    y = int(
                        row["y"]
                    )

                    self.annotations[
                        frame
                    ] = {
                        "visibility":
                            visibility,
                        "x": x,
                        "y": y,
                    }

        except Exception as error:

            QMessageBox.warning(
                self,
                "Annotation",
                f"Could not load annotations:\n{error}",
            )

    # ==================================================
    # SAVE CSV
    # ==================================================

    def save_annotations(self):

        if not self.csv_path:
            return

        try:

            with open(
                self.csv_path,
                "w",
                newline="",
                encoding="utf-8",
            ) as file:

                writer = csv.writer(
                    file
                )

                writer.writerow(
                    [
                        "frame",
                        "visibility",
                        "x",
                        "y",
                    ]
                )

                for frame in self.frames:

                    if frame.name not in self.annotations:
                        continue

                    annotation = (
                        self.annotations[
                            frame.name
                        ]
                    )

                    writer.writerow(
                        [
                            frame.name,
                            annotation[
                                "visibility"
                            ],
                            annotation["x"],
                            annotation["y"],
                        ]
                    )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Annotation",
                f"Could not save annotations:\n{error}",
            )

    # ==================================================
    # CURRENT FRAME
    # ==================================================

    def show_current_frame(self):

        if not self.frames:
            return

        frame_path = self.frames[
            self.current_index
        ]

        pixmap = QPixmap(
            str(frame_path)
        )

        if pixmap.isNull():

            self.status_label.setText(
                "Status: Failed to load frame"
            )

            return

        annotation = self.annotations.get(
            frame_path.name
        )

        if annotation:

            x = annotation["x"]
            y = annotation["y"]

        else:

            x = None
            y = None

        self.image_viewer.set_frame(
            pixmap,
            x,
            y,
        )

        self.frame_label.setText(
            f"Frame: "
            f"{self.current_index + 1:,} / "
            f"{len(self.frames):,} "
            f"({frame_path.name})"
        )

        if annotation:

            visibility = annotation[
                "visibility"
            ]

            if visibility == 1:
                status = "BALL VISIBLE"

            elif visibility == 2:
                status = "OCCLUDED"

            else:
                status = "NOT VISIBLE"

            self.status_label.setText(
                f"Status: {status}"
            )

            self.coordinate_label.setText(
                f"X: {x}    Y: {y}"
            )

        else:

            self.status_label.setText(
                "Status: NOT ANNOTATED"
            )

            self.coordinate_label.setText(
                "X: --    Y: --"
            )

        self.update_buttons()

    # ==================================================
    # BALL CLICK
    # ==================================================

    def ball_clicked(
        self,
        x,
        y,
    ):

        frame = self.frames[
            self.current_index
        ]

        self.annotations[
            frame.name
        ] = {
            "visibility": 1,
            "x": x,
            "y": y,
        }

        self.status_label.setText(
            "Status: BALL VISIBLE"
        )

        self.coordinate_label.setText(
            f"X: {x}    Y: {y}"
        )

        self.save_annotations()

        self.update_statistics()

    # ==================================================
    # MARK VISIBLE
    # ==================================================

    def mark_visible(self):

        frame = self.frames[
            self.current_index
        ]

        annotation = self.annotations.get(
            frame.name
        )

        if not annotation:

            QMessageBox.information(
                self,
                "Ball Position",
                "Click on the ball first.",
            )

            return

        annotation[
            "visibility"
        ] = 1

        self.save_annotations()

        self.show_current_frame()

        self.update_statistics()

    # ==================================================
    # NOT VISIBLE
    # ==================================================

    def mark_not_visible(self):

        frame = self.frames[
            self.current_index
        ]

        self.annotations[
            frame.name
        ] = {
            "visibility": 0,
            "x": -1,
            "y": -1,
        }

        self.save_annotations()

        self.show_current_frame()

        self.update_statistics()

    # ==================================================
    # OCCLUDED
    # ==================================================

    def mark_occluded(self):

        frame = self.frames[
            self.current_index
        ]

        annotation = self.annotations.get(
            frame.name
        )

        if not annotation:

            QMessageBox.information(
                self,
                "Ball Position",
                "Click on the ball first "
                "if you can identify its position.",
            )

            return

        annotation[
            "visibility"
        ] = 2

        self.save_annotations()

        self.show_current_frame()

        self.update_statistics()

    # ==================================================
    # SAVE CURRENT
    # ==================================================

    def save_current(self):

        self.save_annotations()

        self.update_statistics()

    # ==================================================
    # NEXT
    # ==================================================

    def next_frame(self):

        if not self.frames:
            return

        if (
            self.current_index
            < len(self.frames) - 1
        ):

            self.current_index += 1

            self.show_current_frame()

    # ==================================================
    # PREVIOUS
    # ==================================================

    def previous_frame(self):

        if not self.frames:
            return

        if self.current_index > 0:

            self.current_index -= 1

            self.show_current_frame()

    # ==================================================
    # STATISTICS
    # ==================================================

    def update_statistics(self):

        total = len(
            self.frames
        )

        annotated = len(
            self.annotations
        )

        remaining = max(
            0,
            total - annotated,
        )

        if total:

            percentage = (
                annotated
                / total
                * 100
            )

        else:

            percentage = 0

        self.set_card(
            self.total_card,
            f"{total:,}",
        )

        self.set_card(
            self.annotated_card,
            f"{annotated:,}",
        )

        self.set_card(
            self.remaining_card,
            f"{remaining:,}",
        )

        self.set_card(
            self.progress_card,
            f"{percentage:.1f}%",
        )

        self.progress_bar.setValue(
            int(percentage)
        )

    # ==================================================
    # BUTTON STATE
    # ==================================================

    def update_buttons(self):

        enabled = bool(
            self.frames
        )

        self.previous_button.setEnabled(
            enabled
            and self.current_index > 0
        )

        self.next_button.setEnabled(
            enabled
            and self.current_index
            < len(self.frames) - 1
        )

        self.visible_button.setEnabled(
            enabled
        )

        self.not_visible_button.setEnabled(
            enabled
        )

        self.occluded_button.setEnabled(
            enabled
        )

        self.save_button.setEnabled(
            enabled
        )