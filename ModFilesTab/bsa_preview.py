import struct
from pathlib import Path
from typing import Optional


_HEADER = struct.Struct("<4s7I2H")
_FOLDER_RECORD_104 = struct.Struct("<QII")
_FOLDER_RECORD_105 = struct.Struct("<QIIII")
_FILE_RECORD = struct.Struct("<QII")


def _read_cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end == -1:
        return "", len(data)
    value = data[pos:end].decode("utf-8", errors="ignore")
    return value, end + 1


def _read_bzstring(data: bytes, pos: int) -> tuple[str, int]:
    if pos >= len(data):
        return "", pos
    length = data[pos]
    pos += 1
    if length == 0:
        return "", pos
    end = min(pos + length, len(data))
    value = data[pos:end].decode("utf-8", errors="ignore")
    pos = end
    if pos < len(data) and data[pos] == 0:
        pos += 1
    return value, pos


def _decode_flags(value: int, mapping: dict[int, str]) -> list[str]:
    labels: list[str] = []
    for bit, name in mapping.items():
        if value & bit:
            labels.append(name)
    return labels


def build_bsa_preview(path: Path, max_files: int = 2000) -> Optional[tuple[str, str]]:
    try:
        data = path.read_bytes()
    except Exception:
        return None

    if len(data) < _HEADER.size:
        return None

    (
        magic,
        version,
        offset,
        archive_flags,
        folder_count,
        file_count,
        total_folder_name_length,
        total_file_name_length,
        file_flags,
        _padding,
    ) = _HEADER.unpack_from(data, 0)

    if magic != b"BSA\x00":
        return None

    pos = _HEADER.size
    folder_records: list[tuple[int, int]] = []
    for _ in range(folder_count):
        if version == 105:
            if pos + _FOLDER_RECORD_105.size > len(data):
                return None
            name_hash, count, _pad1, offset_val, _pad2 = _FOLDER_RECORD_105.unpack_from(data, pos)
            pos += _FOLDER_RECORD_105.size
        else:
            if pos + _FOLDER_RECORD_104.size > len(data):
                return None
            name_hash, count, offset_val = _FOLDER_RECORD_104.unpack_from(data, pos)
            pos += _FOLDER_RECORD_104.size
        folder_records.append((count, offset_val))

    folders: list[str] = []
    file_records: list[tuple[str, int, bool]] = []
    include_dirs = bool(archive_flags & 0x1)

    for count, _offset_val in folder_records:
        folder_name = ""
        if include_dirs:
            folder_name, pos = _read_bzstring(data, pos)
        folders.append(folder_name)
        for _ in range(count):
            if pos + _FILE_RECORD.size > len(data):
                return None
            _name_hash, size_raw, _offset = _FILE_RECORD.unpack_from(data, pos)
            pos += _FILE_RECORD.size
            is_compressed = bool(size_raw & 0x40000000)
            size = size_raw & 0x3FFFFFFF
            file_records.append((folder_name, size, is_compressed))

    file_names: list[str] = []
    for _ in range(file_count):
        name, pos = _read_cstring(data, pos)
        file_names.append(name)

    entries: list[tuple[str, int, bool]] = []
    for idx, record in enumerate(file_records):
        folder_name, size, is_compressed = record
        file_name = file_names[idx] if idx < len(file_names) else ""
        if folder_name:
            full_name = f"{folder_name}\\{file_name}" if file_name else folder_name
        else:
            full_name = file_name
        entries.append((full_name, size, is_compressed))

    top_folders: dict[str, int] = {}
    for name, _size, _compressed in entries:
        if not name:
            continue
        root = name.split("\\", 1)[0].split("/", 1)[0]
        top_folders[root] = top_folders.get(root, 0) + 1

    archive_flags_map = {
        0x1: "IncludeDirectoryNames",
        0x2: "IncludeFileNames",
        0x4: "CompressedArchive",
        0x8: "RetainDirectoryNames",
        0x10: "RetainFileNames",
        0x20: "RetainFileNameOffsets",
        0x40: "Xbox360Archive",
        0x80: "RetainStringsDuringStartup",
        0x100: "EmbedFileNames",
        0x200: "XMemCodec",
    }
    file_flags_map = {
        0x1: "Meshes",
        0x2: "Textures",
        0x4: "Menus",
        0x8: "Sounds",
        0x10: "Voices",
        0x20: "Shaders",
        0x40: "Trees",
        0x80: "Fonts",
        0x100: "Misc",
    }

    lines: list[str] = []
    version_name = "Skyrim" if version == 104 else "Skyrim SE" if version == 105 else "Unknown"
    lines.append(f"Version: {version} ({version_name})")
    lines.append(f"Folders: {folder_count}")
    lines.append(f"Files: {file_count}")
    lines.append(f"Archive flags: 0x{archive_flags:08X} ({', '.join(_decode_flags(archive_flags, archive_flags_map))})")
    lines.append(f"File flags: 0x{file_flags:04X} ({', '.join(_decode_flags(file_flags, file_flags_map))})")
    lines.append(f"Total folder names: {total_folder_name_length}")
    lines.append(f"Total file names: {total_file_name_length}")

    if top_folders:
        lines.append("Top folders:")
        for name, count in sorted(top_folders.items(), key=lambda x: (-x[1], x[0]))[:40]:
            lines.append(f"  {name} ({count})")

    lines.append("Files:")
    limited_entries = entries[:max_files]
    for name, size, is_compressed in limited_entries:
        suffix = " compressed" if is_compressed else ""
        lines.append(f"  {name} ({size} bytes{suffix})")
    if len(entries) > len(limited_entries):
        lines.append(f"  ... {len(entries) - len(limited_entries)} more")

    return "BSA preview", "\n".join(lines)
