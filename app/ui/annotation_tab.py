from pathlib import Path
import csv
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QFont
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QScrollArea,
    QComboBox,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QLineEdit,
    QSlider,
    QSpinBox,
    QSizePolicy,
    QAbstractItemView,
)


CSV_COLUMNS = [
    "frame",
    "x",
    "y",
    "visibility",
    "x1",
    "y1",
    "x2",
    "y2",
    "source",
    "confidence",
    "status",
]

STATUS_ACCEPTED = "ACCEPTED"
STATUS_REVIEW = "LOW_CONFIDENCE"
STATUS_OCCLUDED = "FULLY_OCCLUDED"
STATUS_OOB = "OUT_OF_BOUNDS"
STATUS_SEVERE_BLUR = "SEVERE_MOTION_BLUR"


class AnnotationImage(QWidget):
    """Dedicated frame canvas. Controls are never placed inside this widget."""

    ball_clicked = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumSize(0, 220)
        self.setStyleSheet(
            """
            QWidget {
                background: #020617;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            """
        )
        self.original_pixmap = None
        self.image_x = 0
        self.image_y = 0
        self.image_width = 0
        self.image_height = 0
        self.ball_x = None
        self.ball_y = None
        self.visibility = 0
        self.box = None
        self.jump_frames = lambda amount: None
        self.play_button = None
        self.save_next_button = None
        self.save_and_next = lambda: None

    def set_frame(self, pixmap, ball_x=None, ball_y=None, visibility=0, box=None):
        self.original_pixmap = pixmap
        self.ball_x = ball_x
        self.ball_y = ball_y
        self.visibility = visibility
        self.box = box
        self.updateGeometry()
        self.update()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        if self.original_pixmap is not None and not self.original_pixmap.isNull() and self.original_pixmap.width() > 0:
            ratio = self.original_pixmap.height() / self.original_pixmap.width()
            return max(220, int(width * ratio) + 2)
        return 360

    def sizeHint(self):
        if self.original_pixmap is not None and not self.original_pixmap.isNull():
            w = max(640, self.original_pixmap.width())
            return QSize(w, self.heightForWidth(w))
        return QSize(960, 540)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#020617"))

        if self.original_pixmap is None or self.original_pixmap.isNull():
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignCenter, "NO FRAME LOADED")
            painter.end()
            return

        scaled = self.original_pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_width = scaled.width()
        self.image_height = scaled.height()
        self.image_x = (self.width() - self.image_width) // 2
        self.image_y = (self.height() - self.image_height) // 2

        painter.drawPixmap(self.image_x, self.image_y, scaled)

        scale_x = self.image_width / self.original_pixmap.width()
        scale_y = self.image_height / self.original_pixmap.height()

        if self.box:
            x1, y1, x2, y2 = self.box
            rect_x = self.image_x + int(x1 * scale_x)
            rect_y = self.image_y + int(y1 * scale_y)
            rect_w = max(1, int((x2 - x1) * scale_x))
            rect_h = max(1, int((y2 - y1) * scale_y))
            painter.setPen(QPen(QColor("#38bdf8"), 2))
            painter.drawRect(rect_x, rect_y, rect_w, rect_h)

        if self.ball_x is not None and self.ball_y is not None:
            cx = self.image_x + int(self.ball_x * scale_x)
            cy = self.image_y + int(self.ball_y * scale_y)
            painter.setPen(QPen(QColor("#22c55e"), 3))
            painter.setBrush(QBrush(QColor("#22c55e")))
            painter.drawEllipse(cx - 6, cy - 6, 12, 12)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawLine(cx - 14, cy, cx + 14, cy)
            painter.drawLine(cx, cy - 14, cx, cy + 14)

        painter.end()

    def mousePressEvent(self, event):
        """Convert a click on the displayed image back to original frame coordinates."""
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        if self.original_pixmap is None or self.original_pixmap.isNull():
            return

        # Ignore clicks outside the actual displayed image.
        px = event.position().x()
        py = event.position().y()
        if (px < self.image_x or py < self.image_y or
                px >= self.image_x + self.image_width or
                py >= self.image_y + self.image_height):
            return

        if self.image_width <= 0 or self.image_height <= 0:
            return

        # Map displayed coordinates to original image coordinates.
        x = int(round((px - self.image_x) * self.original_pixmap.width() / self.image_width))
        y = int(round((py - self.image_y) * self.original_pixmap.height() / self.image_height))

        x = max(0, min(self.original_pixmap.width() - 1, x))
        y = max(0, min(self.original_pixmap.height() - 1, y))

        self.ball_x = x
        self.ball_y = y
        self.visibility = 1
        self.update()
        self.ball_clicked.emit(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


class MetricCard(QFrame):
    """Compact statistics card used by the Statistics tab."""

    def __init__(self, title, value="0", parent=None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(82)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)

        self.title_label = QLabel(str(title))
        self.title_label.setStyleSheet(
            "color: #94a3b8; font-size: 12px; font-weight: 600;"
        )
        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            "color: #f8fafc; font-size: 24px; font-weight: 700;"
        )
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

        self.setStyleSheet(
            """
            QFrame#MetricCard {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            """
        )

    def set_value(self, value):
        self.value_label.setText(str(value))


class AnnotationTab(QWidget):
    """Complete TrackNet annotation workspace."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.frame_directory = None
        self.frames = []
        self.annotations = {}
        self.current_index = 0
        self.csv_path = None

        self.pending_visibility_mode = None
        self.autosave_enabled = False
        self._play_timer = None
        self._updating_slider = False
        self._loading_directory = False

        self.build_ui()

    def build_ui(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #0f172a;
                color: #e5e7eb;
                font-family: Segoe UI;
                font-size: 10pt;
            }
            QFrame#metricCard, QFrame#panel {
                background: #111827;
                border: 1px solid #263244;
                border-radius: 10px;
            }
            QLabel#metricTitle {
                color: #94a3b8;
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#metricValue {
                color: #f8fafc;
                font-size: 18pt;
                font-weight: 800;
            }
            QLabel#metricSubtitle {
                color: #64748b;
                font-size: 8pt;
            }
            QLabel#sectionTitle {
                color: #f8fafc;
                font-size: 11pt;
                font-weight: 800;
            }
            QLabel#metricName {
                color: #94a3b8;
                font-weight: 600;
            }
            QLabel#metricData {
                color: #f8fafc;
                font-weight: 700;
            }
            QLabel#statusGood {
                background: #052e16;
                color: #4ade80;
                border: 1px solid #166534;
                border-radius: 7px;
                padding: 8px;
                font-weight: 800;
            }
            QLabel#statusWarn {
                background: #422006;
                color: #fbbf24;
                border: 1px solid #92400e;
                border-radius: 7px;
                padding: 8px;
                font-weight: 800;
            }
            QLabel#statusBad {
                background: #450a0a;
                color: #f87171;
                border: 1px solid #991b1b;
                border-radius: 7px;
                padding: 8px;
                font-weight: 800;
            }
            QLabel#statusNeutral {
                background: #0b1220;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 8px;
                font-weight: 700;
            }
            QPushButton {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 9px 14px;
                color: #f8fafc;
                font-weight: 700;
            }
            QPushButton:hover { background: #273449; }
            QPushButton:disabled {
                background: #111827;
                color: #475569;
                border-color: #1e293b;
            }
            QPushButton#primary {
                background: #16a34a;
                border: none;
            }
            QPushButton#primary:hover { background: #15803d; }
            QPushButton#danger {
                background: #991b1b;
                border: none;
            }
            QTabWidget::pane {
                border: 1px solid #263244;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #111827;
                color: #94a3b8;
                padding: 9px 18px;
                border: 1px solid #263244;
            }
            QTabBar::tab:selected {
                background: #1e293b;
                color: #f8fafc;
            }
            QTableWidget {
                background: #0b1220;
                color: #e5e7eb;
                gridline-color: #263244;
                border: 1px solid #263244;
                border-radius: 7px;
            }
            QHeaderView::section {
                background: #111827;
                color: #cbd5e1;
                padding: 7px;
                border: 1px solid #263244;
                font-weight: 700;
            }
            QProgressBar {
                background: #0b1220;
                border: 1px solid #263244;
                border-radius: 6px;
                height: 18px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #22c55e;
                border-radius: 5px;
            }
            QComboBox, QDoubleSpinBox {
                background: #0b1220;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px;
            }
            QCheckBox { color: #cbd5e1; }
            QLabel#frameFileLabel {
                background: #0b1220;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 10px;
                color: #f8fafc;
                font-weight: 700;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("TRACKNET ANNOTATION TOOL")
        title.setStyleSheet("font-size: 18pt; font-weight: 800; color: #f8fafc;")
        header.addWidget(title)
        header.addStretch()

        self.dataset_label = QLabel("No frame directory selected")
        self.dataset_label.setObjectName("statusNeutral")
        header.addWidget(self.dataset_label, 1)

        self.folder_button = QPushButton("SELECT FRAME DIRECTORY")
        self.folder_button.clicked.connect(self.select_directory)
        header.addWidget(self.folder_button)
        root.addLayout(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.annotating_page = QWidget()
        self.csv_page = QWidget()
        self.ranges_page = QWidget()
        self.stats_page = QWidget()
        self.settings_page = QWidget()

        self.tabs.addTab(self.annotating_page, "ANNOTATING")
        self.tabs.addTab(self.csv_page, "CSV")
        self.tabs.addTab(self.ranges_page, "RANGES")
        self.tabs.addTab(self.stats_page, "STATISTICS")
        self.tabs.addTab(self.settings_page, "SETTINGS")

        self.build_annotating_page()
        self.build_csv_page()
        self.build_ranges_page()
        self.build_stats_page()
        self.build_settings_page()

        self.update_all()

    # ------------------------------------------------------------------
    # Annotating page
    # ------------------------------------------------------------------

    def build_annotating_page(self):
        """Scrollable, image-first annotation workspace.

        The complete source frame is always rendered with KeepAspectRatio.
        All controls live below the image, never over it. The page itself is
        vertically scrollable so the full image can be shown at a useful size
        even when the display is not tall enough for the image plus controls.
        """
        outer = QVBoxLayout(self.annotating_page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: #0f172a; border: none; }")
        outer.addWidget(scroll)
        self.annotation_scroll = scroll

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 12)
        layout.setSpacing(7)
        scroll.setWidget(content)

        # Compact top status.
        progress_row = QHBoxLayout()
        self.annotation_progress_label = QLabel(
            "FRAME -- / --   •   ANNOTATED 0   •   REMAINING 0"
        )
        self.annotation_progress_label.setObjectName("statusNeutral")
        progress_row.addWidget(self.annotation_progress_label, 1)
        self.annotation_percent_label = QLabel("0.0%")
        self.annotation_percent_label.setStyleSheet(
            "font-size: 10pt; font-weight: 800; color: #f8fafc;"
        )
        progress_row.addWidget(self.annotation_percent_label)
        layout.addLayout(progress_row)

        # FULL IMAGE AREA. Its height follows the source image aspect ratio.
        image_frame = QFrame()
        image_frame.setObjectName("imageFrame")
        image_frame.setStyleSheet(
            "QFrame#imageFrame { background: #020617; border: 1px solid #334155; border-radius: 8px; }"
        )
        image_layout = QVBoxLayout(image_frame)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        self.image_viewer = AnnotationImage()
        self.image_viewer.ball_clicked.connect(self.ball_clicked)
        self.image_viewer.setMinimumWidth(640)
        image_layout.addWidget(self.image_viewer)
        layout.addWidget(image_frame, 0)

        # Frame identity/navigation is BELOW the complete image.
        nav_info = QHBoxLayout()
        self.frame_file_label = QLabel("FILE: --")
        self.frame_file_label.setObjectName("frameFileLabel")
        self.frame_file_label.setMinimumHeight(32)
        nav_info.addWidget(self.frame_file_label, 1)
        self.frame_counter_label = QLabel("FRAME: -- / --")
        self.frame_counter_label.setObjectName("statusNeutral")
        self.frame_counter_label.setAlignment(Qt.AlignCenter)
        self.frame_counter_label.setMinimumHeight(32)
        nav_info.addWidget(self.frame_counter_label)
        layout.addLayout(nav_info)

        fast_nav = QHBoxLayout()
        fast_nav.setSpacing(5)
        self.jump_back_button = QPushButton("◀◀ 10")
        self.jump_back_button.clicked.connect(lambda: self.jump_frames(-10))
        self.prev_fast_button = QPushButton("◀ 1")
        self.prev_fast_button.clicked.connect(self.previous_frame)
        self.frame_number_input = QLineEdit()
        self.frame_number_input.setPlaceholderText("FRAME #")
        self.frame_number_input.setAlignment(Qt.AlignCenter)
        self.frame_number_input.setMinimumWidth(80)
        self.frame_number_input.setMaximumWidth(110)
        self.frame_number_input.returnPressed.connect(self.go_to_frame_from_input)
        self.next_fast_button = QPushButton("1 ▶")
        self.next_fast_button.clicked.connect(self.next_frame)
        self.jump_forward_button = QPushButton("10 ▶▶")
        self.jump_forward_button.clicked.connect(lambda: self.jump_frames(10))
        self.play_button = QPushButton("▶ PLAY")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self.toggle_play)
        for widget in (self.jump_back_button, self.prev_fast_button, self.frame_number_input,
                       self.next_fast_button, self.jump_forward_button, self.play_button):
            fast_nav.addWidget(widget)
        layout.addLayout(fast_nav)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)
        self.frame_slider.valueChanged.connect(self.slider_frame_changed)
        layout.addWidget(self.frame_slider)

        self.navigation_hint = QLabel(
            "Click the ball • ←/→ frame • Shift+←/→ ±10 • Space play"
        )
        self.navigation_hint.setObjectName("statusNeutral")
        self.navigation_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.navigation_hint)

        # Compact current-frame metrics. These are BELOW the image, not beside it.
        metrics_panel = QFrame()
        metrics_panel.setObjectName("panel")
        metrics_layout = QGridLayout(metrics_panel)
        metrics_layout.setContentsMargins(8, 6, 8, 6)
        metrics_layout.setHorizontalSpacing(14)
        metrics_layout.setVerticalSpacing(4)
        self.metric_labels = {}
        metric_names = [
            "Frame", "File", "X", "Y", "Visibility", "Visibility Flag",
            "Source", "Confidence", "Status", "Bounding Box", "Image Size",
        ]
        for i, name in enumerate(metric_names):
            row = i // 4
            col = (i % 4) * 2
            n = QLabel(name)
            n.setObjectName("metricName")
            v = QLabel("--")
            v.setObjectName("metricData")
            v.setWordWrap(True)
            self.metric_labels[name] = v
            metrics_layout.addWidget(n, row, col)
            metrics_layout.addWidget(v, row, col + 1)
        layout.addWidget(metrics_panel)

        self.current_status = QLabel("NOT ANNOTATED — CHOOSE A STATE OR CLICK THE BALL")
        self.current_status.setObjectName("statusNeutral")
        self.current_status.setAlignment(Qt.AlignCenter)
        self.current_status.setWordWrap(True)
        layout.addWidget(self.current_status)

        # Annotation state controls BELOW everything above.
        visibility_group = QGroupBox("ANNOTATION STATE")
        visibility_layout = QGridLayout(visibility_group)
        visibility_layout.setContentsMargins(6, 6, 6, 6)
        visibility_layout.setSpacing(6)

        self.visible_button = QPushButton("● VISIBLE")
        self.visible_button.setToolTip("Select VISIBLE, then click the ball center in the image.")
        self.visible_button.clicked.connect(self.mark_visible)
        self.partial_button = QPushButton("◐ PARTIALLY OCCLUDED")
        self.partial_button.setToolTip("Select PARTIAL, then click the estimated ball center.")
        self.partial_button.clicked.connect(self.mark_partial)
        self.occluded_button = QPushButton("✕ FULLY OCCLUDED")
        self.occluded_button.setToolTip("No click required. Saves x=0, y=0, visibility=0.")
        self.occluded_button.clicked.connect(self.mark_occluded)
        self.oob_button = QPushButton("↗ OUT OF BOUNDS")
        self.oob_button.setToolTip("No click required. Saves x=0, y=0, visibility=0.")
        self.oob_button.clicked.connect(self.mark_oob)
        self.blur_button = QPushButton("≈ SEVERE MOTION BLUR")
        self.blur_button.setToolTip(
            "No click required when the ball is visible but motion blur makes its center impossible to localize. "
            "This is stored as x=0, y=0, visibility=0 for TrackNet-safe labeling, with status SEVERE_MOTION_BLUR for later review."
        )
        self.blur_button.clicked.connect(self.mark_severe_motion_blur)
        self.clear_mark_button = QPushButton("CLEAR MARK")
        self.clear_mark_button.clicked.connect(self.clear_current_annotation)

        buttons = [
            self.visible_button, self.partial_button, self.occluded_button,
            self.oob_button, self.blur_button, self.clear_mark_button,
        ]
        for i, button in enumerate(buttons):
            visibility_layout.addWidget(button, i // 3, i % 3)
        layout.addWidget(visibility_group)

        bottom = QHBoxLayout()
        self.autosave_check = QCheckBox("AUTO-SAVE")
        self.autosave_check.setToolTip("Immediately write annotations to the CSV.")
        self.autosave_check.toggled.connect(self.set_autosave)
        bottom.addWidget(self.autosave_check)
        self.save_hint = QLabel("SAVE commits the current frame")
        self.save_hint.setObjectName("statusNeutral")
        bottom.addWidget(self.save_hint, 1)
        self.previous_button = QPushButton("◀ PREVIOUS")
        self.previous_button.clicked.connect(self.previous_frame)
        self.save_button = QPushButton("SAVE")
        self.save_button.clicked.connect(self.save_current)
        self.save_next_button = QPushButton("SAVE & NEXT ▶")
        self.save_next_button.setObjectName("primary")
        self.save_next_button.clicked.connect(self.save_and_next)
        self.next_button = QPushButton("NEXT ▶")
        self.next_button.clicked.connect(self.next_frame)
        for widget in (self.previous_button, self.save_button, self.save_next_button, self.next_button):
            bottom.addWidget(widget)
        layout.addLayout(bottom)

        self.image_viewer.jump_frames = self.jump_frames
        self.image_viewer.play_button = self.play_button
        self.image_viewer.save_next_button = self.save_next_button
        self.image_viewer.save_and_next = self.save_and_next

    # ------------------------------------------------------------------
    # CSV page
    # ------------------------------------------------------------------

    def build_csv_page(self):
        layout = QVBoxLayout(self.csv_page)
        toolbar = QHBoxLayout()

        self.csv_path_label = QLabel("CSV: --")
        self.csv_path_label.setObjectName("statusNeutral")
        toolbar.addWidget(self.csv_path_label, 1)

        refresh = QPushButton("REFRESH TABLE")
        refresh.clicked.connect(self.refresh_csv_table)
        toolbar.addWidget(refresh)

        save = QPushButton("SAVE CSV")
        save.clicked.connect(self.save_current)
        toolbar.addWidget(save)

        layout.addLayout(toolbar)

        self.csv_table = QTableWidget()
        self.csv_table.setColumnCount(len(CSV_COLUMNS))
        self.csv_table.setHorizontalHeaderLabels(CSV_COLUMNS)
        self.csv_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.csv_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.csv_table.cellDoubleClicked.connect(self.csv_row_clicked)
        self.csv_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.csv_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.csv_table)

        hint = QLabel("Double-click a row to jump to that frame in ANNOTATING.")
        hint.setObjectName("statusNeutral")
        layout.addWidget(hint)

    # ------------------------------------------------------------------
    # Ranges page
    # ------------------------------------------------------------------

    def build_ranges_page(self):
        layout = QVBoxLayout(self.ranges_page)
        layout.addWidget(QLabel("ANNOTATION RANGES", objectName="sectionTitle"))

        self.ranges_table = QTableWidget()
        self.ranges_table.setColumnCount(5)
        self.ranges_table.setHorizontalHeaderLabels(
            ["START", "END", "TYPE", "FRAMES", "STATUS"]
        )
        self.ranges_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ranges_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.ranges_table)

        self.range_summary = QLabel("No ranges yet.")
        self.range_summary.setObjectName("statusNeutral")
        layout.addWidget(self.range_summary)

    # ------------------------------------------------------------------
    # Statistics page
    # ------------------------------------------------------------------

    def build_stats_page(self):
        layout = QVBoxLayout(self.stats_page)
        layout.addWidget(QLabel("ANNOTATION STATISTICS", objectName="sectionTitle"))

        grid = QGridLayout()
        grid.setSpacing(10)

        names = [
            "Total Frames", "Annotated", "Remaining", "Progress",
            "Auto Annotated", "Manual Annotated",
            "Visible", "Partially Occluded", "Fully Occluded", "Out of Bounds",
            "Severe Motion Blur", "High Confidence", "Low Confidence",
        ]

        self.stat_detail_labels = {}
        for i, name in enumerate(names):
            card = MetricCard(name, "0")
            self.stat_detail_labels[name] = card
            grid.addWidget(card, i // 4, i % 4)

        layout.addLayout(grid)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Settings page
    # ------------------------------------------------------------------

    def build_settings_page(self):
        layout = QVBoxLayout(self.settings_page)
        layout.addWidget(QLabel("ANNOTATION SETTINGS", objectName="sectionTitle"))

        model_box = QGroupBox("MODEL")
        model_layout = QGridLayout(model_box)

        model_layout.addWidget(QLabel("Model"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["SAM 2.1 Tiny", "SAM 2.1 Small", "SAM 2.1 Base+", "SAM 2.1 Large"])
        model_layout.addWidget(self.model_combo, 0, 1)

        model_layout.addWidget(QLabel("Confidence threshold"), 1, 0)
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.05)
        self.confidence_spin.setValue(0.70)
        model_layout.addWidget(self.confidence_spin, 1, 1)

        self.auto_resume_check = QCheckBox(
            "Automatically continue when prediction confidence is above threshold"
        )
        self.auto_resume_check.setChecked(True)
        model_layout.addWidget(self.auto_resume_check, 2, 0, 1, 2)

        layout.addWidget(model_box)

        format_box = QGroupBox("TRACKNET CSV FORMAT")
        format_layout = QVBoxLayout(format_box)
        format_layout.addWidget(
            QLabel(
                "Required core: frame, x, y, visibility\n"
                "Visible / partially occluded: visibility = 1\n"
                "Fully occluded / out-of-bounds: x = 0, y = 0, visibility = 0\n"
                "Audit fields: x1, y1, x2, y2, source, confidence, status"
            )
        )
        layout.addWidget(format_box)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Directory / loading
    # ------------------------------------------------------------------

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Frame Directory")
        if not directory:
            return
        self.frame_directory = Path(directory)
        self.load_frames()

    def load_frames(self):
        self.frames = sorted(
            [
                p for p in self.frame_directory.iterdir()
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
            ],
            key=lambda p: self._frame_sort_key(p.name),
        )

        if not self.frames:
            QMessageBox.warning(self, "Annotation", "No image frames were found.")
            return

        self.csv_path = self.frame_directory / "annotations.csv"
        self.load_annotations()
        self.current_index = self._first_unannotated_index()

        self.dataset_label.setText(
            f"{self.frame_directory}  •  {len(self.frames):,} frames"
        )
        self.csv_path_label.setText(f"CSV: {self.csv_path}")
        self.update_all()

    @staticmethod
    def _frame_sort_key(name):
        stem = Path(name).stem
        try:
            return (0, int(stem))
        except ValueError:
            return (1, stem.lower())

    def _first_unannotated_index(self):
        for i, frame in enumerate(self.frames):
            if frame.name not in self.annotations:
                return i
        return 0

    # ------------------------------------------------------------------
    # CSV persistence
    # ------------------------------------------------------------------

    def load_annotations(self):
        self.annotations = {}
        if not self.csv_path or not self.csv_path.exists():
            return

        try:
            with open(self.csv_path, "r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    frame = row.get("frame", "").strip()
                    if not frame:
                        continue

                    def integer(key, default=0):
                        try:
                            return int(float(row.get(key, default)))
                        except (TypeError, ValueError):
                            return default

                    def floating(key, default=0.0):
                        try:
                            return float(row.get(key, default))
                        except (TypeError, ValueError):
                            return default

                    visibility = integer("visibility", 0)
                    x = integer("x", 0)
                    y = integer("y", 0)

                    self.annotations[frame] = {
                        "frame": frame,
                        "x": x,
                        "y": y,
                        "visibility": visibility,
                        "x1": integer("x1", 0),
                        "y1": integer("y1", 0),
                        "x2": integer("x2", 0),
                        "y2": integer("y2", 0),
                        "source": row.get("source", "MANUAL") or "MANUAL",
                        "confidence": floating("confidence", 1.0),
                        "status": row.get("status", STATUS_ACCEPTED) or STATUS_ACCEPTED,
                    }
        except Exception as error:
            QMessageBox.warning(self, "Annotation", f"Could not load annotations:\n{error}")

    def save_annotations(self):
        if not self.csv_path:
            return

        try:
            with open(self.csv_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
                writer.writeheader()

                for frame in self.frames:
                    annotation = self.annotations.get(frame.name)
                    if not annotation:
                        continue
                    writer.writerow(
                        {key: annotation.get(key, "") for key in CSV_COLUMNS}
                    )
        except Exception as error:
            QMessageBox.critical(self, "Annotation", f"Could not save annotations:\n{error}")

    # ------------------------------------------------------------------
    # Current frame
    # ------------------------------------------------------------------

    def show_current_frame(self):
        if not self.frames:
            self.image_viewer.set_frame(None)
            return

        frame_path = self.frames[self.current_index]
        pixmap = QPixmap(str(frame_path))

        if pixmap.isNull():
            self.current_status.setText("FAILED TO LOAD FRAME")
            self.current_status.setObjectName("statusBad")
            self.current_status.style().unpolish(self.current_status)
            self.current_status.style().polish(self.current_status)
            return

        annotation = self.annotations.get(frame_path.name)
        x = annotation.get("x") if annotation else None
        y = annotation.get("y") if annotation else None
        visibility = annotation.get("visibility", 0) if annotation else 0

        box = None
        if annotation and annotation.get("x2", 0) > annotation.get("x1", 0):
            box = (
                annotation["x1"], annotation["y1"],
                annotation["x2"], annotation["y2"]
            )

        self.image_viewer.set_frame(
            pixmap, x, y, visibility, box
        )

        self.metric_labels["Frame"].setText(
            f"{self.current_index + 1:,} / {len(self.frames):,}"
        )
        self.metric_labels["File"].setText(frame_path.name)
        self.frame_file_label.setText(
            f"FILE: {frame_path.name}"
        )
        self.frame_counter_label.setText(
            f"FRAME: {self.current_index + 1:,} / {len(self.frames):,}"
        )

        # Keep navigation controls synchronized without recursively moving
        # the frame while the slider is being updated.
        self.frame_slider.blockSignals(True)
        self.frame_slider.setMaximum(max(0, len(self.frames) - 1))
        self.frame_slider.setValue(self.current_index)
        self.frame_slider.blockSignals(False)
        self.frame_number_input.setText(
            str(self.current_index + 1)
        )

        progress = ((self.current_index + 1) / len(self.frames) * 100) if self.frames else 0
        if hasattr(self, "annotation_progress_label"):
            counts = self.counts()
            self.annotation_progress_label.setText(
                f"FRAME {self.current_index + 1:,} / {len(self.frames):,}   •   "
                f"ANNOTATED {counts['annotated']:,}   •   REMAINING {counts['remaining']:,}"
            )
            self.annotation_percent_label.setText(f"{counts['progress']:.1f}%")
            if hasattr(self, "annotation_progress_bar"):
                self.annotation_progress_bar.setValue(int(counts['progress']))
        self.metric_labels["Image Size"].setText(
            f"{pixmap.width()} × {pixmap.height()}"
        )

        if annotation:
            self.metric_labels["X"].setText(str(annotation["x"]))
            self.metric_labels["Y"].setText(str(annotation["y"]))
            self.metric_labels["Visibility"].setText(
                self.visibility_text(annotation["visibility"], annotation.get("status"))
            )
            self.metric_labels["Visibility Flag"].setText(
                str(annotation["visibility"])
            )
            self.metric_labels["Source"].setText(annotation["source"])
            self.metric_labels["Confidence"].setText(
                f"{annotation['confidence'] * 100:.1f}%"
            )
            self.metric_labels["Status"].setText(annotation["status"])

            if box:
                self.metric_labels["Bounding Box"].setText(
                    f"({box[0]}, {box[1]}) → ({box[2]}, {box[3]})"
                )
            else:
                self.metric_labels["Bounding Box"].setText("--")

            self.current_status.setText(
                f"{self.visibility_text(annotation['visibility'], annotation.get('status'))}  •  "
                f"{annotation['source']}  •  "
                f"{annotation['status']}"
            )
            if annotation.get("status") in {"PARTIALLY_OCCLUDED", STATUS_SEVERE_BLUR}:
                self.current_status.setObjectName("statusWarn")
            else:
                self.current_status.setObjectName(
                    "statusGood" if annotation["visibility"] == 1 else "statusBad"
                )
        else:
            for key in ("X", "Y", "Visibility", "Visibility Flag",
                        "Source", "Confidence", "Status",
                        "Bounding Box"):
                self.metric_labels[key].setText("--")
            if self.pending_visibility_mode == "PARTIAL":
                self.current_status.setText("PARTIAL SELECTED — CLICK THE ESTIMATED BALL CENTER")
                self.current_status.setObjectName("statusWarn")
            elif self.pending_visibility_mode == "VISIBLE":
                self.current_status.setText("VISIBLE SELECTED — CLICK THE BALL CENTER")
                self.current_status.setObjectName("statusWarn")
            else:
                self.current_status.setText("NOT ANNOTATED — CLICK THE BALL OR CHOOSE A VISIBILITY STATE")
                self.current_status.setObjectName("statusNeutral")

        self.current_status.style().unpolish(self.current_status)
        self.current_status.style().polish(self.current_status)

        if hasattr(self, "range_label"):
            self.range_label.setText(self.current_range_text())

    # ------------------------------------------------------------------
    # Annotation actions
    # ------------------------------------------------------------------

    def ball_clicked(self, x, y):
        """Handle a click in the frame viewer.

        If the user selected VISIBLE or PARTIAL first, that selected state is
        applied to the clicked point. If no state was selected, a normal click
        means VISIBLE. This makes it possible to label frames without a ball
        point (OCCLUDED/OOB) while still requiring a point for visibility=1.
        """
        if not self.frames:
            return

        mode = self.pending_visibility_mode or "VISIBLE"
        frame = self.frames[self.current_index]
        old = self.annotations.get(frame.name, {})

        if mode == "PARTIAL":
            status = "PARTIALLY_OCCLUDED"
        else:
            status = STATUS_ACCEPTED

        self.annotations[frame.name] = {
            "frame": frame.name,
            "x": int(x),
            "y": int(y),
            "visibility": 1,
            "x1": old.get("x1", 0),
            "y1": old.get("y1", 0),
            "x2": old.get("x2", 0),
            "y2": old.get("y2", 0),
            "source": "MANUAL",
            "confidence": 1.0,
            "status": status,
        }
        self.pending_visibility_mode = None
        self.update_all()
        self._autosave_if_enabled()

    def mark_visible(self):
        """Select VISIBLE; click the ball if no point exists yet."""
        if not self.frames:
            return
        frame = self.frames[self.current_index]
        annotation = self.annotations.get(frame.name)
        if annotation and annotation.get("visibility") == 1 and annotation.get("status") != STATUS_REVIEW and annotation.get("x") is not None:
            annotation["visibility"] = 1
            annotation["status"] = STATUS_ACCEPTED
            annotation["source"] = "MANUAL"
            annotation["confidence"] = 1.0
            self.pending_visibility_mode = None
            self.update_all()
            self._autosave_if_enabled()
            return

        self.pending_visibility_mode = "VISIBLE"
        self._set_pending_status("VISIBLE — click the ball center")

    def mark_partial(self):
        """Select PARTIAL; click the estimated ball center if needed."""
        if not self.frames:
            return
        frame = self.frames[self.current_index]
        annotation = self.annotations.get(frame.name)
        if annotation and annotation.get("visibility") == 1 and annotation.get("status") != STATUS_REVIEW and annotation.get("x") is not None:
            annotation["visibility"] = 1
            annotation["status"] = "PARTIALLY_OCCLUDED"
            annotation["source"] = "MANUAL"
            annotation["confidence"] = 1.0
            self.pending_visibility_mode = None
            self.update_all()
            self._autosave_if_enabled()
            return

        self.pending_visibility_mode = "PARTIAL"
        self._set_pending_status("PARTIAL — click the estimated ball center")

    def _set_pending_status(self, message):
        self.current_status.setText(message)
        self.current_status.setObjectName("statusWarn")
        self.current_status.style().unpolish(self.current_status)
        self.current_status.style().polish(self.current_status)

    def mark_occluded(self):
        """Mark a frame fully occluded without requiring a point."""
        if not self.frames:
            return
        frame = self.frames[self.current_index]
        self.pending_visibility_mode = None
        self.annotations[frame.name] = {
            "frame": frame.name,
            "x": 0,
            "y": 0,
            "visibility": 0,
            "x1": 0, "y1": 0, "x2": 0, "y2": 0,
            "source": "MANUAL",
            "confidence": 1.0,
            "status": STATUS_OCCLUDED,
        }
        self.update_all()
        self._autosave_if_enabled()

    def mark_oob(self):
        """Mark a frame out of bounds without requiring a point."""
        if not self.frames:
            return
        frame = self.frames[self.current_index]
        self.pending_visibility_mode = None
        self.annotations[frame.name] = {
            "frame": frame.name,
            "x": 0,
            "y": 0,
            "visibility": 0,
            "x1": 0, "y1": 0, "x2": 0, "y2": 0,
            "source": "MANUAL",
            "confidence": 1.0,
            "status": STATUS_OOB,
        }
        self.update_all()
        self._autosave_if_enabled()

    def mark_severe_motion_blur(self):
        """Mark a visible-but-unlocalizable ball caused by severe motion blur.

        TrackNet requires a usable point when visibility=1. When a human can
        see the ball but cannot reliably determine its center because the ball
        is stretched into blur and blends with court/text markings, we keep a
        dedicated status and use x=0, y=0, visibility=0 as a safe temporary
        TrackNet label. The status preserves the reason so these frames can be
        reviewed/corrected later.
        """
        if not self.frames:
            return
        frame = self.frames[self.current_index]
        self.pending_visibility_mode = None
        self.annotations[frame.name] = {
            "frame": frame.name,
            "x": 0,
            "y": 0,
            "visibility": 0,
            "x1": 0, "y1": 0, "x2": 0, "y2": 0,
            "source": "MANUAL",
            "confidence": 1.0,
            "status": STATUS_SEVERE_BLUR,
        }
        self.update_all()
        self._autosave_if_enabled()

    def clear_current_annotation(self):
        if not self.frames:
            return
        frame = self.frames[self.current_index]
        self.annotations.pop(frame.name, None)
        self.pending_visibility_mode = None

        if self.frame_directory:
            preview = self.frame_directory / "annotated" / frame.name
            try:
                if preview.exists():
                    preview.unlink()
            except OSError:
                pass

        self.update_all()
        self.save_annotations() if self.csv_path else None
        self.refresh_csv_table()

    def _require_position(self):
        """Legacy helper kept for compatibility with external callers."""
        if not self.frames:
            return None
        frame = self.frames[self.current_index]
        annotation = self.annotations.get(frame.name)
        if not annotation or annotation.get("visibility") != 1:
            return None
        return annotation

    def _save_current_visual(self):
        """Save a visual verification copy without modifying the original frame."""
        if not self.frames or not self.frame_directory:
            return

        frame = self.frames[self.current_index]
        annotation = self.annotations.get(frame.name)
        if not annotation:
            return

        try:
            source = QPixmap(str(frame))
            if source.isNull():
                return

            canvas = QPixmap(source)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.Antialiasing)

            x = int(annotation.get("x", 0))
            y = int(annotation.get("y", 0))
            visibility = int(annotation.get("visibility", 0))
            status = annotation.get("status", STATUS_ACCEPTED)

            if visibility == 1:
                painter.setPen(QPen(QColor("#22c55e"), max(2, source.width() // 500)))
                painter.setBrush(QBrush(Qt.NoBrush))
                radius = max(5, min(18, source.width() // 120))
                painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
                painter.setPen(QPen(QColor("#ffffff"), max(1, source.width() // 800)))
                painter.drawLine(x - radius * 2, y, x + radius * 2, y)
                painter.drawLine(x, y - radius * 2, x, y + radius * 2)
                text = f"{status}  ({x}, {y})"
            else:
                text = f"{status}  (0, 0)"

            painter.setPen(QPen(QColor("#ffffff")))
            painter.setBrush(QBrush(QColor(2, 6, 23, 220)))
            painter.drawRect(10, 10, min(source.width() - 20, max(260, len(text) * 8 + 30)), 34)
            painter.drawText(20, 32, text)
            painter.end()

            output_dir = self.frame_directory / "annotated"
            output_dir.mkdir(parents=True, exist_ok=True)
            canvas.save(str(output_dir / frame.name), "JPG", 95)
        except Exception:
            # Preview images are auxiliary. Never prevent CSV annotation saving.
            return

    # ------------------------------------------------------------------
    # Fast navigation / autosave
    # ------------------------------------------------------------------

    def set_autosave(self, enabled):
        self.autosave_enabled = bool(enabled)
        if self.autosave_enabled:
            self.save_hint.setText(
                "Auto-save ON: annotations are written immediately."
            )
        else:
            self.save_hint.setText(
                "Manual mode: use SAVE & NEXT to commit and move forward."
            )

    def _autosave_if_enabled(self):
        if self.autosave_enabled:
            self.save_annotations()
            self._save_current_visual()
            self.refresh_csv_table()
            self.show_current_frame()

    def jump_frames(self, amount):
        if not self.frames:
            return
        self.current_index = max(
            0,
            min(
                len(self.frames) - 1,
                self.current_index + amount,
            ),
        )
        self.show_current_frame()
        self.update_navigation_state()

    def go_to_frame(self, frame_number):
        if not self.frames:
            return
        try:
            index = int(frame_number) - 1
        except (TypeError, ValueError):
            return

        index = max(
            0,
            min(len(self.frames) - 1, index),
        )
        self.current_index = index
        self.pending_visibility_mode = None
        self.show_current_frame()
        self.update_navigation_state()

    def go_to_frame_from_input(self):
        self.go_to_frame(
            self.frame_number_input.text()
        )

    def slider_frame_changed(self, index):
        if not self.frames:
            return
        if index == self.current_index:
            return
        self.current_index = max(
            0,
            min(len(self.frames) - 1, index),
        )
        self.show_current_frame()
        self.update_navigation_state()

    def toggle_play(self, playing):
        if playing:
            self.play_button.setText("⏸ PAUSE")
            if not hasattr(self, "_play_timer"):
                from PySide6.QtCore import QTimer
                self._play_timer = QTimer(self)
                self._play_timer.setInterval(80)
                self._play_timer.timeout.connect(self._play_next_frame)
            self._play_timer.start()
        else:
            self.play_button.setText("▶ PLAY")
            if hasattr(self, "_play_timer"):
                self._play_timer.stop()

    def _play_next_frame(self):
        if not self.frames:
            self.play_button.setChecked(False)
            return
        if self.current_index >= len(self.frames) - 1:
            self.play_button.setChecked(False)
            return
        self.current_index += 1
        self.show_current_frame()
        self.update_navigation_state()

    def update_navigation_state(self):
        enabled = bool(self.frames)
        if not enabled:
            return

        self.previous_button.setEnabled(
            self.current_index > 0
        )
        self.next_button.setEnabled(
            self.current_index < len(self.frames) - 1
        )
        self.prev_fast_button.setEnabled(
            self.current_index > 0
        )
        self.next_fast_button.setEnabled(
            self.current_index < len(self.frames) - 1
        )
        self.jump_back_button.setEnabled(
            self.current_index > 0
        )
        self.jump_forward_button.setEnabled(
            self.current_index < len(self.frames) - 1
        )
        self.frame_slider.setEnabled(True)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _current_annotation_ready(self):
        if not self.frames:
            return False
        frame = self.frames[self.current_index]
        annotation = self.annotations.get(frame.name)
        if not annotation:
            return False
        if annotation.get("visibility") == 1:
            return annotation.get("x") is not None and annotation.get("y") is not None
        return annotation.get("status") in {STATUS_OCCLUDED, STATUS_OOB, STATUS_SEVERE_BLUR}

    def save_current(self):
        if not self._current_annotation_ready():
            QMessageBox.information(
                self,
                "Annotation Required",
                "For a visible/partially occluded ball, click the ball center first.\n\n"
                "If the ball cannot be localized, choose FULLY OCCLUDED, OUT OF BOUNDS, or SEVERE MOTION BLUR.",
            )
            return
        self.save_annotations()
        self._save_current_visual()
        self.refresh_csv_table()
        self.show_current_frame()

    def save_and_next(self):
        if not self._current_annotation_ready():
            QMessageBox.information(
                self,
                "Annotation Required",
                "Mark the current frame first.\n\n"
                "Click the ball for VISIBLE/PARTIAL, or choose FULLY OCCLUDED / OUT OF BOUNDS / SEVERE MOTION BLUR.",
            )
            return

        self.save_annotations()
        self._save_current_visual()
        if self.current_index < len(self.frames) - 1:
            self.current_index += 1
            self.pending_visibility_mode = None
        self.update_all()
        self.update_navigation_state()

    def next_frame(self):
        if self.current_index < len(self.frames) - 1:
            self.current_index += 1
            self.pending_visibility_mode = None
            self.show_current_frame()
            self.update_navigation_state()

    def previous_frame(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.pending_visibility_mode = None
            self.show_current_frame()
            self.update_navigation_state()

    # ------------------------------------------------------------------
    # Statistics / ranges
    # ------------------------------------------------------------------

    @staticmethod
    def visibility_text(value, status=None):
        if status == "PARTIALLY_OCCLUDED":
            return "PARTIALLY OCCLUDED"
        if status == STATUS_OCCLUDED:
            return "FULLY OCCLUDED"
        if status == STATUS_OOB:
            return "OUT OF BOUNDS"
        if status == STATUS_SEVERE_BLUR:
            return "SEVERE MOTION BLUR"
        if value == 1:
            return "VISIBLE"
        return "NOT VISIBLE"

    def counts(self):
        values = list(self.annotations.values())
        total = len(self.frames)
        annotated = len(values)

        auto = sum(v.get("source") == "AUTO" for v in values)
        manual = sum(v.get("source") == "MANUAL" for v in values)
        visible = sum(v.get("visibility") == 1 and v.get("status") == STATUS_ACCEPTED for v in values)
        partial = sum(v.get("visibility") == 1 and v.get("status") == "PARTIALLY_OCCLUDED" for v in values)
        occluded = sum(v.get("status") == STATUS_OCCLUDED for v in values)
        oob = sum(v.get("status") == STATUS_OOB for v in values)
        severe_blur = sum(v.get("status") == STATUS_SEVERE_BLUR for v in values)
        high = sum(v.get("confidence", 0) >= self.confidence_spin.value() for v in values)
        low = sum(v.get("status") == STATUS_REVIEW for v in values)

        return {
            "total": total,
            "annotated": annotated,
            "remaining": max(0, total - annotated),
            "progress": (annotated / total * 100) if total else 0,
            "auto": auto,
            "manual": manual,
            "visible": visible,
            "partial": partial,
            "occluded": occluded,
            "oob": oob,
            "severe_blur": severe_blur,
            "high": high,
            "low": low,
        }

    def update_statistics(self):
        c = self.counts()

        # Detailed aggregate statistics live in the STATISTICS tab. The
        # Annotating tab only shows the compact progress strip.
        if hasattr(self, "annotation_progress_label"):
            self.annotation_progress_label.setText(
                f"FRAME {self.current_index + 1 if self.frames else 0:,} / {c['total']:,}   •   "
                f"ANNOTATED {c['annotated']:,}   •   REMAINING {c['remaining']:,}"
            )
            self.annotation_percent_label.setText(
                f"{c['progress']:.1f}%"
            )
            if hasattr(self, "annotation_progress_bar"):
                self.annotation_progress_bar.setValue(int(c['progress']))

        mapping = {
            "Total Frames": c["total"],
            "Annotated": c["annotated"],
            "Remaining": c["remaining"],
            "Progress": f"{c['progress']:.1f}%",
            "Auto Annotated": c["auto"],
            "Manual Annotated": c["manual"],
            "Visible": c["visible"],
            "Partially Occluded": c["partial"],
            "Fully Occluded": c["occluded"],
            "Out of Bounds": c["oob"],
            "Severe Motion Blur": c["severe_blur"],
            "High Confidence": c["high"],
            "Low Confidence": c["low"],
        }

        for key, value in mapping.items():
            if hasattr(self, "stat_detail_labels") and key in self.stat_detail_labels:
                self.stat_detail_labels[key].set_value(value)

    def current_range_text(self):
        if not self.frames:
            return "CURRENT RANGE: --"

        name = self.frames[self.current_index].name
        if name not in self.annotations:
            return f"CURRENT RANGE: FRAME {self.current_index + 1:03d} — NOT ANNOTATED"

        target_source = self.annotations[name].get("source", "MANUAL")
        target_status = self.annotations[name].get("status", STATUS_ACCEPTED)

        start = self.current_index
        end = self.current_index

        while start > 0:
            prev = self.annotations.get(self.frames[start - 1].name)
            if not prev:
                break
            if (
                prev.get("source", "MANUAL") != target_source
                or prev.get("status", STATUS_ACCEPTED) != target_status
            ):
                break
            start -= 1

        while end < len(self.frames) - 1:
            nxt = self.annotations.get(self.frames[end + 1].name)
            if not nxt:
                break
            if (
                nxt.get("source", "MANUAL") != target_source
                or nxt.get("status", STATUS_ACCEPTED) != target_status
            ):
                break
            end += 1

        return (
            f"CURRENT RANGE: {start + 1:03d} → {end + 1:03d}  •  "
            f"{target_source}  •  {target_status}"
        )

    def update_ranges(self):
        self.ranges_table.setRowCount(0)
        if not self.frames:
            self.range_summary.setText("No frames loaded.")
            return

        ranges = []
        i = 0
        while i < len(self.frames):
            annotation = self.annotations.get(self.frames[i].name)
            if not annotation:
                kind = "UNANNOTATED"
                status = "NOT PROCESSED"
            else:
                kind = annotation.get("source", "MANUAL")
                status = annotation.get("status", STATUS_ACCEPTED)

            start = i
            i += 1

            while i < len(self.frames):
                next_ann = self.annotations.get(self.frames[i].name)
                if not next_ann:
                    next_kind = "UNANNOTATED"
                    next_status = "NOT PROCESSED"
                else:
                    next_kind = next_ann.get("source", "MANUAL")
                    next_status = next_ann.get("status", STATUS_ACCEPTED)

                if next_kind != kind or next_status != status:
                    break
                i += 1

            ranges.append((start + 1, i, kind, i - start, status))

        for start, end, kind, count, status in ranges:
            row = self.ranges_table.rowCount()
            self.ranges_table.insertRow(row)
            for col, value in enumerate([f"{start:03d}", f"{end:03d}", kind, count, status]):
                self.ranges_table.setItem(row, col, QTableWidgetItem(str(value)))

        self.range_summary.setText(
            f"{len(ranges)} range(s) • {sum(r[3] for r in ranges)} frames covered"
        )

    # ------------------------------------------------------------------
    # CSV table
    # ------------------------------------------------------------------

    def refresh_csv_table(self):
        self.csv_table.setRowCount(0)

        for frame in self.frames:
            annotation = self.annotations.get(frame.name)
            if not annotation:
                continue

            row = self.csv_table.rowCount()
            self.csv_table.insertRow(row)

            for col, key in enumerate(CSV_COLUMNS):
                value = annotation.get(key, "")
                if key == "confidence":
                    value = f"{float(value):.4f}"
                self.csv_table.setItem(row, col, QTableWidgetItem(str(value)))

        self.csv_table.resizeColumnsToContents()

    def csv_row_clicked(self, row, _column):
        item = self.csv_table.item(row, 0)
        if not item:
            return

        frame_name = item.text()
        for index, frame in enumerate(self.frames):
            if frame.name == frame_name:
                self.current_index = index
                self.tabs.setCurrentWidget(self.annotating_page)
                self.show_current_frame()
                break

    # ------------------------------------------------------------------
    # Global update
    # ------------------------------------------------------------------

    def update_all(self):
        self.show_current_frame()
        self.update_statistics()
        self.update_ranges()
        self.refresh_csv_table()

        if self.csv_path:
            self.csv_path_label.setText(f"CSV: {self.csv_path}")

        enabled = bool(self.frames)
        self.previous_button.setEnabled(enabled and self.current_index > 0)
        self.next_button.setEnabled(
            enabled and self.current_index < len(self.frames) - 1
        )
        self.save_button.setEnabled(enabled)
        self.save_next_button.setEnabled(enabled)
        self.visible_button.setEnabled(enabled)
        self.partial_button.setEnabled(enabled)
        self.occluded_button.setEnabled(enabled)
        self.oob_button.setEnabled(enabled)
        self.blur_button.setEnabled(enabled)

        if self.frames:
            self.update_navigation_state()
        else:
            self.frame_file_label.setText("FILE: --")
            self.frame_counter_label.setText("FRAME: -- / --")
            self.frame_slider.setMaximum(0)
            self.frame_slider.setValue(0)
            if hasattr(self, "annotation_progress_label"):
                self.annotation_progress_label.setText(
                    "FRAME 0 / 0   •   ANNOTATED 0   •   REMAINING 0"
                )
                self.annotation_percent_label.setText("0.0%")
                if hasattr(self, "annotation_progress_bar"):
                    self.annotation_progress_bar.setValue(0)

    # ------------------------------------------------------------------
    # External API for future SAM worker
    # ------------------------------------------------------------------

    def set_model_annotation(
        self,
        frame_name,
        x,
        y,
        visibility=1,
        x1=0,
        y1=0,
        x2=0,
        y2=0,
        confidence=0.0,
        status=STATUS_REVIEW,
    ):
        """Accept a prediction from a future SAM worker.

        Manual annotations can overwrite this prediction. This method never
        changes a manually accepted annotation unless explicitly called by
        application code.
        """
        existing = self.annotations.get(frame_name)
        if existing and existing.get("source") == "MANUAL":
            return

        self.pending_visibility_mode = None
        self.annotations[frame_name] = {
            "frame": frame_name,
            "x": int(x),
            "y": int(y),
            "visibility": int(visibility),
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2),
            "source": "AUTO",
            "confidence": float(confidence),
            "status": status,
        }
        self.update_all()

    def mark_model_low_confidence(self, frame_name, confidence):
        existing = self.annotations.get(frame_name)
        if existing and existing.get("source") == "MANUAL":
            return

        self.pending_visibility_mode = None
        self.annotations[frame_name] = {
            "frame": frame_name,
            "x": 0,
            "y": 0,
            "visibility": 1,
            "x1": 0,
            "y1": 0,
            "x2": 0,
            "y2": 0,
            "source": "AUTO",
            "confidence": float(confidence),
            "status": STATUS_REVIEW,
        }
        self.update_all()