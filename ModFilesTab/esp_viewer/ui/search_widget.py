from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QCompleter, QLineEdit, QWidget, QHBoxLayout

from esp_viewer.core.data_types import Record


class SearchWidget(QWidget):
    search_requested = Signal(str)
    result_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Search (EditorID, FormID, Name...)")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._emit_search)

        self._model = QStandardItemModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.activated.connect(self._on_activated)
        self._input.setCompleter(self._completer)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_return)

        self._results: List[Tuple[str, Record]] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._input)

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            self._model.clear()
            self._results = []
            return
        self._timer.start()

    def _emit_search(self) -> None:
        self.search_requested.emit(self._input.text())

    def _on_activated(self, text: str) -> None:
        for label, record in self._results:
            if label == text:
                self.result_selected.emit(record)
                return

    def _on_return(self) -> None:
        if self._results:
            self.result_selected.emit(self._results[0][1])

    def set_results(self, results: List[Tuple[str, Record]]) -> None:
        self._results = results
        self._model.clear()
        for label, _ in results:
            self._model.appendRow(QStandardItem(label))

    def set_text(self, text: str) -> None:
        self._input.setText(text)

    def focus_input(self) -> None:
        self._input.setFocus()

    def text(self) -> str:
        return self._input.text()
