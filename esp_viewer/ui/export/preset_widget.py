from typing import List

from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QPushButton, QWidget


class PresetWidget(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Presets")
        self._combo = QComboBox(self)
        self._load_button = QPushButton("Load", self)
        self._save_button = QPushButton("Save", self)
        self._delete_button = QPushButton("Delete", self)
        layout = QHBoxLayout(self)
        layout.addWidget(self._combo)
        layout.addWidget(self._load_button)
        layout.addWidget(self._save_button)
        layout.addWidget(self._delete_button)
        layout.addStretch(1)

    def current_preset_name(self) -> str:
        return self._combo.currentText()

    def set_presets(self, names: List[str]) -> None:
        current = self._combo.currentText()
        self._combo.clear()
        self._combo.addItems(names)
        if current:
            index = self._combo.findText(current)
            if index >= 0:
                self._combo.setCurrentIndex(index)

    def load_button(self) -> QPushButton:
        return self._load_button

    def save_button(self) -> QPushButton:
        return self._save_button

    def delete_button(self) -> QPushButton:
        return self._delete_button

    def combo(self) -> QComboBox:
        return self._combo
