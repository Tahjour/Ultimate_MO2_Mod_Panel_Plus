from typing import Callable, Iterable, List, Optional

from esp_viewer.core.data_types import Record

from .base import ExportFilters


DELETED_FLAG = 0x00000020
IGNORED_FLAG = 0x00001000


def filter_records(
    records: Iterable[Record],
    filters: ExportFilters,
    resolve_full_name: Optional[Callable[[Record], Optional[str]]] = None,
) -> List[Record]:
    result: List[Record] = []
    for record in records:
        if not _record_passes_filters(record, filters, resolve_full_name):
            continue
        result.append(record)
    return result


def _record_passes_filters(
    record: Record,
    filters: ExportFilters,
    resolve_full_name: Optional[Callable[[Record], Optional[str]]],
) -> bool:
    if filters.only_with_editor_id and not record.editor_id:
        return False
    if filters.only_with_full_name:
        full_name = record.full_name
        if resolve_full_name is not None:
            full_name = resolve_full_name(record)
        if not full_name:
            return False
    if filters.exclude_deleted and (record.flags & DELETED_FLAG):
        return False
    if filters.exclude_ignored and (record.flags & IGNORED_FLAG):
        return False
    if filters.only_compressed is True and not record.is_compressed:
        return False
    if filters.only_compressed is False and record.is_compressed:
        return False
    if filters.only_with_errors is True and not record.parse_error:
        return False
    if filters.only_with_errors is False and record.parse_error:
        return False
    if filters.formid_min is not None and record.form_id < filters.formid_min:
        return False
    if filters.formid_max is not None and record.form_id > filters.formid_max:
        return False
    if filters.form_version_min is not None and (
        record.form_version is None or record.form_version < filters.form_version_min
    ):
        return False
    if filters.form_version_max is not None and (
        record.form_version is None or record.form_version > filters.form_version_max
    ):
        return False
    return True
