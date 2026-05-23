from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from esp_viewer.core.data_types import Group, Record


@dataclass
class ExportFilters:
    only_with_editor_id: bool = False
    only_with_full_name: bool = False
    exclude_deleted: bool = False
    exclude_ignored: bool = False
    only_compressed: Optional[bool] = None
    only_with_errors: Optional[bool] = None
    formid_min: Optional[int] = None
    formid_max: Optional[int] = None
    form_version_min: Optional[int] = None
    form_version_max: Optional[int] = None


@dataclass
class ExportConfig:
    scope: str
    custom_signatures: Set[str]
    data_types: Set[str]
    record_fields: List[str]
    group_fields: List[str]
    subrecord_fields: List[str]
    formats: Set[str]
    format_options: Dict[str, Dict[str, Any]]
    filters: ExportFilters
    output_dir: str
    base_filename: str
    source_description: str = ""
    selected_records: Optional[List[Record]] = None
    selected_groups: Optional[List[Group]] = None


@dataclass
class ExportedFile:
    path: str
    record_count: int
    size: int


@dataclass
class ExportResult:
    success: bool
    files: List[ExportedFile]
    total_records: int
    duration_seconds: float
    errors: List[str]
    clipboard_text: Optional[str] = None
