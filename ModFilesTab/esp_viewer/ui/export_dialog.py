from enum import Enum
from typing import List

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
)


class ExportScope(Enum):
    ALL_RECORDS = "all_records"
    CURRENT_SELECTION = "current_selection"


class ExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export data")

        self._format_json = QCheckBox("JSON", self)
        self._format_txt = QCheckBox("TXT", self)
        self._format_csv = QCheckBox("CSV", self)

        self._format_json.setChecked(True)

        format_box = QGroupBox("Formats", self)
        format_layout = QHBoxLayout(format_box)
        format_layout.addWidget(self._format_json)
        format_layout.addWidget(self._format_txt)
        format_layout.addWidget(self._format_csv)
        format_layout.addStretch(1)

        self._type_records = QCheckBox("Records", self)
        self._type_groups = QCheckBox("Groups", self)
        self._type_records.setChecked(True)

        type_box = QGroupBox("Data types", self)
        type_layout = QHBoxLayout(type_box)
        type_layout.addWidget(self._type_records)
        type_layout.addWidget(self._type_groups)
        type_layout.addStretch(1)

        self._scope = QComboBox(self)
        self._scope.addItem("All records", ExportScope.ALL_RECORDS)
        self._scope.addItem("Current selection", ExportScope.CURRENT_SELECTION)

        self._record_signature = QCheckBox("Signature", self)
        self._record_data_size = QCheckBox("Data Size", self)
        self._record_flags_raw = QCheckBox("Flags (raw)", self)
        self._record_form_id = QCheckBox("FormID", self)
        self._record_form_id_raw = QCheckBox("FormID (raw)", self)
        self._record_vci1 = QCheckBox("VCI1", self)
        self._record_form_version = QCheckBox("Form Version", self)
        self._record_vci2 = QCheckBox("VCI2", self)
        self._record_editor_id = QCheckBox("EditorID", self)
        self._record_full_name = QCheckBox("Full Name", self)
        self._record_flags = QCheckBox("Flags", self)
        self._record_flag_names = QCheckBox("Flag Names", self)
        self._record_is_compressed = QCheckBox("Compressed", self)
        self._record_parse_error = QCheckBox("Parse Error", self)
        self._record_raw_offset = QCheckBox("Offset", self)

        for checkbox in (
            self._record_signature,
            self._record_data_size,
            self._record_flags_raw,
            self._record_form_id,
            self._record_form_id_raw,
            self._record_vci1,
            self._record_form_version,
            self._record_vci2,
            self._record_editor_id,
            self._record_full_name,
            self._record_flags,
            self._record_flag_names,
            self._record_is_compressed,
            self._record_parse_error,
            self._record_raw_offset,
        ):
            checkbox.setChecked(True)

        record_id_box = QGroupBox("Identifiers", self)
        record_id_layout = QHBoxLayout(record_id_box)
        record_id_layout.addWidget(self._record_signature)
        record_id_layout.addWidget(self._record_form_id)
        record_id_layout.addWidget(self._record_form_id_raw)
        record_id_layout.addWidget(self._record_editor_id)
        record_id_layout.addWidget(self._record_full_name)
        record_id_layout.addStretch(1)

        record_version_box = QGroupBox("Version and size", self)
        record_version_layout = QHBoxLayout(record_version_box)
        record_version_layout.addWidget(self._record_data_size)
        record_version_layout.addWidget(self._record_vci1)
        record_version_layout.addWidget(self._record_form_version)
        record_version_layout.addWidget(self._record_vci2)
        record_version_layout.addStretch(1)

        record_flags_box = QGroupBox("Flags", self)
        record_flags_layout = QHBoxLayout(record_flags_box)
        record_flags_layout.addWidget(self._record_flags)
        record_flags_layout.addWidget(self._record_flags_raw)
        record_flags_layout.addWidget(self._record_flag_names)
        record_flags_layout.addStretch(1)

        record_tech_box = QGroupBox("Technical", self)
        record_tech_layout = QHBoxLayout(record_tech_box)
        record_tech_layout.addWidget(self._record_is_compressed)
        record_tech_layout.addWidget(self._record_parse_error)
        record_tech_layout.addWidget(self._record_raw_offset)
        record_tech_layout.addStretch(1)

        self._group_label = QCheckBox("Label", self)
        self._group_type = QCheckBox("Group Type", self)
        self._group_size = QCheckBox("Group Size", self)
        self._group_stamp = QCheckBox("Stamp", self)
        self._group_unknown1 = QCheckBox("Unknown1", self)
        self._group_unknown2 = QCheckBox("Unknown2", self)
        self._group_raw_offset = QCheckBox("Offset", self)
        self._group_children_count = QCheckBox("Children", self)

        for checkbox in (
            self._group_label,
            self._group_type,
            self._group_size,
            self._group_stamp,
            self._group_unknown1,
            self._group_unknown2,
            self._group_raw_offset,
            self._group_children_count,
        ):
            checkbox.setChecked(True)

        group_main_box = QGroupBox("Group info", self)
        group_main_layout = QHBoxLayout(group_main_box)
        group_main_layout.addWidget(self._group_label)
        group_main_layout.addWidget(self._group_type)
        group_main_layout.addWidget(self._group_size)
        group_main_layout.addWidget(self._group_stamp)
        group_main_layout.addStretch(1)

        group_extra_box = QGroupBox("Extra", self)
        group_extra_layout = QHBoxLayout(group_extra_box)
        group_extra_layout.addWidget(self._group_unknown1)
        group_extra_layout.addWidget(self._group_unknown2)
        group_extra_layout.addWidget(self._group_raw_offset)
        group_extra_layout.addWidget(self._group_children_count)
        group_extra_layout.addStretch(1)

        scope_box = QGroupBox("Scope", self)
        scope_layout = QFormLayout(scope_box)
        scope_layout.addRow("Export", self._scope)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self._type_records.toggled.connect(self._update_field_groups)
        self._type_groups.toggled.connect(self._update_field_groups)
        self._update_field_groups()

        layout = QVBoxLayout(self)
        layout.addWidget(format_box)
        layout.addWidget(type_box)
        layout.addWidget(scope_box)
        layout.addWidget(record_id_box)
        layout.addWidget(record_version_box)
        layout.addWidget(record_flags_box)
        layout.addWidget(record_tech_box)
        layout.addWidget(group_main_box)
        layout.addWidget(group_extra_box)
        layout.addWidget(buttons)

    def selected_formats(self) -> List[str]:
        formats: List[str] = []
        if self._format_json.isChecked():
            formats.append("json")
        if self._format_txt.isChecked():
            formats.append("txt")
        if self._format_csv.isChecked():
            formats.append("csv")
        return formats

    def selected_types(self) -> List[str]:
        types: List[str] = []
        if self._type_records.isChecked():
            types.append("records")
        if self._type_groups.isChecked():
            types.append("groups")
        return types

    def selected_record_fields(self) -> List[str]:
        fields: List[str] = []
        if self._record_signature.isChecked():
            fields.append("signature")
        if self._record_data_size.isChecked():
            fields.append("data_size")
        if self._record_flags_raw.isChecked():
            fields.append("flags_raw")
        if self._record_form_id.isChecked():
            fields.append("form_id")
        if self._record_form_id_raw.isChecked():
            fields.append("form_id_raw")
        if self._record_vci1.isChecked():
            fields.append("vci1")
        if self._record_form_version.isChecked():
            fields.append("form_version")
        if self._record_vci2.isChecked():
            fields.append("vci2")
        if self._record_editor_id.isChecked():
            fields.append("editor_id")
        if self._record_full_name.isChecked():
            fields.append("full_name")
        if self._record_flags.isChecked():
            fields.append("flags")
        if self._record_flag_names.isChecked():
            fields.append("flag_names")
        if self._record_is_compressed.isChecked():
            fields.append("is_compressed")
        if self._record_parse_error.isChecked():
            fields.append("parse_error")
        if self._record_raw_offset.isChecked():
            fields.append("raw_offset")
        return fields

    def selected_group_fields(self) -> List[str]:
        fields: List[str] = []
        if self._group_label.isChecked():
            fields.append("label")
        if self._group_type.isChecked():
            fields.append("group_type")
        if self._group_size.isChecked():
            fields.append("group_size")
        if self._group_stamp.isChecked():
            fields.append("stamp")
        if self._group_unknown1.isChecked():
            fields.append("unknown1")
        if self._group_unknown2.isChecked():
            fields.append("unknown2")
        if self._group_raw_offset.isChecked():
            fields.append("raw_offset")
        if self._group_children_count.isChecked():
            fields.append("children_count")
        return fields

    def scope(self) -> ExportScope:
        data = self._scope.currentData()
        if isinstance(data, ExportScope):
            return data
        return ExportScope.ALL_RECORDS

    def _update_field_groups(self) -> None:
        record_enabled = self._type_records.isChecked()
        group_enabled = self._type_groups.isChecked()
        for checkbox in (
            self._record_signature,
            self._record_data_size,
            self._record_flags_raw,
            self._record_form_id,
            self._record_form_id_raw,
            self._record_vci1,
            self._record_form_version,
            self._record_vci2,
            self._record_editor_id,
            self._record_full_name,
            self._record_flags,
            self._record_flag_names,
            self._record_is_compressed,
            self._record_parse_error,
            self._record_raw_offset,
        ):
            checkbox.setEnabled(record_enabled)
        for checkbox in (
            self._group_label,
            self._group_type,
            self._group_size,
            self._group_stamp,
            self._group_unknown1,
            self._group_unknown2,
            self._group_raw_offset,
            self._group_children_count,
        ):
            checkbox.setEnabled(group_enabled)
