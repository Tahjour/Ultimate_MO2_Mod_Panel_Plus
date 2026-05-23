from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Union, Tuple

if TYPE_CHECKING:
    from esp_viewer.core.formid_resolver import FormIDResolver
    from esp_viewer.core.load_order import LoadOrderInfo


class ConflictStatus(Enum):
    NOT_DEFINED = "ctNotDefined"
    IDENTICAL_TO_MASTER = "ctIdenticalToMaster"
    ONLY_ONE = "ctOnlyOne"
    HIDDEN_BY_MOD_GROUP = "ctHiddenByModGroup"
    MASTER = "ctMaster"
    CONFLICT_BENIGN = "ctConflictBenign"
    OVERRIDE = "ctOverride"
    IDENTICAL_TO_MASTER_WINS_CONFLICT = "ctIdenticalToMasterWinsConflict"
    CONFLICT_LOSES = "ctConflictLoses"
    CONFLICT_CRITICAL = "ctConflictCritical"


@dataclass(frozen=True)
class RecordConflict:
    status: ConflictStatus
    field_statuses: Dict[Tuple[str, int], ConflictStatus]
    winning_plugin: Optional[str]
    chain_length: int
    is_deleted: bool
    is_injected: bool
    chain_plugins: Tuple[str, ...]
    chain_paths: Tuple[str, ...]


@dataclass(frozen=True)
class ConflictAnalysisResult:
    statuses: Dict[Tuple[str, int], ConflictStatus]
    details: Dict[Tuple[str, int], RecordConflict]
    load_order: List[str]


logger = logging.getLogger(__name__)


RECORD_FLAGS: Dict[int, str] = {
    0x00000001: "ESM",
    0x00000004: "Cannot Wait",
    0x00000020: "Deleted",
    0x00000040: "Has Distant LOD",
    0x00000080: "Localized (TES4) / Turn Off Fire (others)",
    0x00000100: "Inaccessible",
    0x00000200: "Casts Shadows",
    0x00000400: "Persistent / Quest Item",
    0x00000800: "Initially Disabled",
    0x00001000: "Ignored",
    0x00008000: "Visible When Distant",
    0x00020000: "Dangerous / Off Limits",
    0x00040000: "Compressed",
    0x00080000: "Cannot Wait",
    0x00800000: "Is Marker",
    0x02000000: "Obstacle / No AI Acquire",
    0x04000000: "NavMesh Gen - Filter",
    0x08000000: "NavMesh Gen - Bounding Box",
    0x40000000: "NavMesh Gen - Ground",
}


GROUP_TYPE_NAMES: Dict[int, str] = {
    0: "Top",
    1: "World Children",
    2: "Interior Cell Block",
    3: "Interior Cell Sub-Block",
    4: "Exterior Cell Block",
    5: "Exterior Cell Sub-Block",
    6: "Cell Children",
    7: "Topic Children",
    8: "Cell Persistent Children",
    9: "Cell Temporary Children",
    10: "Cell Visible Distant Children",
}


@dataclass
class Field:
    signature: str
    size: int
    raw: bytes

    def __repr__(self) -> str:
        return f"Field({self.signature}, {self.size} bytes)"


@dataclass
class Record:
    signature: str
    data_size: int
    flags: int
    form_id: int
    vci1: int
    form_version: Optional[int]
    vci2: Optional[int]
    fields: List[Field]
    is_compressed: bool
    editor_id: Optional[str]
    full_name: Optional[str]
    parse_error: Optional[str]
    raw_offset: int = 0
    _content_hash: Optional[str] = field(default=None, init=False, repr=False)

    def get_content_hash(self) -> str:
        """Возвращает хеш содержимого записи для быстрого сравнения."""
        if self._content_hash is None:
            hasher = hashlib.md5()
            # Хешируем основные метаданные, влияющие на структуру
            hasher.update(self.signature.encode('ascii'))
            hasher.update(self.flags.to_bytes(4, 'little'))
            # Хешируем все поля (сигнатура + данные)
            for f in self.fields:
                hasher.update(f.signature.encode('ascii'))
                hasher.update(f.raw)
            self._content_hash = hasher.hexdigest()
        return self._content_hash

    @property
    def flag_names(self) -> List[str]:
        names: List[str] = []
        for bit, name in RECORD_FLAGS.items():
            if self.flags & bit:
                names.append(name)
        return names


@dataclass
class Group:
    label_raw: bytes
    group_type: int
    group_size: int
    stamp: int
    unknown1: Optional[int]
    unknown2: Optional[int]
    children: List[Union[Group, Record]]
    raw_offset: int = 0


@dataclass
class LazyPluginIndex:
    path: str
    header_size: int
    record_offsets: Dict[Tuple[str, int], int]  # (sig, form_id) -> offset
    file_size: int
    localized: bool = False
    masters: List[str] = field(default_factory=list)


@dataclass
class PluginFile:
    path: str
    file_size: int
    header_size: int
    localized: bool
    strings: StringTables
    children: List[Union[Group, Record]]
    masters: List[str] = field(default_factory=list)
    load_order: Optional[LoadOrderInfo] = None
    formid_resolver: Optional[FormIDResolver] = None
    is_esl: bool = False
    record_map: Dict[Tuple[str, int], Record] = field(default_factory=dict)
    lazy_index: Optional[LazyPluginIndex] = None
