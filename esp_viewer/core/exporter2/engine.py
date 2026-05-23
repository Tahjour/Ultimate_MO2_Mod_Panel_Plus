import os
import time
from typing import Dict, Iterable, List, Optional, Tuple

from esp_viewer.core.data_types import Group, PluginFile, Record
from esp_viewer.core.search_engine import iter_groups, iter_records

from .base import ExportConfig, ExportResult, ExportedFile
from .filters import filter_records
from .formatters import (
    ClipboardFormatter,
    CSVExportFormatter,
    HTMLExportFormatter,
    JSONExportFormatter,
    LuaExportFormatter,
    PythonDictFormatter,
    TXTExportFormatter,
    XMLExportFormatter,
)
from .serializers import (
    build_record_paths,
    iter_group_contexts,
    serialize_detail_rows,
    serialize_group,
    serialize_plugin_summary,
    serialize_record,
    serialize_subrecords,
)


class ExportEngine:
    def __init__(self, plugin: PluginFile, config: ExportConfig, resolve_full_name) -> None:
        self._plugin = plugin
        self._config = config
        self._resolve_full_name = resolve_full_name
        self._formatters = {
            "json": JSONExportFormatter(),
            "csv": CSVExportFormatter(",", "csv"),
            "tsv": CSVExportFormatter("\t", "tsv"),
            "txt": TXTExportFormatter(),
            "html": HTMLExportFormatter(),
            "xml": XMLExportFormatter(),
            "lua": LuaExportFormatter(),
            "python": PythonDictFormatter(),
            "clipboard": ClipboardFormatter(),
        }

    def _collect_scope(self) -> Tuple[List[Record], List[Group]]:
        records: List[Record] = []
        groups: List[Group] = []
        scope = self._config.scope
        if scope == "entire_plugin":
            records = list(iter_records(self._plugin.children))
            groups = list(iter_groups(self._plugin.children))
        elif scope in {"current_selection", "filtered", "search"}:
            if self._config.selected_records is not None:
                records = list(self._config.selected_records)
            if self._config.selected_groups is not None:
                groups = list(self._config.selected_groups)
        elif scope == "custom":
            signature_set = {sig.upper() for sig in self._config.custom_signatures}
            for record in iter_records(self._plugin.children):
                if record.signature.upper() in signature_set:
                    records.append(record)
            for group in iter_groups(self._plugin.children):
                if self._group_has_signature(group, signature_set):
                    groups.append(group)
        else:
            records = list(iter_records(self._plugin.children))
            groups = list(iter_groups(self._plugin.children))
        return records, groups

    def _group_has_signature(self, group: Group, signatures: set[str]) -> bool:
        for child in group.children:
            if isinstance(child, Record) and child.signature.upper() in signatures:
                return True
            if isinstance(child, Group) and self._group_has_signature(child, signatures):
                return True
        return False

    def collect(self) -> Tuple[List[Record], List[Group]]:
        records, groups = self._collect_scope()
        records = filter_records(records, self._config.filters, self._resolve_full_name)
        return records, groups

    def export(self, progress_callback=None, cancel_check=None) -> ExportResult:
        start = time.perf_counter()
        files: List[ExportedFile] = []
        errors: List[str] = []
        total_records = 0
        clipboard_text: Optional[str] = None

        records, groups = self.collect()
        record_paths = build_record_paths(self._plugin.children)

        record_rows = [
            serialize_record(record, self._plugin, self._resolve_full_name, record_paths)
            for record in records
        ]
        group_ids = {id(group) for group in groups}
        group_rows = [
            serialize_group(group, self._plugin, depth, path)
            for group, depth, path in iter_group_contexts(self._plugin.children, self._plugin)
            if not group_ids or id(group) in group_ids
        ]
        subrecord_rows: List[dict] = []
        detail_rows: List[dict] = []
        for index, record in enumerate(records):
            if cancel_check and cancel_check():
                break
            if "subrecords" in self._config.data_types:
                subrecord_rows.extend(serialize_subrecords(record, self._plugin, self._resolve_full_name))
            if "details" in self._config.data_types:
                try:
                    detail_rows.extend(serialize_detail_rows(record, self._plugin, self._resolve_full_name))
                except Exception:
                    continue
            if progress_callback:
                progress_callback(index + 1, len(records))

        summary_rows = serialize_plugin_summary(self._plugin) if "summary" in self._config.data_types else []

        data_map = {
            "records": (record_rows, self._config.record_fields),
            "groups": (group_rows, self._config.group_fields),
            "subrecords": (subrecord_rows, self._config.subrecord_fields),
            "details": (detail_rows, ["parent_form_id", "parent_editor_id", "parent_signature", "path", "name", "value", "depth", "refs"]),
            "summary": (summary_rows, ["path", "file_size", "header_size", "localized", "masters", "is_esl", "load_order"]),
        }

        for fmt in self._config.formats:
            formatter = self._formatters.get(fmt)
            if formatter is None:
                continue
            ext = formatter.file_extension()
            base = self._config.base_filename
            for data_type, (rows, fields) in data_map.items():
                if data_type not in self._config.data_types:
                    continue
                if not rows:
                    continue
                options = self._config.format_options.get(fmt, {})
                if fmt == "clipboard":
                    text = formatter.write_table("", rows, fields, options)
                    section = f"[{data_type}]\n{text}\n"
                    clipboard_text = (clipboard_text or "") + section
                    total_records += len(rows)
                    continue
                path = os.path.join(self._config.output_dir, f"{base}_{data_type}.{ext}")
                try:
                    count = formatter.write_table(path, rows, fields, options)
                    size = os.path.getsize(path)
                    files.append(ExportedFile(path=path, record_count=count, size=size))
                    total_records += count
                except Exception as exc:
                    errors.append(str(exc))

        duration = time.perf_counter() - start
        success = not errors
        return ExportResult(
            success=success,
            files=files,
            total_records=total_records,
            duration_seconds=duration,
            errors=errors,
            clipboard_text=clipboard_text,
        )

    def preview(self, limit: int = 20) -> Dict[str, str]:
        records, groups = self.collect()
        records = records[:limit]
        groups = groups[:limit]
        record_paths = build_record_paths(self._plugin.children)
        record_rows = [
            serialize_record(record, self._plugin, self._resolve_full_name, record_paths)
            for record in records
        ]
        group_ids = {id(group) for group in groups}
        group_rows = [
            serialize_group(group, self._plugin, depth, path)
            for group, depth, path in iter_group_contexts(self._plugin.children, self._plugin)
            if not group_ids or id(group) in group_ids
        ]
        previews: Dict[str, str] = {}
        data_map = {
            "records": (record_rows, self._config.record_fields),
            "groups": (group_rows, self._config.group_fields),
        }
        for fmt in self._config.formats:
            formatter = self._formatters.get(fmt)
            if formatter is None:
                continue
            if fmt == "clipboard":
                continue
            ext = formatter.file_extension()
            for data_type, (rows, fields) in data_map.items():
                if data_type not in self._config.data_types:
                    continue
                if not rows:
                    continue
                path = os.path.join(self._config.output_dir, f"__preview_{data_type}__.{ext}")
                try:
                    formatter.write_table(path, rows, fields, self._config.format_options.get(fmt, {}))
                    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                        previews[f"{data_type}_{fmt}"] = handle.read()
                    os.remove(path)
                except Exception:
                    continue
        return previews
