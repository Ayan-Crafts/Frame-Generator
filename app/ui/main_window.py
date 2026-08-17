from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Frame Generator")
        self.resize(700, 450)

        self.input_directory = ""
        self.output_directory = ""

        self.input_label = QLabel("Input: Not selected")
        self.output_label = QLabel("Output: Not selected")

        input_button = QPushButton("Select Input Directory")
        output_button = QPushButton("Select Output Directory")
        start_button = QPushButton("START EXPORTING")

        input_button.clicked.connect(self.select_input)
        output_button.clicked.connect(self.select_output)

        layout = QVBoxLayout()

        layout.addWidget(self.input_label)
        layout.addWidget(input_button)

        layout.addWidget(self.output_label)
        layout.addWidget(output_button)

        layout.addStretch()

        layout.addWidget(start_button)

        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)

    def select_input(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Input Directory"
        )

        if directory:
            self.input_directory = directory
            self.input_label.setText(
                f"Input: {directory}"
            )

    def select_output(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory"
        )

        if directory:
            self.output_directory = directory
            self.output_label.setText(
                f"Output: {directory}"
            )