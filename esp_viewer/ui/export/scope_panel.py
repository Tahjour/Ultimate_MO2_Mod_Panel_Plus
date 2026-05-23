from typing import Dict, Set

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ScopePanel(QGroupBox):
    scope_changed = Signal(str)
    custom_selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Source")
        self._scope = QComboBox(self)
        self._scope.addItem("Entire Plugin", "entire_plugin")
        self._scope.addItem("Current Selection", "current_selection")
        self._scope.addItem("Filtered Results", "filtered")
        self._scope.addItem("Search Results", "search")
        self._scope.addItem("Custom Selection", "custom")

        self._custom_box = QGroupBox("Custom Selection", self)
        self._custom_list = QListWidget(self._custom_box)
        self._custom_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._custom_select_all = QPushButton("Select All", self._custom_box)
        self._custom_deselect_all = QPushButton("Deselect", self._custom_box)
        self._custom_invert = QPushButton("Invert", self._custom_box)

        custom_buttons = QHBoxLayout()
        custom_buttons.addWidget(self._custom_select_all)
        custom_buttons.addWidget(self._custom_deselect_all)
        custom_buttons.addWidget(self._custom_invert)
        custom_buttons.addStretch(1)

        custom_layout = QVBoxLayout(self._custom_box)
        custom_layout.addLayout(custom_buttons)
        custom_layout.addWidget(self._custom_list)
        layout = QVBoxLayout(self)
        layout.addWidget(self._scope)

        layout.addWidget(self._custom_box)

        self._scope.currentIndexChanged.connect(self._on_scope_changed)
        self._custom_list.itemChanged.connect(self._on_custom_changed)
        self._custom_select_all.clicked.connect(self._select_all)
        self._custom_deselect_all.clicked.connect(self._deselect_all)
        self._custom_invert.clicked.connect(self._invert_selection)

        self._update_custom_visibility()

    def scope_key(self) -> str:
        data = self._scope.currentData()
        if isinstance(data, str):
            return data
        return "entire_plugin"

    def set_scope_key(self, key: str) -> None:
        index = self._scope.findData(key)
        if index >= 0:
            self._scope.setCurrentIndex(index)

    def set_signatures(self, signature_counts: Dict[str, int], signature_labels: Dict[str, str]) -> None:
        self._custom_list.blockSignals(True)
        self._custom_list.clear()
        for signature in sorted(signature_counts.keys()):
            count = signature_counts.get(signature, 0)
            label = signature_labels.get(signature, signature)
            text = f"{signature} ({count}) — {label}"
            item = QListWidgetItem(text, self._custom_list)
            item.setData(Qt.ItemDataRole.UserRole, signature)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
        self._custom_list.blockSignals(False)
        self.custom_selection_changed.emit()

    def custom_signatures(self) -> Set[str]:
        selected: Set[str] = set()
        for index in range(self._custom_list.count()):
            item = self._custom_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                signature = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(signature, str):
                    selected.add(signature)
        return selected

    def set_custom_signatures(self, signatures: Set[str]) -> None:
        self._custom_list.blockSignals(True)
        for index in range(self._custom_list.count()):
            item = self._custom_list.item(index)
            signature = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(signature, str):
                state = Qt.CheckState.Checked if signature in signatures else Qt.CheckState.Unchecked
                item.setCheckState(state)
        self._custom_list.blockSignals(False)
        self.custom_selection_changed.emit()

    def state(self) -> Dict[str, object]:
        return {
            "scope": self.scope_key(),
            "custom_signatures": sorted(self.custom_signatures()),
        }

    def apply_state(self, state: Dict[str, object]) -> None:
        scope_key = state.get("scope")
        if isinstance(scope_key, str):
            self.set_scope_key(scope_key)
        signatures = state.get("custom_signatures", [])
        if isinstance(signatures, list):
            self.set_custom_signatures(set(str(item) for item in signatures))

    def _on_scope_changed(self) -> None:
        self._update_custom_visibility()
        self.scope_changed.emit(self.scope_key())

    def _update_custom_visibility(self) -> None:
        self._custom_box.setVisible(self.scope_key() == "custom")

    def _on_custom_changed(self) -> None:
        self.custom_selection_changed.emit()

    def _select_all(self) -> None:
        self._custom_list.blockSignals(True)
        for index in range(self._custom_list.count()):
            self._custom_list.item(index).setCheckState(Qt.CheckState.Checked)
        self._custom_list.blockSignals(False)
        self.custom_selection_changed.emit()

    def _deselect_all(self) -> None:
        self._custom_list.blockSignals(True)
        for index in range(self._custom_list.count()):
            self._custom_list.item(index).setCheckState(Qt.CheckState.Unchecked)
        self._custom_list.blockSignals(False)
        self.custom_selection_changed.emit()

    def _invert_selection(self) -> None:
        self._custom_list.blockSignals(True)
        for index in range(self._custom_list.count()):
            item = self._custom_list.item(index)
            state = item.checkState()
            item.setCheckState(Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked)
        self._custom_list.blockSignals(False)
        self.custom_selection_changed.emit()
