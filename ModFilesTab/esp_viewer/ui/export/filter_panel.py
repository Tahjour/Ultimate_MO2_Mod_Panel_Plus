from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QWidget,
)

from esp_viewer.core.exporter2.base import ExportFilters


class FilterPanel(QGroupBox):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Filters")

        self._only_with_editor_id = QCheckBox("Only with EditorID", self)
        self._only_with_full_name = QCheckBox("Only with Full Name", self)
        self._exclude_deleted = QCheckBox("Exclude deleted records", self)
        self._exclude_ignored = QCheckBox("Exclude ignored records", self)
        self._exclude_deleted.setChecked(True)

        self._compressed_mode = QComboBox(self)
        self._compressed_mode.addItems(["Any", "Only compressed", "Only uncompressed"])

        self._parse_error_mode = QComboBox(self)
        self._parse_error_mode.addItems(["Any", "Only with parse errors", "Exclude parse errors"])

        self._formid_min = QLineEdit(self)
        self._formid_max = QLineEdit(self)
        self._form_version_min = QLineEdit(self)
        self._form_version_max = QLineEdit(self)

        layout = QFormLayout(self)
        layout.addRow(self._only_with_editor_id)
        layout.addRow(self._only_with_full_name)
        layout.addRow(self._exclude_deleted)
        layout.addRow(self._exclude_ignored)
        layout.addRow("Compression", self._compressed_mode)
        layout.addRow("Parse errors", self._parse_error_mode)
        layout.addRow("FormID min (hex)", self._formid_min)
        layout.addRow("FormID max (hex)", self._formid_max)
        layout.addRow("Form version min", self._form_version_min)
        layout.addRow("Form version max", self._form_version_max)

        for checkbox in self.findChildren(QCheckBox):
            checkbox.toggled.connect(self._on_any_changed)
        for line in self.findChildren(QLineEdit):
            line.textChanged.connect(self._on_any_changed)
        for combo in self.findChildren(QComboBox):
            combo.currentIndexChanged.connect(self._on_any_changed)

    def build_filters(self) -> ExportFilters:
        filters = ExportFilters()
        filters.only_with_editor_id = self._only_with_editor_id.isChecked()
        filters.only_with_full_name = self._only_with_full_name.isChecked()
        filters.exclude_deleted = self._exclude_deleted.isChecked()
        filters.exclude_ignored = self._exclude_ignored.isChecked()
        filters.only_compressed = self._parse_tri_state(self._compressed_mode.currentIndex())
        filters.only_with_errors = self._parse_tri_state(self._parse_error_mode.currentIndex())
        text_min = self._formid_min.text().strip()
        text_max = self._formid_max.text().strip()
        if text_min:
            try:
                filters.formid_min = int(text_min, 16)
            except ValueError:
                filters.formid_min = None
        if text_max:
            try:
                filters.formid_max = int(text_max, 16)
            except ValueError:
                filters.formid_max = None
        text_version_min = self._form_version_min.text().strip()
        text_version_max = self._form_version_max.text().strip()
        if text_version_min:
            try:
                filters.form_version_min = int(text_version_min)
            except ValueError:
                filters.form_version_min = None
        if text_version_max:
            try:
                filters.form_version_max = int(text_version_max)
            except ValueError:
                filters.form_version_max = None
        return filters

    def _parse_tri_state(self, index: int):
        if index == 1:
            return True
        if index == 2:
            return False
        return None

    def _on_any_changed(self, *_) -> None:
        self.changed.emit()

    def state(self) -> dict:
        return {
            "only_with_editor_id": self._only_with_editor_id.isChecked(),
            "only_with_full_name": self._only_with_full_name.isChecked(),
            "exclude_deleted": self._exclude_deleted.isChecked(),
            "exclude_ignored": self._exclude_ignored.isChecked(),
            "compressed_mode": self._compressed_mode.currentIndex(),
            "parse_error_mode": self._parse_error_mode.currentIndex(),
            "formid_min": self._formid_min.text(),
            "formid_max": self._formid_max.text(),
            "form_version_min": self._form_version_min.text(),
            "form_version_max": self._form_version_max.text(),
        }

    def apply_state(self, state: dict) -> None:
        self._only_with_editor_id.setChecked(bool(state.get("only_with_editor_id", False)))
        self._only_with_full_name.setChecked(bool(state.get("only_with_full_name", False)))
        self._exclude_deleted.setChecked(bool(state.get("exclude_deleted", True)))
        self._exclude_ignored.setChecked(bool(state.get("exclude_ignored", False)))
        self._compressed_mode.setCurrentIndex(int(state.get("compressed_mode", 0)))
        self._parse_error_mode.setCurrentIndex(int(state.get("parse_error_mode", 0)))
        self._formid_min.setText(str(state.get("formid_min", "")))
        self._formid_max.setText(str(state.get("formid_max", "")))
        self._form_version_min.setText(str(state.get("form_version_min", "")))
        self._form_version_max.setText(str(state.get("form_version_max", "")))
