from PyQt6.QtCore import QTimer, pyqtSignal as Signal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget


class QuickFilterWidget(QWidget):
    filter_changed = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = QComboBox(self)
        self._mode.addItems(["Signature", "Text"])

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Quick filter")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._emit_filter)

        self._mode.currentIndexChanged.connect(self._emit_filter)
        self._input.textChanged.connect(self._on_text_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._mode)
        layout.addWidget(self._input)

    def _on_text_changed(self, text: str) -> None:
        self._timer.start()

    def _emit_filter(self) -> None:
        self.filter_changed.emit(self._mode.currentText(), self._input.text())

    def focus_input(self) -> None:
        self._input.setFocus()
        self._input.selectAll()
