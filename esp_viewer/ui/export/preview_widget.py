from PyQt6.QtWidgets import QGroupBox, QPlainTextEdit, QVBoxLayout, QWidget


class PreviewWidget(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Preview")
        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self._text)

    def set_preview_text(self, text: str) -> None:
        self._text.setPlainText(text)
