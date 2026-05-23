import struct
from typing import Callable, Optional

from esp_viewer.constants2 import RECORD_SIGNATURE_TYPES
from esp_viewer.core.data_types import GROUP_TYPE_NAMES, Group, PluginFile, Record


def format_record_identity(
    record: Record,
    plugin: Optional[PluginFile] = None,
    resolve_full_name: Optional[Callable[[Record], Optional[str]]] = None,
    include_signature_if_missing: bool = True,
) -> str:
    base = f"0x{record.form_id:08X}"
    if plugin and plugin.formid_resolver:
        base = plugin.formid_resolver.format_formid(record.form_id, record.signature)

    full_name = resolve_full_name(record) if resolve_full_name else record.full_name
    parts = []
    if record.editor_id:
        parts.append(record.editor_id)
    if full_name and full_name != record.editor_id:
        parts.append(f'"{full_name}"')
    if not parts:
        if include_signature_if_missing:
            parts.append(record.signature)
        else:
            return base
    return f"{' '.join(parts)} {base}"


def format_group_label(group: Group, plugin: Optional[PluginFile] = None) -> str:
    label = group.label_raw
    gt = group.group_type

    if gt == 0:
        sig = label.decode("ascii", errors="replace").rstrip("\x00")
        mapping = {
            "TES4": "File Header",
            "WRLD": "Worldspace",
            "CELL": "Cell",
        }
        human = mapping.get(sig) or RECORD_SIGNATURE_TYPES.get(sig)
        if sig == "TES4" and human:
            return f"{sig} - {human}"
        if human:
            return f"{sig} - {human}"
        return sig

    if gt in {1, 6, 7, 8, 9, 10}:
        value = struct.unpack_from("<I", label, 0)[0]
        text = f"0x{value:08X}"
        if plugin and plugin.formid_resolver:
            text = plugin.formid_resolver.format_formid(value)
            target = plugin.formid_resolver.get(value)
            if target is not None:
                type_name = RECORD_SIGNATURE_TYPES.get(target.signature, target.signature)
                prefix = (
                    f"{target.signature} - {type_name}"
                    if type_name and type_name != target.signature
                    else target.signature
                )
                identity = format_record_identity(target, plugin, include_signature_if_missing=False)
                return f"{prefix} {identity}"

    if gt in {2, 3}:
        value = struct.unpack_from("<i", label, 0)[0]
        prefix = "Block" if gt == 2 else "Sub-Block"
        return f"{prefix} {value}"

    if gt in {4, 5}:
        y, x = struct.unpack_from("<hh", label, 0)
        prefix = "Block" if gt == 4 else "Sub-Block"
        return f"{prefix} {x},{y}"

    return label.hex(" ")


def group_type_label(group: Group) -> str:
    if group.group_type == 0:
        return "GRUP - Top"
    name = GROUP_TYPE_NAMES.get(group.group_type, "Group")
    return f"GRUP - {name}"
