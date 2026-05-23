from typing import List, Set

from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


class FieldsPanel(QGroupBox):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Fields")

        self._type_records = QCheckBox("Records", self)
        self._type_groups = QCheckBox("Groups", self)
        self._type_subrecords = QCheckBox("Subrecords", self)
        self._type_details = QCheckBox("Details", self)
        self._type_summary = QCheckBox("Summary", self)
        self._type_records.setChecked(True)
        self._type_groups.setChecked(True)

        self._record_signature = QCheckBox("Signature", self)
        self._record_type_name = QCheckBox("Record Type", self)
        self._record_form_id = QCheckBox("FormID", self)
        self._record_form_id_hex = QCheckBox("FormID hex", self)
        self._record_form_id_decimal = QCheckBox("FormID decimal", self)
        self._record_master_file = QCheckBox("Master File", self)
        self._record_editor_id = QCheckBox("EditorID", self)
        self._record_full_name = QCheckBox("Full Name", self)
        self._record_data_size = QCheckBox("Data Size", self)
        self._record_flags = QCheckBox("Flags", self)
        self._record_flag_names = QCheckBox("Flag Names", self)
        self._record_form_version = QCheckBox("Form Version", self)
        self._record_vci1 = QCheckBox("VCI1", self)
        self._record_vci2 = QCheckBox("VCI2", self)
        self._record_is_compressed = QCheckBox("Compressed", self)
        self._record_raw_offset = QCheckBox("Offset", self)
        self._record_parse_error = QCheckBox("Parse Error", self)
        self._record_subrecord_count = QCheckBox("Subrecord Count", self)
        self._record_subrecord_list = QCheckBox("Subrecord List", self)
        self._record_parent_group_type = QCheckBox("Parent Group Type", self)
        self._record_parent_group_label = QCheckBox("Parent Group Label", self)
        self._record_full_path = QCheckBox("Full Path", self)

        record_box = QGroupBox("Record fields", self)
        record_layout = QVBoxLayout(record_box)
        record_row1 = QHBoxLayout()
        record_row1.addWidget(self._record_signature)
        record_row1.addWidget(self._record_type_name)
        record_row1.addWidget(self._record_form_id)
        record_row1.addWidget(self._record_form_id_hex)
        record_row1.addWidget(self._record_form_id_decimal)
        record_row1.addWidget(self._record_master_file)
        record_row1.addStretch(1)

        record_row2 = QHBoxLayout()
        record_row2.addWidget(self._record_editor_id)
        record_row2.addWidget(self._record_full_name)
        record_row2.addWidget(self._record_data_size)
        record_row2.addWidget(self._record_flags)
        record_row2.addWidget(self._record_flag_names)
        record_row2.addStretch(1)

        record_row3 = QHBoxLayout()
        record_row3.addWidget(self._record_form_version)
        record_row3.addWidget(self._record_vci1)
        record_row3.addWidget(self._record_vci2)
        record_row3.addWidget(self._record_is_compressed)
        record_row3.addWidget(self._record_raw_offset)
        record_row3.addWidget(self._record_parse_error)
        record_row3.addStretch(1)

        record_row4 = QHBoxLayout()
        record_row4.addWidget(self._record_subrecord_count)
        record_row4.addWidget(self._record_subrecord_list)
        record_row4.addWidget(self._record_parent_group_type)
        record_row4.addWidget(self._record_parent_group_label)
        record_row4.addWidget(self._record_full_path)
        record_row4.addStretch(1)

        record_layout.addLayout(record_row1)
        record_layout.addLayout(record_row2)
        record_layout.addLayout(record_row3)
        record_layout.addLayout(record_row4)

        self._group_label = QCheckBox("Label", self)
        self._group_label_raw_hex = QCheckBox("Label Hex", self)
        self._group_type = QCheckBox("Group Type", self)
        self._group_type_id = QCheckBox("Group Type ID", self)
        self._group_size = QCheckBox("Group Size", self)
        self._group_stamp = QCheckBox("Stamp", self)
        self._group_unknown1 = QCheckBox("Unknown1", self)
        self._group_unknown2 = QCheckBox("Unknown2", self)
        self._group_raw_offset = QCheckBox("Offset", self)
        self._group_children_count = QCheckBox("Children Count", self)
        self._group_record_count = QCheckBox("Record Count", self)
        self._group_depth = QCheckBox("Depth", self)
        self._group_full_path = QCheckBox("Full Path", self)

        group_box = QGroupBox("Group fields", self)
        group_layout = QVBoxLayout(group_box)
        group_row1 = QHBoxLayout()
        group_row1.addWidget(self._group_label)
        group_row1.addWidget(self._group_label_raw_hex)
        group_row1.addWidget(self._group_type)
        group_row1.addWidget(self._group_type_id)
        group_row1.addWidget(self._group_size)
        group_row1.addWidget(self._group_stamp)
        group_row1.addStretch(1)

        group_row2 = QHBoxLayout()
        group_row2.addWidget(self._group_unknown1)
        group_row2.addWidget(self._group_unknown2)
        group_row2.addWidget(self._group_raw_offset)
        group_row2.addWidget(self._group_children_count)
        group_row2.addWidget(self._group_record_count)
        group_row2.addWidget(self._group_depth)
        group_row2.addWidget(self._group_full_path)
        group_row2.addStretch(1)

        group_layout.addLayout(group_row1)
        group_layout.addLayout(group_row2)

        self._subrecord_parent_form_id = QCheckBox("Parent FormID", self)
        self._subrecord_parent_editor_id = QCheckBox("Parent EditorID", self)
        self._subrecord_parent_signature = QCheckBox("Parent Signature", self)
        self._subrecord_signature = QCheckBox("Subrecord Signature", self)
        self._subrecord_size = QCheckBox("Subrecord Size", self)
        self._subrecord_index = QCheckBox("Subrecord Index", self)
        self._subrecord_value_formatted = QCheckBox("Value Formatted", self)
        self._subrecord_value_raw = QCheckBox("Value Raw Hex", self)

        subrecord_box = QGroupBox("Subrecord fields", self)
        subrecord_layout = QVBoxLayout(subrecord_box)
        subrecord_row1 = QHBoxLayout()
        subrecord_row1.addWidget(self._subrecord_parent_form_id)
        subrecord_row1.addWidget(self._subrecord_parent_editor_id)
        subrecord_row1.addWidget(self._subrecord_parent_signature)
        subrecord_row1.addWidget(self._subrecord_signature)
        subrecord_row1.addStretch(1)

        subrecord_row2 = QHBoxLayout()
        subrecord_row2.addWidget(self._subrecord_size)
        subrecord_row2.addWidget(self._subrecord_index)
        subrecord_row2.addWidget(self._subrecord_value_formatted)
        subrecord_row2.addWidget(self._subrecord_value_raw)
        subrecord_row2.addStretch(1)

        subrecord_layout.addLayout(subrecord_row1)
        subrecord_layout.addLayout(subrecord_row2)

        type_box = QGroupBox("Data types", self)
        type_layout = QHBoxLayout(type_box)
        type_layout.addWidget(self._type_records)
        type_layout.addWidget(self._type_groups)
        type_layout.addWidget(self._type_subrecords)
        type_layout.addWidget(self._type_details)
        type_layout.addWidget(self._type_summary)
        type_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(type_box)
        layout.addWidget(record_box)
        layout.addWidget(group_box)
        layout.addWidget(subrecord_box)

        for checkbox in self.findChildren(QCheckBox):
            checkbox.toggled.connect(self._on_any_changed)
        self._type_records.toggled.connect(self._update_field_groups)
        self._type_groups.toggled.connect(self._update_field_groups)
        self._type_subrecords.toggled.connect(self._update_field_groups)
        self._update_field_groups()

    def _on_any_changed(self, *_) -> None:
        self.changed.emit()

    def selected_record_fields(self) -> List[str]:
        fields: List[str] = []
        if self._record_signature.isChecked():
            fields.append("signature")
        if self._record_type_name.isChecked():
            fields.append("record_type_name")
        if self._record_form_id.isChecked():
            fields.append("form_id")
        if self._record_form_id_hex.isChecked():
            fields.append("form_id_hex")
        if self._record_form_id_decimal.isChecked():
            fields.append("form_id_decimal")
        if self._record_master_file.isChecked():
            fields.append("master_file")
        if self._record_editor_id.isChecked():
            fields.append("editor_id")
        if self._record_full_name.isChecked():
            fields.append("full_name")
        if self._record_data_size.isChecked():
            fields.append("data_size")
        if self._record_flags.isChecked():
            fields.append("flags")
        if self._record_flag_names.isChecked():
            fields.append("flag_names")
        if self._record_form_version.isChecked():
            fields.append("form_version")
        if self._record_vci1.isChecked():
            fields.append("vci1")
        if self._record_vci2.isChecked():
            fields.append("vci2")
        if self._record_is_compressed.isChecked():
            fields.append("is_compressed")
        if self._record_raw_offset.isChecked():
            fields.append("raw_offset")
        if self._record_parse_error.isChecked():
            fields.append("parse_error")
        if self._record_subrecord_count.isChecked():
            fields.append("subrecord_count")
        if self._record_subrecord_list.isChecked():
            fields.append("subrecord_list")
        if self._record_parent_group_type.isChecked():
            fields.append("parent_group_type")
        if self._record_parent_group_label.isChecked():
            fields.append("parent_group_label")
        if self._record_full_path.isChecked():
            fields.append("full_path")
        return fields

    def selected_group_fields(self) -> List[str]:
        fields: List[str] = []
        if self._group_label.isChecked():
            fields.append("label")
        if self._group_label_raw_hex.isChecked():
            fields.append("label_raw_hex")
        if self._group_type.isChecked():
            fields.append("group_type")
        if self._group_type_id.isChecked():
            fields.append("group_type_id")
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
        if self._group_record_count.isChecked():
            fields.append("record_count")
        if self._group_depth.isChecked():
            fields.append("depth")
        if self._group_full_path.isChecked():
            fields.append("full_path")
        return fields

    def selected_subrecord_fields(self) -> List[str]:
        fields: List[str] = []
        if self._subrecord_parent_form_id.isChecked():
            fields.append("parent_form_id")
        if self._subrecord_parent_editor_id.isChecked():
            fields.append("parent_editor_id")
        if self._subrecord_parent_signature.isChecked():
            fields.append("parent_signature")
        if self._subrecord_signature.isChecked():
            fields.append("subrecord_signature")
        if self._subrecord_size.isChecked():
            fields.append("subrecord_size")
        if self._subrecord_index.isChecked():
            fields.append("subrecord_index")
        if self._subrecord_value_formatted.isChecked():
            fields.append("value_formatted")
        if self._subrecord_value_raw.isChecked():
            fields.append("value_raw_hex")
        return fields

    def selected_data_types(self) -> Set[str]:
        data_types: Set[str] = set()
        if self._type_records.isChecked():
            data_types.add("records")
        if self._type_groups.isChecked():
            data_types.add("groups")
        if self._type_subrecords.isChecked():
            data_types.add("subrecords")
        if self._type_details.isChecked():
            data_types.add("details")
        if self._type_summary.isChecked():
            data_types.add("summary")
        return data_types

    def set_selected_data_types(self, data_types: Set[str]) -> None:
        self._type_records.setChecked("records" in data_types)
        self._type_groups.setChecked("groups" in data_types)
        self._type_subrecords.setChecked("subrecords" in data_types)
        self._type_details.setChecked("details" in data_types)
        self._type_summary.setChecked("summary" in data_types)
        self._update_field_groups()

    def set_record_fields(self, fields: List[str]) -> None:
        mapping = {
            "signature": self._record_signature,
            "record_type_name": self._record_type_name,
            "form_id": self._record_form_id,
            "form_id_hex": self._record_form_id_hex,
            "form_id_decimal": self._record_form_id_decimal,
            "master_file": self._record_master_file,
            "editor_id": self._record_editor_id,
            "full_name": self._record_full_name,
            "data_size": self._record_data_size,
            "flags": self._record_flags,
            "flag_names": self._record_flag_names,
            "form_version": self._record_form_version,
            "vci1": self._record_vci1,
            "vci2": self._record_vci2,
            "is_compressed": self._record_is_compressed,
            "raw_offset": self._record_raw_offset,
            "parse_error": self._record_parse_error,
            "subrecord_count": self._record_subrecord_count,
            "subrecord_list": self._record_subrecord_list,
            "parent_group_type": self._record_parent_group_type,
            "parent_group_label": self._record_parent_group_label,
            "full_path": self._record_full_path,
        }
        for key, checkbox in mapping.items():
            checkbox.setChecked(key in fields)

    def set_group_fields(self, fields: List[str]) -> None:
        mapping = {
            "label": self._group_label,
            "label_raw_hex": self._group_label_raw_hex,
            "group_type": self._group_type,
            "group_type_id": self._group_type_id,
            "group_size": self._group_size,
            "stamp": self._group_stamp,
            "unknown1": self._group_unknown1,
            "unknown2": self._group_unknown2,
            "raw_offset": self._group_raw_offset,
            "children_count": self._group_children_count,
            "record_count": self._group_record_count,
            "depth": self._group_depth,
            "full_path": self._group_full_path,
        }
        for key, checkbox in mapping.items():
            checkbox.setChecked(key in fields)

    def set_subrecord_fields(self, fields: List[str]) -> None:
        mapping = {
            "parent_form_id": self._subrecord_parent_form_id,
            "parent_editor_id": self._subrecord_parent_editor_id,
            "parent_signature": self._subrecord_parent_signature,
            "subrecord_signature": self._subrecord_signature,
            "subrecord_size": self._subrecord_size,
            "subrecord_index": self._subrecord_index,
            "value_formatted": self._subrecord_value_formatted,
            "value_raw_hex": self._subrecord_value_raw,
        }
        for key, checkbox in mapping.items():
            checkbox.setChecked(key in fields)

    def _update_field_groups(self) -> None:
        record_enabled = self._type_records.isChecked()
        group_enabled = self._type_groups.isChecked()
        subrecord_enabled = self._type_subrecords.isChecked()
        for checkbox in (
            self._record_signature,
            self._record_type_name,
            self._record_form_id,
            self._record_form_id_hex,
            self._record_form_id_decimal,
            self._record_master_file,
            self._record_editor_id,
            self._record_full_name,
            self._record_data_size,
            self._record_flags,
            self._record_flag_names,
            self._record_form_version,
            self._record_vci1,
            self._record_vci2,
            self._record_is_compressed,
            self._record_raw_offset,
            self._record_parse_error,
            self._record_subrecord_count,
            self._record_subrecord_list,
            self._record_parent_group_type,
            self._record_parent_group_label,
            self._record_full_path,
        ):
            checkbox.setEnabled(record_enabled)
        for checkbox in (
            self._group_label,
            self._group_label_raw_hex,
            self._group_type,
            self._group_type_id,
            self._group_size,
            self._group_stamp,
            self._group_unknown1,
            self._group_unknown2,
            self._group_raw_offset,
            self._group_children_count,
            self._group_record_count,
            self._group_depth,
            self._group_full_path,
        ):
            checkbox.setEnabled(group_enabled)
        for checkbox in (
            self._subrecord_parent_form_id,
            self._subrecord_parent_editor_id,
            self._subrecord_parent_signature,
            self._subrecord_signature,
            self._subrecord_size,
            self._subrecord_index,
            self._subrecord_value_formatted,
            self._subrecord_value_raw,
        ):
            checkbox.setEnabled(subrecord_enabled)

    def state(self) -> dict:
        return {
            "data_types": sorted(self.selected_data_types()),
            "record_fields": self.selected_record_fields(),
            "group_fields": self.selected_group_fields(),
            "subrecord_fields": self.selected_subrecord_fields(),
        }

    def apply_state(self, state: dict) -> None:
        data_types = state.get("data_types", [])
        if isinstance(data_types, list):
            self.set_selected_data_types(set(str(item) for item in data_types))
        record_fields = state.get("record_fields", [])
        if isinstance(record_fields, list):
            self.set_record_fields([str(item) for item in record_fields])
        group_fields = state.get("group_fields", [])
        if isinstance(group_fields, list):
            self.set_group_fields([str(item) for item in group_fields])
        subrecord_fields = state.get("subrecord_fields", [])
        if isinstance(subrecord_fields, list):
            self.set_subrecord_fields([str(item) for item in subrecord_fields])
