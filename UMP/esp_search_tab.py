from __future__ import annotations

import json
import logging
import os
import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import mobase
from PyQt6.QtCore import Qt, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
	QAbstractItemView,
	QCheckBox,
	QComboBox,
	QGroupBox,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QMessageBox,
	QPushButton,
	QProgressBar,
	QSizePolicy,
	QSplitter,
	QTreeWidget,
	QTreeWidgetItem,
	QVBoxLayout,
	QWidget,
)


logger = logging.getLogger(__name__)


LOCALIZED_SIGNATURES = {
    "FULL",
    "DESC",
    "SHRT",
    "TNAM",
    "ITXT",
    "NNAM",
    "CNAM",
    "SNAM",
    "ANAM",
    "RNAM",
    "QNAM",
}

RECORD_SIGNATURE_TYPES = {
    "TES4": "File Header",
    "GMST": "Game Setting",
    "KYWD": "Keyword",
    "LCRT": "Location Ref Type",
    "AACT": "Action",
    "TXST": "Texture Set",
    "GLOB": "Global",
    "CLAS": "Class",
    "FACT": "Faction",
    "HDPT": "Head Part",
    "EYES": "Eyes",
    "RACE": "Race",
    "SOUN": "Sound Marker",
    "ASPC": "Acoustic Space",
    "MGEF": "Magic Effect",
    "SCPT": "Script",
    "LTEX": "Land Texture",
    "ENCH": "Object Effect",
    "SPEL": "Spell",
    "SCRL": "Scroll",
    "ACTI": "Activator",
    "TACT": "Talking Activator",
    "ARMO": "Armor",
    "BOOK": "Book",
    "CONT": "Container",
    "DOOR": "Door",
    "INGR": "Ingredient",
    "LIGH": "Light",
    "MISC": "Misc Item",
    "APPA": "Apparatus",
    "STAT": "Static",
    "MSTT": "Moveable Static",
    "GRAS": "Grass",
    "TREE": "Tree",
    "FLOR": "Flora",
    "FURN": "Furniture",
    "WEAP": "Weapon",
    "AMMO": "Ammunition",
    "NPC_": "Non-Player Character",
    "LVLN": "Leveled NPC",
    "KEYM": "Key",
    "ALCH": "Ingestible",
    "IDLM": "Idle Marker",
    "COBJ": "Constructible Object",
    "PROJ": "Projectile",
    "HAZD": "Hazard",
    "SLGM": "Soul Gem",
    "LVLI": "Leveled Item",
    "WTHR": "Weather",
    "CLMT": "Climate",
    "SPGD": "Shader Particle Geometry",
    "RFCT": "Visual Effect",
    "REGN": "Region",
    "NAVI": "Navigation Mesh Info Map",
    "CELL": "Cell",
    "REFR": "Placed Object",
    "ACHR": "Placed NPC",
    "PMIS": "Placed Missile",
    "PGRE": "Placed Grenade",
    "PHZD": "Placed Hazard",
    "WRLD": "Worldspace",
    "LAND": "Landscape",
    "NAVM": "Navigation Mesh",
    "DIAL": "Dialog Topic",
    "INFO": "Dialog Info",
    "QUST": "Quest",
    "IDLE": "Idle Animation",
    "PACK": "Package",
    "CSTY": "Combat Style",
    "LSCR": "Load Screen",
    "LVSP": "Leveled Spell",
    "ANIO": "Animated Object",
    "WATR": "Water",
    "EFSH": "Effect Shader",
    "EXPL": "Explosion",
    "DEBR": "Debris",
    "IMGS": "Image Space",
    "IMAD": "Image Space Adapter",
    "FLST": "FormID List",
    "PERK": "Perk",
    "BPTD": "Body Part Data",
    "ADDN": "Addon Node",
    "AVIF": "Actor Value Info",
    "CAMS": "Camera Shot",
    "CPTH": "Camera Path",
    "VTYP": "Voice Type",
    "MATT": "Material Type",
    "IPCT": "Impact",
    "IPDS": "Impact Data Set",
    "ARMA": "Armor Addon",
    "ECZN": "Encounter Zone",
    "LCTN": "Location",
    "MESG": "Message",
    "DOBJ": "Default Object Manager",
    "LGTM": "Lighting Template",
    "MUSC": "Music Type",
    "FSTP": "Footstep",
    "FSTS": "Footstep Set",
    "SMBN": "Story Manager Branch Node",
    "SMQN": "Story Manager Quest Node",
    "SMEN": "Story Manager Event Node",
    "DLBR": "Dialog Branch",
    "MUST": "Music Track",
    "DLVW": "Dialog View",
    "WOOP": "Word of Power",
    "SHOU": "Shout",
    "EQUP": "Equip Type",
    "RELA": "Relationship",
    "SCEN": "Scene",
    "ASTP": "Association Type",
    "OTFT": "Outfit",
    "ARTO": "Art Object",
    "MATO": "Material Object",
    "MOVT": "Movement Type",
    "SNDR": "Sound Descriptor",
    "DUAL": "Dual Cast Data",
    "SNCT": "Sound Category",
    "SOPM": "Sound Output Model",
    "COLL": "Collision Layer",
    "CLFM": "Color",
    "REVB": "Reverb Parameters",
    "LENS": "Lens Flare",
    "VOLI": "Volumetric Lighting",
}

SUBRECORD_LABELS = {
    "EDID": "Editor ID",
    "FULL": "Name",
    "DESC": "Description",
    "MODL": "Model Filename",
    "MODT": "Model Texture Data",
    "MODS": "Model Alternate Textures",
    "OBND": "Object Bounds",
    "KWDA": "Keywords",
    "KSIZ": "Keyword Count",
    "VMAD": "Virtual Machine Adapter",
    "HEDR": "Header",
    "CNAM": "Author",
    "SNAM": "Description",
    "MAST": "Master File",
    "DATA": "Data",
    "ONAM": "Overridden Forms",
    "INTV": "Internal Version",
    "INCC": "Internal Cell Count",
    "DNAM": "Data",
    "ETYP": "Equipment Type",
    "BIDS": "Block Bash Impact Data Set",
    "BAMT": "Alternate Block Material",
    "YNAM": "Pick Up Sound",
    "ZNAM": "Put Down Sound",
    "EAMT": "Enchantment Amount",
    "EITM": "Object Effect",
    "ANAM": "Attenuation",
    "CRDT": "Critical Data",
    "VNAM": "Detection Sound Level",
    "INAM": "Impact Data Set",
    "WNAM": "First Person Model Object",
    "TNAM": "Texture",
    "NAM6": "Name",
    "NAM7": "Name",
    "NAM8": "Name",
    "NAM9": "Name",
    "SPIT": "Spell Data",
    "EFID": "Base Effect",
    "EFIT": "Effect Data",
    "CTDA": "Condition",
    "CIS1": "Condition Parameter 1",
    "CIS2": "Condition Parameter 2",
    "CITC": "Condition Item Count",
    "ACBS": "Configuration",
    "AIDT": "AI Data",
    "PKID": "Package",
    "SPLO": "Actor Effect",
    "PRKR": "Perk",
    "COCT": "Container Count",
    "CNTO": "Container Item",
    "RNAM": "Race",
    "QNAM": "Quest",
    "SNDD": "Sound Data",
    "MDOB": "Menu Display Object",
}

COMMON_FIELD_ORDER = [
    "EDID",
    "FULL",
    "DESC",
    "SHRT",
    "ITXT",
    "TNAM",
    "NNAM",
    "CNAM",
    "SNAM",
    "ANAM",
    "RNAM",
    "QNAM",
    "HEDR",
    "KWDA",
    "MAST",
    "ONAM",
    "VMAD",
    "DATA",
    "DNAM",
    "SNDD",
    "MDOB",
    "OBND",
    "SPIT",
    "EFID",
    "EFIT",
    "CTDA",
    "CIS1",
    "CIS2",
    "CITC",
    "ENAM",
    "INAM",
    "FNAM",
    "GNAM",
    "LNAM",
    "PNAM",
    "MNAM",
    "XNAM",
    "WNAM",
    "ZNAM",
    "YNAM",
    "BIDS",
    "BODT",
    "BOD2",
    "ETYP",
    "BAMT",
    "KSIZ",
]

FIELD_SIGNATURE_LABELS: List[Tuple[str, str]] = []
_seen_fields: set = set()
for _sig in COMMON_FIELD_ORDER:
    _label = SUBRECORD_LABELS.get(_sig, _sig)
    FIELD_SIGNATURE_LABELS.append((_sig, _label))
    _seen_fields.add(_sig)
for _sig in sorted(SUBRECORD_LABELS):
    if _sig in _seen_fields:
        continue
    FIELD_SIGNATURE_LABELS.append((_sig, SUBRECORD_LABELS[_sig]))


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class Field:
    signature: str
    size: int
    raw: bytes


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
    parse_error: Optional[str]


@dataclass
class StringTables:
    strings: Dict[int, str] = field(default_factory=dict)
    ilstrings: Dict[int, str] = field(default_factory=dict)
    dlstrings: Dict[int, str] = field(default_factory=dict)

    def resolve(self, string_id: int) -> Optional[str]:
        for table in (self.strings, self.ilstrings, self.dlstrings):
            text = table.get(string_id)
            if text is not None:
                return text
        return None


@dataclass
class PluginFile:
    path: str
    header_size: int
    localized: bool
    strings: StringTables


# ---------------------------------------------------------------------------
#  Binary reader
# ---------------------------------------------------------------------------

class ByteReader:
    __slots__ = ("data", "pos", "length")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.length = len(data)

    def can_read(self, size: int) -> bool:
        return self.pos + size <= self.length

    def read(self, size: int) -> bytes:
        if not self.can_read(size):
            raise ValueError(
                f"Unexpected end of data: need {size} bytes at offset {self.pos}, "
                f"but only {self.length - self.pos} available",
            )
        chunk = self.data[self.pos : self.pos + size]
        self.pos += size
        return chunk

    def peek(self, size: int) -> bytes:
        if not self.can_read(size):
            return b""
        return self.data[self.pos : self.pos + size]

    def read_u16(self) -> int:
        return self._read_struct("<H", 2)

    def read_u32(self) -> int:
        return self._read_struct("<I", 4)

    def _read_struct(self, fmt: str, size: int) -> int:
        if not self.can_read(size):
            raise ValueError(
                f"Cannot read {size} bytes at offset {self.pos}, "
                f"only {self.length - self.pos} remaining",
            )
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return value


# ---------------------------------------------------------------------------
#  Text helpers
# ---------------------------------------------------------------------------

def decode_text(raw: bytes) -> Optional[str]:
    if not raw:
        return None
    trimmed = raw.rstrip(b"\x00")
    if not trimmed:
        return ""
    for encoding in ("utf-8", "cp1252", "cp1251"):
        try:
            text = trimmed.decode(encoding)
            if all(ch.isprintable() or ch in ("\n", "\r", "\t") for ch in text):
                return text
        except (UnicodeDecodeError, ValueError):
            continue
    return None


def _read_cstring(data: bytes, start: int) -> bytes:
    end = data.find(b"\x00", start)
    if end == -1:
        return data[start:]
    return data[start:end]


# ---------------------------------------------------------------------------
#  String table loading
# ---------------------------------------------------------------------------

def read_string_table(path: str, has_length_prefix: bool) -> Dict[int, str]:
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        logger.warning("Cannot read string table %s: %s", path, exc)
        return {}

    if len(data) < 8:
        return {}

    count, data_size = struct.unpack_from("<II", data, 0)
    directory_start = 8
    data_start = directory_start + count * 8
    if data_start > len(data):
        return {}

    data_end = min(data_start + data_size, len(data))

    entries: Dict[int, str] = {}
    for i in range(count):
        entry_offset = directory_start + i * 8
        if entry_offset + 8 > len(data):
            break
        string_id, rel_offset = struct.unpack_from("<II", data, entry_offset)
        pos = data_start + rel_offset
        if pos >= data_end:
            continue
        try:
            if has_length_prefix:
                if pos + 4 > data_end:
                    continue
                length = struct.unpack_from("<I", data, pos)[0]
                pos += 4
                if pos + length > data_end:
                    continue
                raw = data[pos : pos + length].rstrip(b"\x00")
            else:
                raw = _read_cstring(data, pos)
            text = decode_text(raw)
            if text is not None:
                entries[string_id] = text
        except (struct.error, ValueError):
            continue

    return entries


def _find_string_file(
    base: str,
    folders: List[str],
    extension: str,
) -> Optional[str]:
    candidates: List[Tuple[str, str]] = []
    lower_ext = f".{extension.lower()}"
    lower_base = base.lower() + "_"
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        try:
            for name in os.listdir(folder):
                lower_name = name.lower()
                if lower_name.startswith(lower_base) and lower_name.endswith(
                    lower_ext,
                ):
                    lang = lower_name[len(lower_base) : -len(lower_ext)]
                    candidates.append((os.path.join(folder, name), lang))
        except OSError:
            continue
    if not candidates:
        return None
    for pref in ("english", "russian"):
        for path, lang in candidates:
            if lang == pref:
                return path
    return candidates[0][0]


def load_string_tables(
    plugin_path: str,
    extra_dirs: Optional[List[str]] = None,
) -> StringTables:
    base = os.path.splitext(os.path.basename(plugin_path))[0]
    plugin_dir = os.path.dirname(os.path.abspath(plugin_path))
    search_dirs = [
        os.path.join(plugin_dir, "Strings"),
        os.path.join(os.path.dirname(plugin_dir), "Strings"),
        plugin_dir,
    ]
    if extra_dirs:
        search_dirs.extend(extra_dirs)

    tables = StringTables()
    for ext, attr, has_prefix in [
        ("strings", "strings", False),
        ("ilstrings", "ilstrings", True),
        ("dlstrings", "dlstrings", True),
    ]:
        path = _find_string_file(base, search_dirs, ext)
        if path:
            setattr(tables, attr, read_string_table(path, has_prefix))
    return tables


# ---------------------------------------------------------------------------
#  Record parsing
# ---------------------------------------------------------------------------

def decompress_record(raw_data: bytes) -> Tuple[bytes, Optional[str]]:
    if len(raw_data) < 4:
        return raw_data, "Compressed record too short for size prefix"
    expected_size = int.from_bytes(raw_data[:4], "little", signed=False)
    try:
        decompressed = zlib.decompress(raw_data[4:])
    except zlib.error as exc:
        return raw_data, f"Decompression error: {exc}"
    if len(decompressed) != expected_size:
        return (
            decompressed,
            f"Decompressed size mismatch: expected {expected_size}, "
            f"got {len(decompressed)}",
        )
    return decompressed, None


def is_valid_signature(sig: bytes) -> bool:
    if len(sig) != 4:
        return False
    if sig == b"GRUP":
        return True
    return all(65 <= b <= 90 or 48 <= b <= 57 or b == 95 for b in sig)


def parse_subrecords(data: bytes) -> Tuple[List[Field], Optional[str]]:
    fields: List[Field] = []
    pos = 0
    error: Optional[str] = None
    pending_size: Optional[int] = None
    data_len = len(data)

    while pos < data_len:
        if pos + 6 > data_len:
            remaining = data_len - pos
            error = (
                f"Insufficient data for subrecord header "
                f"({remaining} bytes remaining)"
            )
            break

        signature = data[pos : pos + 4].decode("ascii", errors="replace")
        size = struct.unpack_from("<H", data, pos + 4)[0]
        pos += 6

        if signature == "XXXX":
            if size != 4 or pos + 4 > data_len:
                error = "Invalid XXXX subrecord"
                break
            pending_size = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            continue

        if pending_size is not None:
            size = pending_size
            pending_size = None

        if pos + size > data_len:
            error = (
                f"Subrecord {signature} at offset {pos - 6}: "
                f"declared size {size}, but only {data_len - pos} bytes available"
            )
            break

        raw = data[pos : pos + size]
        pos += size
        fields.append(Field(signature=signature, size=size, raw=raw))

    return fields, error


def parse_record(reader: ByteReader, header_size: int) -> Record:
    signature = reader.read(4).decode("ascii", errors="replace")
    data_size = reader.read_u32()
    flags = reader.read_u32()
    form_id = reader.read_u32()
    vci1 = reader.read_u32()

    form_version: Optional[int] = None
    vci2: Optional[int] = None
    if header_size == 24:
        form_version = reader.read_u16()
        vci2 = reader.read_u16()

    raw_data = reader.read(data_size)
    is_compressed = bool(flags & 0x00040000)
    parse_error: Optional[str] = None

    if is_compressed:
        raw_data, parse_error = decompress_record(raw_data)

    fields, fields_error = parse_subrecords(raw_data)
    if fields_error:
        parse_error = (
            f"{parse_error}; {fields_error}" if parse_error else fields_error
        )

    return Record(
        signature=signature,
        data_size=data_size,
        flags=flags,
        form_id=form_id,
        vci1=vci1,
        form_version=form_version,
        vci2=vci2,
        fields=fields,
        is_compressed=is_compressed,
        parse_error=parse_error,
    )


def detect_header_size(data: bytes) -> int:
    if len(data) < 24:
        return 24
    if data[:4] != b"TES4":
        return 24
    data_size = struct.unpack_from("<I", data, 4)[0]
    for candidate in (24, 20):
        next_pos = candidate + data_size
        if next_pos + 4 <= len(data) and is_valid_signature(
            data[next_pos : next_pos + 4],
        ):
            return candidate
    return 24


def detect_localized(data: bytes, header_size: int) -> bool:
    if len(data) < header_size or data[:4] != b"TES4":
        return False
    flags = struct.unpack_from("<I", data, 8)[0]
    return bool(flags & 0x00000080)


def iter_group_records(
    reader: ByteReader,
    header_size: int,
    depth: int,
) -> Iterable[Record]:
    if depth > 128:
        raise ValueError("Maximum group nesting depth exceeded")
    offset = reader.pos
    signature = reader.read(4)
    if signature != b"GRUP":
        raise ValueError(
            f"Expected GRUP at offset {offset}, got {signature!r}",
        )
    group_size = reader.read_u32()
    reader.read(4)
    reader.read_u32()
    reader.read_u32()
    if header_size == 24:
        reader.read_u16()
        reader.read_u16()
    children_size = group_size - header_size
    end_pos = reader.pos + max(children_size, 0)
    while reader.pos < end_pos:
        if not reader.can_read(4):
            break
        sig = reader.peek(4)
        if sig == b"GRUP":
            yield from iter_group_records(reader, header_size, depth + 1)
        elif is_valid_signature(sig):
            yield parse_record(reader, header_size)
        else:
            reader.pos = end_pos
            break
    if reader.pos != end_pos:
        reader.pos = end_pos


def iter_records(data: bytes, header_size: int) -> Iterable[Record]:
    reader = ByteReader(data)
    while reader.pos < reader.length:
        if not reader.can_read(4):
            break
        sig = reader.peek(4)
        if sig == b"GRUP":
            yield from iter_group_records(reader, header_size, 0)
        elif is_valid_signature(sig):
            yield parse_record(reader, header_size)
        else:
            break


# ---------------------------------------------------------------------------
#  Search helpers
# ---------------------------------------------------------------------------

def format_form_id(form_id: int) -> str:
    return f"{form_id:08X}"


def resolve_field_text(fld: Field, plugin: PluginFile) -> Optional[str]:
    text = decode_text(fld.raw)
    if text is not None:
        return text
    if (
        plugin.localized
        and fld.size == 4
        and fld.signature in LOCALIZED_SIGNATURES
    ):
        string_id = int.from_bytes(fld.raw, "little", signed=False)
        return plugin.strings.resolve(string_id)
    return None


def iter_field_matches(
    record: Record,
    plugin: PluginFile,
    search_lower: str,
    signatures: Optional[List[str]],
    include_form_id: bool,
) -> Iterable[Tuple[str, str]]:
    if include_form_id:
        form_text = format_form_id(record.form_id)
        if search_lower in form_text.casefold():
            yield "REF ID", form_text
    for fld in record.fields:
        if signatures is not None and fld.signature not in signatures:
            continue
        text = resolve_field_text(fld, plugin)
        if text is None:
            continue
        if search_lower in text.casefold():
            yield fld.signature, text


def iter_plugin_matches(
    plugin_path: str,
    search_lower: str,
    signatures: Optional[List[str]],
    include_form_id: bool,
    extra_string_dirs: Optional[List[str]] = None,
) -> Iterable[Tuple[str, str, str]]:
    try:
        with open(plugin_path, "rb") as handle:
            data = handle.read()
    except OSError:
        return

    header_size = detect_header_size(data)
    localized = detect_localized(data, header_size)
    strings = (
        load_string_tables(plugin_path, extra_string_dirs)
        if localized
        else StringTables()
    )

    plugin = PluginFile(
        path=plugin_path,
        header_size=header_size,
        localized=localized,
        strings=strings,
    )

    for record in iter_records(data, header_size):
        for sig, value in iter_field_matches(
            record,
            plugin,
            search_lower,
            signatures,
            include_form_id,
        ):
            record_label = (
                f"{record.signature} [{format_form_id(record.form_id)}]"
            )
            yield record_label, sig, value


# ---------------------------------------------------------------------------
#  Background worker
# ---------------------------------------------------------------------------

class EspFieldSearchWorker(QThread):
    MAX_RESULTS = 10000

    progress = pyqtSignal(int, int)
    result_found = pyqtSignal(str, str, str, str, str)
    finished_search = pyqtSignal(int)
    limit_reached = pyqtSignal()

    def __init__(
        self,
        organizer: mobase.IOrganizer,
        search_text: str,
        signatures: Optional[List[str]],
        include_form_id: bool,
        active_only: bool,
        extra_string_dirs: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._organizer = organizer
        self._search_text = search_text
        self._signatures = signatures
        self._include_form_id = include_form_id
        self._active_only = active_only
        self._extra_string_dirs = extra_string_dirs or []
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        results_count = 0
        mod_list = self._organizer.modList()
        all_mods = mod_list.allMods()
        total_mods = len(all_mods)
        search_lower = self._search_text.casefold()

        for i, mod_name in enumerate(all_mods):
            if self._cancelled:
                break
            self.progress.emit(i + 1, total_mods)

            state = mod_list.state(mod_name)
            if not (state & mobase.ModState.EXISTS):
                continue
            if self._active_only and not (state & mobase.ModState.ACTIVE):
                continue

            mod_info = mod_list.getMod(mod_name)
            if not mod_info:
                continue
            mod_path = mod_info.absolutePath()
            if not mod_path or not os.path.exists(mod_path):
                continue

            try:
                for root, _, files in os.walk(mod_path):
                    if self._cancelled:
                        break
                    for file_name in files:
                        if self._cancelled:
                            break
                        ext = os.path.splitext(file_name)[1].lower()
                        if ext not in (".esp", ".esm", ".esl"):
                            continue
                        plugin_path = os.path.join(root, file_name)
                        for record_label, field_sig, value in iter_plugin_matches(
                            plugin_path,
                            search_lower,
                            self._signatures,
                            self._include_form_id,
                            self._extra_string_dirs,
                        ):
                            if self._cancelled:
                                break
                            self.result_found.emit(
                                mod_name,
                                plugin_path,
                                record_label,
                                field_sig,
                                value,
                            )
                            results_count += 1
                            if results_count >= self.MAX_RESULTS:
                                self.limit_reached.emit()
                                self._cancelled = True
                                break
            except Exception:
                logger.exception("Error processing mod %s", mod_name)
                continue

        self.finished_search.emit(results_count)


# ---------------------------------------------------------------------------
#  UI tab
# ---------------------------------------------------------------------------

class EspFieldSearchTab(QWidget):
    SETTINGS_KEY = "FullModSearch"
    MAX_RECENT_ITEMS = 10
    FLUSH_INTERVAL_MS = 200
    search_status = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget,
        organizer: mobase.IOrganizer,
        mods_view,
    ) -> None:
        super().__init__(parent)
        self._organizer = organizer
        self._mods_view = mods_view
        self._mod_list = organizer.modList()

        self._search_worker: Optional[EspFieldSearchWorker] = None
        self._mod_tree_items: Dict[str, QTreeWidgetItem] = {}
        self._total_hits = 0
        self._limit_was_reached = False

        self._pending_results: List[Tuple[str, str, str, str, str]] = []
        self._pending_recent_entry: Optional[Dict[str, str]] = None
        self._first_result_mod: Optional[str] = None

        self._recent_searches: List[Dict[str, str]] = []
        self._field_options: Dict[str, Tuple[Optional[List[str]], bool]] = {}

        self.settings = QSettings("ModOrganizer2", "FullModSearchPlugin")

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_INTERVAL_MS)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_pending_results)

        self._setup_ui()
        self._connect_signals()
        self._load_state()

    # ---- UI construction ---------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # --- search options ---
        search_group = QGroupBox("Search Options", self)
        search_group.setFlat(True)
        search_layout = QVBoxLayout(search_group)
        search_layout.setContentsMargins(4, 2, 4, 2)

        field_row = QHBoxLayout()
        field_row.addWidget(QLabel("Field:"))

        self.field_combo = QComboBox(self)
        self._populate_field_options()
        field_row.addWidget(self.field_combo)

        field_row.addWidget(QLabel("Value:"))

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText(
            "Enter text to search (partial matches allowed)",
        )
        self.search_input.setClearButtonEnabled(True)
        field_row.addWidget(self.search_input)

        self.search_btn = QPushButton("Search", self)
        field_row.addWidget(self.search_btn)

        field_row.addStretch()
        search_layout.addLayout(field_row)

        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_btn)

        self.clear_btn = QPushButton("Clear Results", self)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()

        self.active_mods_only_cb = QCheckBox("Active Mods Only", self)
        btn_layout.addWidget(self.active_mods_only_cb)
        search_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        search_layout.addWidget(self.progress_bar)

        layout.addWidget(search_group)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- results ---
        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.results_tree = QTreeWidget(self)
        self.results_tree.setHeaderLabels(["Mod / Record", "Field / Value"])
        self.results_tree.setColumnWidth(0, 450)
        self.results_tree.setAlternatingRowColors(True)
        self.results_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.results_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._set_results_tree_height(20)
        results_layout.addWidget(self.results_tree)

        info_layout = QHBoxLayout()
        self.results_label = QLabel("No results", self)
        info_layout.addWidget(self.results_label)
        info_layout.addStretch()
        self.goto_mod_btn = QPushButton("Go to Mod", self)
        self.goto_mod_btn.setEnabled(False)
        info_layout.addWidget(self.goto_mod_btn)
        results_layout.addLayout(info_layout)

        splitter.addWidget(results_group)

        # --- recent searches ---
        recent_group = QGroupBox("Recent Searches", self)
        recent_group.setFlat(True)
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(4, 2, 4, 2)

        self.recent_list = QTreeWidget(self)
        self.recent_list.setHeaderLabels(["Field", "Value"])
        self.recent_list.setColumnWidth(0, 200)
        self.recent_list.setRootIsDecorated(False)
        self.recent_list.setAlternatingRowColors(True)
        recent_layout.addWidget(self.recent_list)

        clear_recent_btn = QPushButton("Clear History", self)
        clear_recent_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_recent_btn)

        splitter.addWidget(recent_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _set_results_tree_height(self, rows: int) -> None:
        row_height = self.results_tree.sizeHintForRow(0)
        if row_height <= 0:
            row_height = self.results_tree.fontMetrics().height() + 6
        header_height = self.results_tree.header().height()
        frame = self.results_tree.frameWidth() * 2
        height = header_height + row_height * rows + frame
        self.results_tree.setMinimumHeight(height)

    # ---- signals -----------------------------------------------------------

    def _connect_signals(self) -> None:
        self.search_btn.clicked.connect(self._start_search)
        self.cancel_btn.clicked.connect(self._cancel_search)
        self.clear_btn.clicked.connect(self._clear_results)
        self.search_input.returnPressed.connect(self._start_search)
        self.results_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_tree.itemClicked.connect(self._on_result_clicked)
        self.goto_mod_btn.clicked.connect(self._goto_selected_mod)
        self.recent_list.itemDoubleClicked.connect(self._on_recent_clicked)
        self.recent_list.itemClicked.connect(self._on_recent_clicked)
        self.field_combo.currentIndexChanged.connect(self._save_state)
        self.active_mods_only_cb.stateChanged.connect(self._save_state)

    # ---- persistence -------------------------------------------------------

    def _load_state(self) -> None:
        self._recent_searches = self._load_recent()
        self._update_recent_list()

        field_index = self.settings.value(
            f"{self.SETTINGS_KEY}/EspFieldIndex",
            0,
            type=int,
        )
        if 0 <= field_index < self.field_combo.count():
            self.field_combo.setCurrentIndex(field_index)
        self.active_mods_only_cb.setChecked(
            self.settings.value(
                f"{self.SETTINGS_KEY}/EspFieldActiveOnly",
                False,
                type=bool,
            ),
        )

    def _load_recent(self) -> List[Dict[str, str]]:
        raw = self.settings.value(
            f"{self.SETTINGS_KEY}/RecentEspFieldSearchesV2",
            "",
            type=str,
        )
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
            except (json.JSONDecodeError, TypeError):
                pass

        old_entries = self.settings.value(
            f"{self.SETTINGS_KEY}/RecentEspFieldSearches",
            [],
            type=list,
        )
        if old_entries:
            migrated: List[Dict[str, str]] = []
            for entry in old_entries:
                if not isinstance(entry, str):
                    continue
                parts = entry.split("|", 2)
                migrated.append(
                    {
                        "field": parts[0] if parts else "",
                        "value": parts[1] if len(parts) > 1 else "",
                        "mod": parts[2] if len(parts) > 2 else "",
                    },
                )
            if migrated:
                self._recent_searches = migrated
                self._save_recent()
                return migrated

        return []

    def _save_state(self) -> None:
        self.settings.setValue(
            f"{self.SETTINGS_KEY}/EspFieldIndex",
            self.field_combo.currentIndex(),
        )
        self.settings.setValue(
            f"{self.SETTINGS_KEY}/EspFieldActiveOnly",
            self.active_mods_only_cb.isChecked(),
        )
        self.settings.sync()

    def _save_recent(self) -> None:
        self.settings.setValue(
            f"{self.SETTINGS_KEY}/RecentEspFieldSearchesV2",
            json.dumps(self._recent_searches, ensure_ascii=False),
        )
        self.settings.sync()

    # ---- field options -----------------------------------------------------

    def _populate_field_options(self) -> None:
        self._field_options = {
            "All Fields": (None, False),
            "REF ID (FormID)": ([], True),
        }
        for signature, label in FIELD_SIGNATURE_LABELS:
            display = f"{signature} ({label})" if label else signature
            self._field_options[display] = ([signature], False)
        for disp in self._field_options:
            self.field_combo.addItem(disp)

    def _selected_signatures(self) -> Tuple[Optional[List[str]], bool, str]:
        field_label = self.field_combo.currentText()
        signatures, include_form_id = self._field_options.get(
            field_label,
            (None, False),
        )
        return signatures, include_form_id, field_label

    # ---- recent searches ---------------------------------------------------

    def _update_recent_list(self) -> None:
        self.recent_list.clear()
        for entry in self._recent_searches:
            field_label = entry.get("field", "")
            value = entry.get("value", "")
            mod_name = entry.get("mod", "")
            item = QTreeWidgetItem([field_label, value])
            if mod_name:
                item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {"mod": mod_name},
                )
            self.recent_list.addTopLevelItem(item)

    def _add_to_recent(
        self,
        field_label: str,
        search_text: str,
    ) -> Dict[str, str]:
        entry: Dict[str, str] = {
            "field": field_label,
            "value": search_text,
            "mod": "",
        }
        self._recent_searches = [
            e
            for e in self._recent_searches
            if not (
                e.get("field") == field_label and e.get("value") == search_text
            )
        ]
        self._recent_searches.insert(0, entry)
        self._recent_searches = self._recent_searches[: self.MAX_RECENT_ITEMS]
        self._save_recent()
        self._update_recent_list()
        return entry

    def _set_recent_mod(
        self,
        entry: Optional[Dict[str, str]],
        mod_name: str,
    ) -> None:
        if not entry or not mod_name:
            return
        if entry.get("mod") == mod_name:
            return
        entry["mod"] = mod_name
        self._save_recent()
        self._update_recent_list()

    def _clear_recent(self) -> None:
        self._recent_searches = []
        self._save_recent()
        self._update_recent_list()
        self.search_status.emit("Recent searches cleared")

    # ---- extra string dirs -------------------------------------------------

    def _get_extra_string_dirs(self) -> List[str]:
        dirs: List[str] = []
        try:
            game = self._organizer.managedGame()
            if game:
                data_dir = game.dataDirectory().absolutePath()
                strings_dir = os.path.join(data_dir, "Strings")
                if os.path.isdir(strings_dir):
                    dirs.append(strings_dir)
        except Exception:
            logger.debug(
                "Could not resolve game data directory for string tables",
            )
        return dirs

    # ---- search control ----------------------------------------------------

    def _start_search(self) -> None:
        search_text = self.search_input.text().strip()
        if not search_text:
            QMessageBox.warning(self, "Search", "Please enter text to search.")
            return
        if len(search_text) < 2:
            QMessageBox.warning(
                self,
                "Search",
                "Please enter at least 2 characters.",
            )
            return

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait()

        self._clear_results()

        signatures, include_form_id, field_label = self._selected_signatures()
        self._pending_recent_entry = self._add_to_recent(
            field_label,
            search_text,
        )
        self._first_result_mod = None
        self._limit_was_reached = False
        self._save_state()

        self.search_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.search_status.emit("Searching...")

        extra_dirs = self._get_extra_string_dirs()

        self._search_worker = EspFieldSearchWorker(
            self._organizer,
            search_text,
            signatures,
            include_form_id,
            self.active_mods_only_cb.isChecked(),
            extra_dirs,
        )
        self._search_worker.progress.connect(self._on_search_progress)
        self._search_worker.result_found.connect(self._on_result_found)
        self._search_worker.finished_search.connect(self._on_search_finished)
        self._search_worker.limit_reached.connect(self._on_limit_reached)
        self._search_worker.start()

    def _cancel_search(self) -> None:
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self.search_status.emit("Search cancelled")

    def _clear_results(self) -> None:
        self._flush_timer.stop()
        self._pending_results.clear()
        self.results_tree.clear()
        self._mod_tree_items = {}
        self._total_hits = 0
        self.results_label.setText("No results")
        self.goto_mod_btn.setEnabled(False)

    # ---- worker callbacks --------------------------------------------------

    def _on_search_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.search_status.emit(f"Searching... ({current}/{total} mods)")

    def _on_limit_reached(self) -> None:
        self._limit_was_reached = True

    def _on_result_found(
        self,
        mod_name: str,
        plugin_path: str,
        record_label: str,
        field_sig: str,
        value: str,
    ) -> None:
        if self._total_hits >= EspFieldSearchWorker.MAX_RESULTS:
            return

        self._pending_results.append(
            (mod_name, plugin_path, record_label, field_sig, value),
        )
        self._total_hits += 1

        if self._first_result_mod is None:
            self._first_result_mod = mod_name
            self._set_recent_mod(self._pending_recent_entry, mod_name)

        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_pending_results(self) -> None:
        if not self._pending_results:
            return
        self.results_tree.setUpdatesEnabled(False)
        try:
            for entry in self._pending_results:
                self._add_result_to_tree(*entry)
        finally:
            self.results_tree.setUpdatesEnabled(True)
            self._pending_results.clear()
        mod_count = len(self._mod_tree_items)
        self.results_label.setText(
            f"{self._total_hits} hits in {mod_count} mods",
        )

    def _add_result_to_tree(
        self,
        mod_name: str,
        plugin_path: str,
        record_label: str,
        field_sig: str,
        value: str,
    ) -> None:
        display_value = value[:200] + "..." if len(value) > 200 else value
        plugin_name = os.path.basename(plugin_path)

        if mod_name not in self._mod_tree_items:
            mod_item = QTreeWidgetItem([mod_name, ""])
            font = QFont()
            font.setBold(True)
            mod_item.setFont(0, font)
            mod_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {"type": "mod", "name": mod_name},
            )
            self.results_tree.addTopLevelItem(mod_item)
            self._mod_tree_items[mod_name] = mod_item

        mod_item = self._mod_tree_items[mod_name]

        rec_sig = record_label.split()[0] if record_label else ""
        rec_type = RECORD_SIGNATURE_TYPES.get(rec_sig, "")
        label = f"{plugin_name} → {record_label}"
        if rec_type:
            label += f" ({rec_type})"

        hit_item = QTreeWidgetItem([label, f"{field_sig}: {display_value}"])
        hit_item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {"type": "mod", "name": mod_name},
        )
        mod_item.addChild(hit_item)

    def _on_search_finished(self, total_results: int) -> None:
        self._flush_timer.stop()
        self._flush_pending_results()

        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self._pending_recent_entry = None
        self._first_result_mod = None

        mod_count = len(self._mod_tree_items)
        if self._limit_was_reached:
            status = (
                f"Search complete: showing first "
                f"{EspFieldSearchWorker.MAX_RESULTS} results "
                f"in {mod_count} mods (limit reached)"
            )
            self.results_label.setText(
                f"{total_results} hits in {mod_count} mods "
                f"(limit of {EspFieldSearchWorker.MAX_RESULTS} reached)",
            )
        else:
            status = (
                f"Search complete: {total_results} hits in {mod_count} mods"
            )

        self.search_status.emit(status)

        if mod_count <= 20:
            self.results_tree.expandAll()

    # ---- result navigation -------------------------------------------------

    def _on_selection_changed(self) -> None:
        items = self.results_tree.selectedItems()
        self.goto_mod_btn.setEnabled(bool(items))

    def _on_result_clicked(self, item: QTreeWidgetItem) -> None:
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        mod_name = data.get("name")
        if mod_name:
            self._goto_mod(mod_name)

    def _goto_selected_mod(self) -> None:
        items = self.results_tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        mod_name = data.get("name")
        if mod_name:
            self._goto_mod(mod_name)

    def _goto_mod(self, mod_name: str) -> None:
        if not self._mods_view or not self._mods_view.model():
            self.search_status.emit("Error: Mods view not available")
            return
        display_name = self._mod_list.displayName(mod_name)
        model = self._mods_view.model()
        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            display_name,
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )
        if not matches:
            matches = model.match(
                model.index(0, 0),
                Qt.ItemDataRole.DisplayRole,
                display_name,
                1,
                Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive,
            )
        if matches:
            index = matches[0]
            parent = index.parent()
            if parent.isValid():
                self._mods_view.expand(parent)
            self._mods_view.scrollTo(
                index,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )
            self._mods_view.setCurrentIndex(index)
            self._mods_view.setFocus()
            self.search_status.emit(f"Selected: {display_name}")
        else:
            self.search_status.emit(f"Could not find mod: {display_name}")

    # ---- recent click handler ----------------------------------------------

    def _on_recent_clicked(self, item: QTreeWidgetItem) -> None:
        if not item:
            return
        field_label = item.text(0)
        value = item.text(1)
        mod_data = item.data(0, Qt.ItemDataRole.UserRole)
        mod_name = ""
        if isinstance(mod_data, dict):
            mod_name = mod_data.get("mod", "")

        index = self.field_combo.findText(field_label)
        if index != -1:
            self.field_combo.setCurrentIndex(index)
            self.custom_field_input.setText("")
        elif field_label:
            self.field_combo.setCurrentIndex(0)
            self.custom_field_input.setText(field_label)

        self.search_input.setText(value)
        self.search_input.setFocus()
        self.search_input.selectAll()

        if mod_name:
            self._goto_mod(mod_name)

    # ---- public API --------------------------------------------------------

    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def cleanup(self) -> None:
        """Stop running search and release resources.

        Must be called before the parent widget is destroyed.
        """
        self._flush_timer.stop()
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait(5000)


__all__ = ["EspFieldSearchTab"]
