from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget

from esp_viewer.ui.advanced_search_widget import AdvancedSearchWidget


class ToolsPanel(QWidget):
    search_requested = Signal(str, list)
    record_selected = Signal(object)
    conflict_filter_changed = Signal(bool, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search = AdvancedSearchWidget(self)
        self._search.search_requested.connect(self.search_requested)
        self._search.record_selected.connect(self.record_selected)
        self._search.setAccessibleName("Advanced search")
        self._search.setAccessibleDescription("Search by parameters and results")

        tabs = QTabWidget(self)
        tabs.addTab(self._search, "Search")

        self._conflict_only = QCheckBox("Show only conflicts", self)
        self._conflict_hide_identical = QCheckBox("Hide identical to master", self)
        self._conflict_only.toggled.connect(self._emit_conflict_filter)
        self._conflict_hide_identical.toggled.connect(self._emit_conflict_filter)

        conflict_box = QGroupBox("Conflicts", self)
        conflict_layout = QVBoxLayout(conflict_box)
        conflict_layout.addWidget(self._conflict_only)
        conflict_layout.addWidget(self._conflict_hide_identical)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(tabs)
        layout.addWidget(conflict_box)
        layout.addStretch(1)

    def _emit_conflict_filter(self) -> None:
        self.conflict_filter_changed.emit(
            self._conflict_only.isChecked(),
            self._conflict_hide_identical.isChecked(),
        )

    def set_conflict_filters(self, only_conflicts: bool, hide_identical: bool) -> None:
        if self._conflict_only.isChecked() != only_conflicts:
            self._conflict_only.blockSignals(True)
            self._conflict_only.setChecked(only_conflicts)
            self._conflict_only.blockSignals(False)
        if self._conflict_hide_identical.isChecked() != hide_identical:
            self._conflict_hide_identical.blockSignals(True)
            self._conflict_hide_identical.setChecked(hide_identical)
            self._conflict_hide_identical.blockSignals(False)

    def focus_search(self) -> None:
        self._search.focus_input()

    def set_search_results(self, results) -> None:
        self._search.set_results(results)

    def save_search_header_state(self):
        return self._search.header_state()

    def restore_search_header_state(self, state) -> bool:
        return self._search.restore_header_state(state)

    def apply_search_default_sizes(self) -> None:
        self._search._apply_default_column_sizes()


class ExportPanel(QWidget):
    export_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._export_button = QPushButton("Export", self)
        self._export_button.clicked.connect(self.export_requested)
        self._export_button.setAccessibleName("Export data")
        self._export_button.setAccessibleDescription("Start export of selected data")

        export_box = QGroupBox("Export", self)
        export_layout = QHBoxLayout(export_box)
        export_layout.addWidget(self._export_button)
        export_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(export_box)
        layout.addStretch(1)
