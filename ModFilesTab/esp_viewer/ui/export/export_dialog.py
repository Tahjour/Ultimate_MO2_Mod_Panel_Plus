import json
import os
from typing import Optional, Set

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_viewer.core.data_types import PluginFile
from esp_viewer.core.search_engine import iter_records
from esp_viewer.core.exporter2 import ExportConfig, ExportEngine
from esp_viewer.core.exporter2.base import ExportFilters
from esp_viewer.ui.export.fields_panel import FieldsPanel
from esp_viewer.ui.export.filter_panel import FilterPanel
from esp_viewer.ui.export.format_panel import FormatPanel
from esp_viewer.ui.export.preset_widget import PresetWidget
from esp_viewer.ui.export.preview_widget import PreviewWidget
from esp_viewer.ui.export.scope_panel import ScopePanel


class ExportDialog(QDialog):
    def __init__(
        self,
        plugin: PluginFile,
        default_output_dir: str,
        base_filename: str,
        resolve_full_name,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._plugin = plugin
        self._default_output_dir = default_output_dir
        self._base_filename = base_filename
        self._resolve_full_name = resolve_full_name
        self._output_dir: Optional[str] = None
        self._settings = QSettings("esp_viewer", "esp_viewer")
        self.setWindowTitle("Export data")

        self._scope_panel = ScopePanel(self)
        self._fields_panel = FieldsPanel(self)
        self._format_panel = FormatPanel(self)
        self._filter_panel = FilterPanel(self)
        self._preview = PreviewWidget(self)
        self._preset_widget = PresetWidget(self)

        self._path_label = QLabel(self)
        self._path_label.setText(self._default_output_dir)
        self._choose_dir_button = QPushButton("Browse", self)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        output_widget = QWidget(self)
        output_layout = QHBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self._path_label, 1)
        output_layout.addWidget(self._choose_dir_button)

        left_column = QVBoxLayout()
        left_column.addWidget(self._preset_widget)
        left_column.addWidget(self._scope_panel)
        left_column.addWidget(self._fields_panel)
        left_column.addStretch(1)

        right_column = QVBoxLayout()
        right_column.addWidget(self._format_panel)
        right_column.addWidget(self._filter_panel)
        right_column.addWidget(self._preview, 1)

        main_row = QHBoxLayout()
        main_row.addLayout(left_column, 1)
        main_row.addLayout(right_column, 1)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output folder:", self))
        output_row.addWidget(output_widget, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(main_row, 1)
        layout.addLayout(output_row)
        layout.addWidget(buttons)

        self._configure_scope_signatures()
        self._apply_default_fields()
        self._restore_last_state()
        self._update_output_dir_label()
        self._refresh_presets()
        self._update_preview()

        self._choose_dir_button.clicked.connect(self._choose_output_dir)
        self._preset_widget.load_button().clicked.connect(self._load_selected_preset)
        self._preset_widget.save_button().clicked.connect(self._save_preset)
        self._preset_widget.delete_button().clicked.connect(self._delete_preset)
        self._scope_panel.scope_changed.connect(lambda _: self._update_preview())
        self._scope_panel.custom_selection_changed.connect(self._update_preview)
        self._fields_panel.changed.connect(self._update_preview)
        self._format_panel.changed.connect(self._update_preview)
        self._filter_panel.changed.connect(self._update_preview)
        self._preset_widget.combo().currentIndexChanged.connect(self._update_preview)

    def _apply_default_fields(self) -> None:
        self._fields_panel.set_record_fields(
            [
                "signature",
                "record_type_name",
                "form_id",
                "form_id_hex",
                "editor_id",
                "full_name",
            ]
        )
        self._fields_panel.set_group_fields(["label", "group_type", "children_count"])
        self._fields_panel.set_subrecord_fields(["subrecord_signature", "subrecord_size", "value_formatted"])

    def _configure_scope_signatures(self) -> None:
        signature_counts = {}
        signature_labels = {}
        for record in iter_records(self._plugin.children):
            signature = record.signature
            signature_counts[signature] = signature_counts.get(signature, 0) + 1
        from esp_viewer.constants2 import RECORD_SIGNATURE_TYPES

        for signature, label in RECORD_SIGNATURE_TYPES.items():
            if signature in signature_counts:
                signature_labels[signature] = label
        self._scope_panel.set_signatures(signature_counts, signature_labels)

    def _update_output_dir_label(self) -> None:
        output_dir = self._output_dir or self._default_output_dir
        self._path_label.setText(output_dir)

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Export folder", self._output_dir or self._default_output_dir)
        if directory:
            self._output_dir = directory
            self._update_output_dir_label()
            self._update_preview()

    def _build_filters(self) -> ExportFilters:
        return self._filter_panel.build_filters()

    def _build_formats(self) -> Set[str]:
        return self._format_panel.selected_formats()

    def build_config(self) -> Optional[ExportConfig]:
        output_dir = self._output_dir or self._default_output_dir
        record_fields = self._fields_panel.selected_record_fields()
        group_fields = self._fields_panel.selected_group_fields()
        subrecord_fields = self._fields_panel.selected_subrecord_fields()
        data_types = self._fields_panel.selected_data_types()
        formats = self._build_formats()
        if not formats or not data_types:
            return None
        if "records" in data_types and not record_fields:
            return None
        if "groups" in data_types and not group_fields:
            return None
        if "subrecords" in data_types and not subrecord_fields:
            return None
        filters = self._build_filters()
        scope_key = self._scope_panel.scope_key()
        custom_signatures = self._scope_panel.custom_signatures() if scope_key == "custom" else set()
        return ExportConfig(
            scope=scope_key,
            custom_signatures=custom_signatures,
            data_types=data_types,
            record_fields=record_fields,
            group_fields=group_fields,
            subrecord_fields=subrecord_fields,
            formats=formats,
            format_options=self._format_panel.format_options(),
            filters=filters,
            output_dir=output_dir,
            base_filename=self._base_filename,
        )

    def _update_preview(self) -> None:
        config = self.build_config()
        if config is None:
            self._preview.set_preview_text("")
            return
        engine = ExportEngine(self._plugin, config, self._resolve_full_name)
        previews = engine.preview(limit=20)
        text_parts = []
        for key, text in previews.items():
            text_parts.append(f"[{key}]\n{text}")
        self._preview.set_preview_text("\n\n".join(text_parts))

    def _preset_state(self) -> dict:
        return {
            "scope": self._scope_panel.state(),
            "fields": self._fields_panel.state(),
            "formats": self._format_panel.state(),
            "filters": self._filter_panel.state(),
            "output_dir": self._output_dir or self._default_output_dir,
        }

    def _apply_state(self, state: dict) -> None:
        if "scope" in state and isinstance(state["scope"], dict):
            self._scope_panel.apply_state(state["scope"])
        if "fields" in state and isinstance(state["fields"], dict):
            self._fields_panel.apply_state(state["fields"])
        if "formats" in state and isinstance(state["formats"], dict):
            self._format_panel.apply_state(state["formats"])
        if "filters" in state and isinstance(state["filters"], dict):
            self._filter_panel.apply_state(state["filters"])
        output_dir = state.get("output_dir")
        if isinstance(output_dir, str) and output_dir:
            self._output_dir = output_dir
        self._update_output_dir_label()
        self._update_preview()

    def _read_presets(self) -> dict:
        self._settings.beginGroup("export")
        raw = self._settings.value("presets", "{}")
        self._settings.endGroup()
        if not isinstance(raw, str):
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return data
        return {}

    def _write_presets(self, presets: dict) -> None:
        self._settings.beginGroup("export")
        self._settings.setValue("presets", json.dumps(presets, ensure_ascii=False))
        self._settings.endGroup()

    def _refresh_presets(self) -> None:
        presets = self._read_presets()
        names = sorted(presets.keys())
        self._preset_widget.set_presets(names)

    def _load_selected_preset(self) -> None:
        presets = self._read_presets()
        name = self._preset_widget.current_preset_name()
        state = presets.get(name)
        if isinstance(state, dict):
            self._apply_state(state)

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        presets = self._read_presets()
        presets[name] = self._preset_state()
        self._write_presets(presets)
        self._refresh_presets()
        index = self._preset_widget.combo().findText(name)
        if index >= 0:
            self._preset_widget.combo().setCurrentIndex(index)

    def _delete_preset(self) -> None:
        name = self._preset_widget.current_preset_name()
        if not name:
            return
        presets = self._read_presets()
        if name in presets:
            del presets[name]
            self._write_presets(presets)
            self._refresh_presets()

    def _restore_last_state(self) -> None:
        self._settings.beginGroup("export")
        raw = self._settings.value("last_state", "")
        self._settings.endGroup()
        if not isinstance(raw, str) or not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if isinstance(data, dict):
            self._apply_state(data)

    def _save_last_state(self) -> None:
        state = self._preset_state()
        self._settings.beginGroup("export")
        self._settings.setValue("last_state", json.dumps(state, ensure_ascii=False))
        self._settings.endGroup()

    def accept(self) -> None:
        self._save_last_state()
        super().accept()
