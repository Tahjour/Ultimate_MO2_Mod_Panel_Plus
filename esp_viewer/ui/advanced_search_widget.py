from typing import Iterable, List, Tuple

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHeaderView,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from esp_viewer.core.data_types import Record


class AdvancedSearchWidget(QWidget):
    search_requested = Signal(str, list)
    record_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = QLineEdit(self)
        self._query.setPlaceholderText("Search by parameters")
        self._query.returnPressed.connect(self._emit_search)

        self._search_button = QPushButton("Search", self)
        self._search_button.clicked.connect(self._emit_search)

        self._all_fields = QCheckBox("All fields", self)
        self._all_fields.setChecked(True)
        self._all_fields.toggled.connect(self._toggle_all)

        self._field_signature = QCheckBox("Signature", self)
        self._field_editor_id = QCheckBox("EditorID", self)
        self._field_full_name = QCheckBox("Name", self)
        self._field_form_id = QCheckBox("FormID", self)

        for checkbox in (
            self._field_signature,
            self._field_editor_id,
            self._field_full_name,
            self._field_form_id,
        ):
            checkbox.setEnabled(False)

        self._results_model = QStandardItemModel(self)
        self._results_model.setHorizontalHeaderLabels(["Record", "Type"])

        self._results_view = QTreeView(self)
        self._results_view.setModel(self._results_model)
        self._results_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._results_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._results_view.doubleClicked.connect(self._activate_selected)
        self._results_view.header().setStretchLastSection(False)
        self._results_view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._results_view.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._apply_default_column_sizes()

        top_row = QHBoxLayout()
        top_row.addWidget(self._query)
        top_row.addWidget(self._search_button)

        fields_row = QHBoxLayout()
        fields_row.addWidget(self._all_fields)
        fields_row.addWidget(self._field_signature)
        fields_row.addWidget(self._field_editor_id)
        fields_row.addWidget(self._field_full_name)
        fields_row.addWidget(self._field_form_id)
        fields_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_row)
        layout.addLayout(fields_row)
        layout.addWidget(self._results_view)

        self._results: List[Tuple[str, Record]] = []

    def _toggle_all(self, checked: bool) -> None:
        for checkbox in (
            self._field_signature,
            self._field_editor_id,
            self._field_full_name,
            self._field_form_id,
        ):
            checkbox.setEnabled(not checked)
            if checked:
                checkbox.setChecked(False)

    def _emit_search(self) -> None:
        query = self._query.text()
        fields = self.selected_fields()
        self.search_requested.emit(query, fields)

    def selected_fields(self) -> List[str]:
        if self._all_fields.isChecked():
            return ["all"]
        fields: List[str] = []
        if self._field_signature.isChecked():
            fields.append("signature")
        if self._field_editor_id.isChecked():
            fields.append("editor_id")
        if self._field_full_name.isChecked():
            fields.append("full_name")
        if self._field_form_id.isChecked():
            fields.append("form_id")
        return fields

    def set_results(self, results: Iterable[Tuple[str, str, Record]]) -> None:
        self._results = []
        self._results_model.removeRows(0, self._results_model.rowCount())
        for label, type_text, record in results:
            item = QStandardItem(label)
            item.setData(record, Qt.ItemDataRole.UserRole + 1)
            type_item = QStandardItem(type_text)
            type_item.setEditable(False)
            self._results_model.appendRow([item, type_item])
            self._results.append((label, record))

    def header_state(self):
        return self._results_view.header().saveState()

    def restore_header_state(self, state) -> bool:
        return self._results_view.header().restoreState(state)

    def _apply_default_column_sizes(self) -> None:
        header = self._results_view.header()
        self._results_view.resizeColumnToContents(1)
        base_width = max(320, header.sectionSizeHint(0))
        self._results_view.setColumnWidth(0, base_width)

    def _activate_selected(self) -> None:
        indexes = self._results_view.selectedIndexes()
        if not indexes:
            return
        index = indexes[0].siblingAtColumn(0)
        item = self._results_model.itemFromIndex(index)
        if item is None:
            return
        record = item.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(record, Record):
            self.record_selected.emit(record)

    def focus_input(self) -> None:
        self._query.setFocus()
        self._query.selectAll()
