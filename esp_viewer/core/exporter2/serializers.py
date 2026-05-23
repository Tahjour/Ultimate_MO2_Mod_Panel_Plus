from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from esp_viewer.constants2 import RECORD_SIGNATURE_TYPES
from esp_viewer.core.data_types import Field, Group, PluginFile, Record
from esp_viewer.formatting.group_formatter import format_group_label, group_type_label
from esp_viewer.formatting.record_formatter import DetailNode, StructuredSubrecordParser


def serialize_record(
    record: Record,
    plugin: Optional[PluginFile],
    resolve_full_name: Callable[[Record], Optional[str]],
    record_paths: Dict[Tuple[str, int], List[Group]],
) -> dict:
    full_name = resolve_full_name(record)
    resolver = plugin.formid_resolver if plugin else None
    formatted_formid = None
    master_file = None
    if resolver:
        formatted_formid = resolver.format_formid(record.form_id, record.signature)
        master_file = resolver.master_name(record.form_id)
    parent_groups = record_paths.get((record.signature, record.form_id), [])
    parent_group = parent_groups[-1] if parent_groups else None
    parent_group_label = format_group_label(parent_group, plugin) if parent_group else None
    parent_group_type = group_type_label(parent_group) if parent_group else None
    path_labels = [format_group_label(group, plugin) for group in parent_groups]
    record_type_name = RECORD_SIGNATURE_TYPES.get(record.signature, record.signature)
    return {
        "signature": record.signature,
        "form_id": formatted_formid or f"[{record.form_id:08X}]",
        "form_id_hex": f"0x{record.form_id:08X}",
        "form_id_decimal": record.form_id,
        "editor_id": record.editor_id,
        "full_name": full_name,
        "data_size": record.data_size,
        "flags": f"0x{record.flags:08X}",
        "flag_names": record.flag_names,
        "form_version": record.form_version,
        "vci1": record.vci1,
        "vci2": record.vci2,
        "is_compressed": record.is_compressed,
        "raw_offset": record.raw_offset,
        "master_file": master_file,
        "record_type_name": record_type_name,
        "parse_error": record.parse_error,
        "subrecord_count": len(record.fields),
        "subrecord_list": [field.signature for field in record.fields],
        "parent_group_type": parent_group_type,
        "parent_group_label": parent_group_label,
        "full_path": " > ".join(path_labels + [record.signature]),
    }


def serialize_group(group: Group, plugin: PluginFile, depth: int, path: Sequence[Group]) -> dict:
    label = format_group_label(group, plugin)
    raw_label = group.label_raw.hex(" ").upper()
    path_labels = [format_group_label(item, plugin) for item in path]
    return {
        "group_type": group_type_label(group),
        "group_type_id": group.group_type,
        "label": label,
        "label_raw_hex": raw_label,
        "group_size": group.group_size,
        "stamp": f"0x{group.stamp:08X}",
        "unknown1": group.unknown1,
        "unknown2": group.unknown2,
        "raw_offset": group.raw_offset,
        "children_count": len(group.children),
        "record_count": count_group_records(group),
        "depth": depth,
        "full_path": " > ".join(path_labels + [label]),
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


def count_group_records(group: Group) -> int:
    total = 0
    for child in group.children:
        if isinstance(child, Record):
            total += 1
        elif isinstance(child, Group):
            total += count_group_records(child)
    return total


def build_record_paths(nodes: Iterable[object]) -> Dict[Tuple[str, int], List[Group]]:
    paths: Dict[Tuple[str, int], List[Group]] = {}

    def visit(items: Iterable[object], stack: List[Group]) -> None:
        for item in items:
            if isinstance(item, Record):
                paths[(item.signature, item.form_id)] = list(stack)
            elif isinstance(item, Group):
                stack.append(item)
                visit(item.children, stack)
                stack.pop()

    visit(nodes, [])
    return paths


def iter_group_contexts(
    nodes: Iterable[object],
    plugin: PluginFile,
) -> Iterable[Tuple[Group, int, List[Group]]]:
    def visit(items: Iterable[object], depth: int, path: List[Group]):
        for item in items:
            if isinstance(item, Group):
                yield (item, depth, list(path))
                yield from visit(item.children, depth + 1, path + [item])

    yield from visit(nodes, 0, [])


def serialize_subrecords(
    record: Record,
    plugin: Optional[PluginFile],
    resolve_full_name: Callable[[Record], Optional[str]],
) -> List[dict]:
    resolver = plugin.formid_resolver if plugin else None
    formatted_formid = None
    if resolver:
        formatted_formid = resolver.format_formid(record.form_id, record.signature)
    entries: List[dict] = []
    for index, field_obj in enumerate(record.fields):
        entries.append(
            {
                "parent_form_id": formatted_formid or f"0x{record.form_id:08X}",
                "parent_editor_id": record.editor_id,
                "parent_signature": record.signature,
                "subrecord_signature": field_obj.signature,
                "subrecord_size": field_obj.size,
                "subrecord_index": index,
                "value_formatted": None,
                "value_raw_hex": field_obj.raw.hex(" ").upper(),
            }
        )
    return entries


def serialize_detail_rows(
    record: Record,
    plugin: Optional[PluginFile],
    resolve_full_name: Callable[[Record], Optional[str]],
) -> List[dict]:
    resolver = plugin.formid_resolver if plugin else None
    formatted_formid = None
    if resolver:
        formatted_formid = resolver.format_formid(record.form_id, record.signature)
    rows: List[dict] = []
    parser = StructuredSubrecordParser(record, plugin)

    def visit(node: DetailNode, path: List[str]) -> None:
        current_path = path + [node.name]
        rows.append(
            {
                "parent_form_id": formatted_formid or f"0x{record.form_id:08X}",
                "parent_editor_id": record.editor_id,
                "parent_signature": record.signature,
                "path": " > ".join(current_path),
                "name": node.name,
                "value": node.value,
                "depth": len(path),
                "refs": [
                    {
                        "signature": signature,
                        "form_id": f"0x{form_id:08X}",
                    }
                    for signature, form_id in node.refs
                ],
            }
        )
        for child in node.children:
            visit(child, current_path)

    for node in parser.iter_nodes():
        visit(node, [])
    return rows


def serialize_plugin_summary(plugin: PluginFile) -> List[dict]:
    load_order = None
    if plugin.load_order is not None:
        load_order = {
            "plugin_name": plugin.load_order.plugin_name,
            "masters": plugin.load_order.masters,
        }
    return [
        {
            "path": plugin.path,
            "file_size": plugin.file_size,
            "header_size": plugin.header_size,
            "localized": plugin.localized,
            "masters": plugin.masters,
            "is_esl": plugin.is_esl,
            "load_order": load_order,
        }
    ]


def filter_fields(data: dict, fields: List[str]) -> dict:
    if not fields:
        return data
    return {field: data.get(field) for field in fields}


def format_export_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}={value[key]}" for key in value)
    return str(value)


def serialize_record_full(
    record: Record,
    plugin: Optional[PluginFile],
    resolve_full_name: Callable[[Record], Optional[str]],
    record_paths: Dict[Tuple[str, int], List[Group]],
) -> dict:
    payload = serialize_record(record, plugin, resolve_full_name, record_paths)
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
    resolve_full_name: Callable[[Record], Optional[str]],
    record_paths: Dict[Tuple[str, int], List[Group]],
    depth: int = 0,
    path: Optional[List[Group]] = None,
) -> dict:
    if isinstance(node, Record):
        return {
            "type": "record",
            "data": serialize_record_full(node, plugin, resolve_full_name, record_paths),
        }
    path = path or []
    return {
        "type": "group",
        "data": serialize_group(node, plugin, depth, path),
        "children": [
            serialize_node_tree(child, plugin, resolve_full_name, record_paths, depth + 1, path + [node])
            for child in node.children
        ],
    }


def filter_fields(data: dict, fields: List[str]) -> dict:
    return {field: data.get(field) for field in fields}


def format_export_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)
