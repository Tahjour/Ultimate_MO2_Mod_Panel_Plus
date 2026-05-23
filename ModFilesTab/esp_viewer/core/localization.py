import configparser
import logging
import os
import struct
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from esp_viewer.core.data_types import Field, PluginFile


LOCALIZED_SIGNATURES = frozenset({
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
    "EPF2",
})


@dataclass
class StringTables:
    strings: Dict[int, str] = field(default_factory=dict)
    ilstrings: Dict[int, str] = field(default_factory=dict)
    dlstrings: Dict[int, str] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        return len(self.strings) + len(self.ilstrings) + len(self.dlstrings)

    def resolve(self, string_id: int) -> Optional[str]:
        for table in (self.strings, self.ilstrings, self.dlstrings):
            text = table.get(string_id)
            if text is not None:
                return text
        return None


def decode_text(raw: bytes, preferred_encoding: Optional[str] = None) -> Optional[str]:
    if not raw:
        return None
    # Try length-prefixed LString (uint16 length + UTF-16LE) as used by TES5 wbLString
    # Skip for 4-byte data (likely string IDs in localized plugins)
    if len(raw) > 4 and len(raw) >= 2 and len(raw) % 2 == 0:
        length = struct.unpack_from("<H", raw, 0)[0]
        if 2 + length * 2 <= len(raw) and 0 < length < 4096:
            try:
                text = raw[2 : 2 + length * 2].decode("utf-16-le", errors="strict")
                if text and all(ch.isprintable() or ch in ("\n", "\r", "\t") for ch in text):
                    return text
            except (UnicodeDecodeError, ValueError):
                pass
    trimmed = raw.rstrip(b"\x00")
    if not trimmed:
        return ""
    encodings: List[str] = []
    if preferred_encoding:
        encodings.append(preferred_encoding)
    encodings.extend(["utf-8", "utf-16-le", "cp1252", "cp1251"])
    for encoding in encodings:
        try:
            text = trimmed.decode(encoding)
            if text and all(ch.isprintable() or ch in ("\n", "\r", "\t") for ch in text):
                return text
        except (UnicodeDecodeError, ValueError):
            continue
    return None


def resolve_string(field: "Field", plugin: Optional["PluginFile"]) -> str:
    if (
        plugin is not None
        and plugin.localized
        and field.size == 4
        and field.signature in LOCALIZED_SIGNATURES
    ):
        string_id = int.from_bytes(field.raw, "little", signed=False)
        if string_id == 0:
            return ""
        resolved = plugin.strings.resolve(string_id)
        if resolved is not None:
            return resolved
        return f"<<Missing string 0x{string_id:08X}>>"
    text = decode_text(field.raw)
    if text is None:
        return ""
    return text


def read_cstring(data: bytes, start: int) -> bytes:
    end = data.find(b"\x00", start)
    if end == -1:
        return data[start:]
    return data[start:end]


def read_string_table(path: str, has_length_prefix: bool) -> Dict[int, str]:
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        logger.warning(f"Cannot read string table {path}: {exc}")
        return {}

    if len(data) < 8:
        return {}

    count, data_size = struct.unpack_from("<II", data, 0)
    directory_start = 8
    directory_size = count * 8
    data_start = directory_start + directory_size

    if data_start > len(data):
        logger.warning(f"String table {path}: directory exceeds file size")
        return {}

    data_end = data_start + data_size
    if data_end > len(data):
        data_end = len(data)

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
                raw = read_cstring(data, pos)

            text = decode_text(raw)
            if text is not None:
                entries[string_id] = text
        except (struct.error, ValueError) as exc:
            logger.debug(f"Error reading string {string_id} from {path}: {exc}")
            continue

    logger.info(f"Loaded {len(entries)} strings from {path}")
    return entries


def _normalize_language(value: str) -> str:
    normalized = value.strip().lower()
    if "-" in normalized:
        normalized = normalized.split("-", 1)[0]
    if "_" in normalized:
        normalized = normalized.split("_", 1)[0]
    aliases = {
        "en": "english",
        "eng": "english",
        "ru": "russian",
        "rus": "russian",
    }
    return aliases.get(normalized, normalized)


def _read_ini_language(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return None
    value = ""
    if parser.has_option("General", "sLanguage"):
        value = parser.get("General", "sLanguage", fallback="")
    if not value and parser.has_option("Controls", "iLanguage"):
        try:
            code = parser.getint("Controls", "iLanguage")
        except (ValueError, configparser.Error):
            code = 0
        value = {
            1: "german",
            2: "french",
            3: "spanish",
            4: "italian",
        }.get(code, "english")
    value = value.strip()
    if not value:
        return None
    return _normalize_language(value)


def _read_cmd_language(argv: Optional[List[str]] = None) -> Optional[str]:
    args = argv if argv is not None else sys.argv[1:]
    expect_value = False
    for arg in args:
        if expect_value:
            expect_value = False
            if arg:
                return _normalize_language(arg)
            continue
        if arg in {"-l", "--language"}:
            expect_value = True
            continue
        if arg.startswith("-l:"):
            value = arg[3:]
            if value:
                return _normalize_language(value)
            continue
        if arg.startswith("-l="):
            value = arg[3:]
            if value:
                return _normalize_language(value)
            continue
        if arg.startswith("--language="):
            value = arg.split("=", 1)[1]
            if value:
                return _normalize_language(value)
    return None


def _detect_language() -> Optional[str]:
    cmd_lang = _read_cmd_language()
    if cmd_lang:
        return cmd_lang
    env_lang = (
        os.environ.get("ESP_VIEWER_LANGUAGE")
        or os.environ.get("ESP_VIEWER_LANG")
        or os.environ.get("SKYRIM_LANGUAGE")
        or os.environ.get("SKYRIM_LANG")
    )
    if env_lang:
        return _normalize_language(env_lang)
    env_ini = os.environ.get("SKYRIM_INI")
    if env_ini:
        detected = _read_ini_language(env_ini)
        if detected:
            return detected

    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents", "My Games")
    candidates = [
        "Skyrim Special Edition",
        "Skyrim",
        "Skyrim VR",
        "Enderal Special Edition",
        "Enderal",
    ]
    for folder in candidates:
        base = os.path.join(docs, folder)
        custom = _read_ini_language(os.path.join(base, "SkyrimCustom.ini"))
        prefs = _read_ini_language(os.path.join(base, "SkyrimPrefs.ini"))
        primary = _read_ini_language(os.path.join(base, "Skyrim.ini"))
        if custom:
            return custom
        if prefs:
            return prefs
        if primary:
            return primary
    return None


def find_string_file(
    base: str,
    folders: List[str],
    extension: str,
    language: Optional[str] = None,
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
                if lower_name.startswith(lower_base) and lower_name.endswith(lower_ext):
                    lang = lower_name[len(lower_base) : -len(lower_ext)]
                    candidates.append((os.path.join(folder, name), lang))
        except OSError:
            continue

    if not candidates:
        return None

    preferred_languages: List[str] = []
    if language:
        preferred_languages.append(_normalize_language(language))
    preferred_languages.extend(["english", "russian"])
    for pref in preferred_languages:
        for path, lang in candidates:
            if lang == pref:
                return path

    return candidates[0][0]


def _collect_string_dirs(plugin_path: str) -> List[str]:
    extra_dirs: List[str] = []
    env_vars = (
        "SKYRIM_DATA_DIR",
        "SKYRIM_SE_DATA_DIR",
        "SKYRIM_DATA",
        "SKYRIMSE_DATA_DIR",
    )
    for key in env_vars:
        value = os.environ.get(key)
        if not value:
            continue
        if value.lower().endswith("strings") and os.path.isdir(value):
            extra_dirs.append(value)
            continue
        candidate = os.path.join(value, "Strings")
        if os.path.isdir(candidate):
            extra_dirs.append(candidate)

    plugin_dir = os.path.dirname(os.path.abspath(plugin_path))
    current = plugin_dir
    while True:
        parent = os.path.dirname(current)
        if parent == current:
            break
        if os.path.basename(current).lower() in {"mo2", "mo3"}:
            base_parent = parent
            candidate = os.path.join(base_parent, "Data", "Strings")
            if os.path.isdir(candidate):
                extra_dirs.append(candidate)
            try:
                for name in os.listdir(base_parent):
                    if not name.lower().startswith("skyrim"):
                        continue
                    candidate = os.path.join(base_parent, name, "Data", "Strings")
                    if os.path.isdir(candidate):
                        extra_dirs.append(candidate)
            except OSError:
                pass
            break
        current = parent

    return extra_dirs


def load_string_tables(plugin_path: str) -> StringTables:
    base = os.path.splitext(os.path.basename(plugin_path))[0]
    plugin_dir = os.path.dirname(os.path.abspath(plugin_path))

    search_dirs = [
        os.path.join(plugin_dir, "Strings"),
        os.path.join(os.path.dirname(plugin_dir), "Strings"),
        plugin_dir,
    ]
    for extra in _collect_string_dirs(plugin_path):
        if extra not in search_dirs:
            search_dirs.append(extra)

    tables = StringTables()
    language = _detect_language()
    if language:
        logger.info(f"Using localization language: {language}")

    for ext, attr, has_prefix in [
        ("strings", "strings", False),
        ("ilstrings", "ilstrings", True),
        ("dlstrings", "dlstrings", True),
    ]:
        path = find_string_file(base, search_dirs, ext, language)
        if path:
            logger.info(f"Loading {ext} from {path}")
            setattr(tables, attr, read_string_table(path, has_prefix))

    return tables
