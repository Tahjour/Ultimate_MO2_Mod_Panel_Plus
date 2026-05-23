from typing import Callable, Iterable, List, Optional, Set, Tuple

from .data_types import Group, PluginFile, Record
from .record_formatter import StructuredSubrecordParser


def iter_records(nodes: Iterable[object]) -> Iterable[Record]:
    for node in nodes:
        if isinstance(node, Record):
            yield node
        elif isinstance(node, Group):
            yield from iter_records(node.children)


def iter_groups(nodes: Iterable[object]) -> Iterable[Group]:
    for node in nodes:
        if isinstance(node, Group):
            yield node
            yield from iter_groups(node.children)


def parse_form_id(query: str) -> Optional[int]:
    value = query.strip().lower().replace("0x", "")
    if not value:
        return None
    if not all(c in "0123456789abcdef" for c in value):
        return None
    if len(value) > 8:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def normalize_fields(fields: Optional[Iterable[str]]) -> Set[str]:
    if not fields:
        return {"signature", "editor_id", "full_name", "form_id", "values"}
    normalized = {field for field in fields if field}
    if "all" in normalized:
        return {"signature", "editor_id", "full_name", "form_id", "values"}
    return normalized


def record_matches(
    plugin: PluginFile,
    record: Record,
    query: str,
    fields: Optional[Iterable[str]],
    resolve_full_name: Callable[[Record], Optional[str]],
) -> bool:
    text = query.strip().lower()
    if not text:
        return False
    enabled = normalize_fields(fields)
    form_id = parse_form_id(text) if "form_id" in enabled else None

    if "signature" in enabled and text in record.signature.lower():
        return True
    if "editor_id" in enabled and record.editor_id and text in record.editor_id.lower():
        return True
    if "full_name" in enabled:
        full = resolve_full_name(record)
        if full and text in full.lower():
            return True
    if "form_id" in enabled:
        if form_id is not None and record.form_id == form_id:
            return True
        if text in f"{record.form_id:08X}".lower():
            return True
    if "values" in enabled:
        try:
            parser = StructuredSubrecordParser(record, plugin)
            stack = list(parser.iter_nodes())
            while stack:
                node = stack.pop()
                if node.name and text in node.name.lower():
                    return True
                if node.value and text in node.value.lower():
                    return True
                if node.children:
                    stack.extend(node.children)
        except Exception:
            return False
    return False


def search_records(
    plugin: PluginFile,
    query: str,
    fields: Optional[Iterable[str]],
    resolve_full_name: Callable[[Record], Optional[str]],
    limit: Optional[int] = None,
) -> List[Record]:
    results: List[Record] = []
    for record in iter_records(plugin.children):
        if record_matches(plugin, record, query, fields, resolve_full_name):
            results.append(record)
            if limit is not None and len(results) >= limit:
                break
    return results


def matching_record_keys(
    plugin: PluginFile,
    query: str,
    fields: Optional[Iterable[str]],
    resolve_full_name: Callable[[Record], Optional[str]],
) -> Set[Tuple[str, int]]:
    matches: Set[Tuple[str, int]] = set()
    for record in iter_records(plugin.children):
        if record_matches(plugin, record, query, fields, resolve_full_name):
            matches.add((record.signature, record.form_id))
    return matches
