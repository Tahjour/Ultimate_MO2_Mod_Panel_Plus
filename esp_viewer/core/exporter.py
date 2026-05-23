import csv
import json
import os
from typing import Callable, Iterable, List, Optional

from esp_viewer.core.data_types import Field, Group, PluginFile, Record
from esp_viewer.formatting.group_formatter import format_group_label
from esp_viewer.formatting.record_formatter import DetailNode, StructuredSubrecordParser


def serialize_record(record: Record, resolve_full_name: Callable[[Record], Optional[str]]) -> dict:
    full_name = resolve_full_name(record)
    return {
        "signature": record.signature,
        "data_size": record.data_size,
        "flags_raw": record.flags,
        "form_id": f"0x{record.form_id:08X}",
        "form_id_raw": record.form_id,
        "vci1": record.vci1,
        "form_version": record.form_version,
        "vci2": record.vci2,
        "editor_id": record.editor_id,
        "full_name": full_name,
        "flags": f"0x{record.flags:08X}",
        "flag_names": record.flag_names,
        "is_compressed": record.is_compressed,
        "parse_error": record.parse_error,
        "raw_offset": record.raw_offset,
    }


def serialize_group(group: Group, plugin) -> dict:
    return {
        "label": format_group_label(group, plugin),
        "group_type": group.group_type,
        "group_size": group.group_size,
        "stamp": group.stamp,
        "unknown1": group.unknown1,
        "unknown2": group.unknown2,
        "raw_offset": group.raw_offset,
        "children_count": len(group.children),
    }


def serialize_detail_node(node: DetailNode) -> dict:
    return {
        "name": node.name,
        "value": node.value,
        "refs": [
            {"signature": signature, "form_id": form_id}
            for signature, form_id in node.refs
        ],
        "children": [serialize_detail_node(child) for child in node.children],
    }


def serialize_field(field_obj: Field) -> dict:
    return {
        "signature": field_obj.signature,
        "size": field_obj.size,
        "raw": field_obj.raw.hex(" ").upper(),
    }


def serialize_record_full(record: Record, plugin: Optional[PluginFile], resolve_full_name) -> dict:
    payload = serialize_record(record, resolve_full_name)
    payload["fields"] = [serialize_field(field_obj) for field_obj in record.fields]
    payload["details"] = []
    try:
        parser = StructuredSubrecordParser(record, plugin)
        payload["details"] = [serialize_detail_node(node) for node in parser.iter_nodes()]
    except Exception as exc:
        payload["detail_error"] = str(exc)
    return payload


def serialize_node_tree(
    node: Record | Group,
    plugin: PluginFile,
    resolve_full_name,
) -> dict:
    if isinstance(node, Record):
        return {
            "type": "record",
            "data": serialize_record_full(node, plugin, resolve_full_name),
        }
    return {
        "type": "group",
        "data": serialize_group(node, plugin),
        "children": [serialize_node_tree(child, plugin, resolve_full_name) for child in node.children],
    }


def export_plugin_json(path: str, plugin: PluginFile, resolve_full_name) -> None:
    load_order = None
    if plugin.load_order is not None:
        load_order = {
            "plugin_name": plugin.load_order.plugin_name,
            "masters": plugin.load_order.masters,
        }
    payload = {
        "plugin": {
            "path": plugin.path,
            "file_size": plugin.file_size,
            "header_size": plugin.header_size,
            "localized": plugin.localized,
            "masters": plugin.masters,
            "is_esl": plugin.is_esl,
            "load_order": load_order,
        },
        "children": [serialize_node_tree(child, plugin, resolve_full_name) for child in plugin.children],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def export_records_json(
    path: str,
    records: Iterable[Record],
    resolve_full_name,
    fields: List[str],
) -> None:
    payload = [filter_fields(serialize_record(record, resolve_full_name), fields) for record in records]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def export_records_txt(
    path: str,
    records: Iterable[Record],
    resolve_full_name,
    fields: List[str],
) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            data = filter_fields(serialize_record(record, resolve_full_name), fields)
            line = "\t".join(format_export_value(data.get(field)) for field in fields)
            handle.write(line + "\n")


def export_records_csv(
    path: str,
    records: Iterable[Record],
    resolve_full_name,
    fields: List[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for record in records:
            data = filter_fields(serialize_record(record, resolve_full_name), fields)
            writer.writerow([format_export_value(data.get(field)) for field in fields])


def export_groups_json(
    path: str,
    groups: Iterable[Group],
    plugin,
    fields: List[str],
) -> None:
    payload = [filter_fields(serialize_group(group, plugin), fields) for group in groups]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def export_groups_txt(
    path: str,
    groups: Iterable[Group],
    plugin,
    fields: List[str],
) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for group in groups:
            data = filter_fields(serialize_group(group, plugin), fields)
            line = "\t".join(format_export_value(data.get(field)) for field in fields)
            handle.write(line + "\n")


def export_groups_csv(
    path: str,
    groups: Iterable[Group],
    plugin,
    fields: List[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for group in groups:
            data = filter_fields(serialize_group(group, plugin), fields)
            writer.writerow([format_export_value(data.get(field)) for field in fields])


def build_export_paths(output_dir: str, base_name: str, suffix: str, formats: Iterable[str]) -> List[str]:
    paths: List[str] = []
    for fmt in formats:
        ext = fmt.lower()
        filename = f"{base_name}{suffix}.{ext}"
        paths.append(os.path.join(output_dir, filename))
    return paths


def filter_fields(data: dict, fields: List[str]) -> dict:
    return {field: data.get(field) for field in fields}


def format_export_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)
