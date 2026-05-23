from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from esp_viewer.core.data_types import PluginFile


_HEADER = ("<4s7I2H", 36)
_FOLDER_RECORD_104 = ("<QII", 16)
_FOLDER_RECORD_105 = ("<QIIII", 24)
_FILE_RECORD = ("<QII", 16)


@dataclass(frozen=True)
class BSAEntry:
    path: str
    size: int
    compressed: bool


@dataclass(frozen=True)
class ArchiveIndex:
    path: Path
    version: int
    files: Tuple[BSAEntry, ...]


def _read_cstring(data: bytes, pos: int) -> Tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end == -1:
        return "", len(data)
    value = data[pos:end].decode("utf-8", errors="ignore")
    return value, end + 1


def _read_bzstring(data: bytes, pos: int) -> Tuple[str, int]:
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


def _unpack(fmt_size: Tuple[str, int], data: bytes, pos: int):
    import struct

    fmt, sz = fmt_size
    if pos + sz > len(data):
        return None, pos
    return struct.unpack_from(fmt, data, pos), pos + sz


def _parse_ba2_index(data: bytes) -> Optional[ArchiveIndex]:
    import struct
    if len(data) < 24:
        return None
        
    magic, version, header_type, file_count, name_table_offset = struct.unpack_from("<4sI4sIQ", data, 0)
    if magic != b"BTDX":
        return None
        
    entries = []
    # BA2 GNRL (General) или DX10 (Textures)
    # Формат записей файлов зависит от типа архива
    pos = 24
    for _ in range(file_count):
        if header_type == b"GNRL":
            # name_hash, extension, directory_hash, flags, offset, packed_size, unpacked_size, sentinel
            # Нам важен размер и сжатие
            _, _, _, _, _, packed_sz, unpacked_sz, _ = struct.unpack_from("<I4sIIQQII", data, pos)
            is_compressed = packed_sz != 0 and packed_sz < unpacked_sz
            entries.append({"size": unpacked_sz, "compressed": is_compressed})
            pos += 44
        elif header_type == b"DX10":
            # name_hash, extension, directory_hash, flags, ... (разные поля для текстур)
            _, _, _, _, _, _, packed_sz, unpacked_sz = struct.unpack_from("<I4sIIBBII", data, pos)
            is_compressed = packed_sz != 0 and packed_sz < unpacked_sz
            entries.append({"size": unpacked_sz, "compressed": is_compressed})
            pos += 32
        else:
            break
            
    # Читаем таблицу имен
    final_entries = []
    if name_table_offset > 0 and name_table_offset < len(data):
        pos = name_table_offset
        for i in range(len(entries)):
            if pos + 2 > len(data):
                break
            name_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            if pos + name_len > len(data):
                break
            name = data[pos:pos+name_len].decode("utf-8", errors="ignore")
            pos += name_len
            
            e = entries[i]
            final_entries.append(BSAEntry(path=name.replace("\\", "/"), size=e["size"], compressed=e["compressed"]))
            
    return ArchiveIndex(path=Path(""), version=version, files=tuple(final_entries))


def _parse_bsa_index_from_bytes(data: bytes, max_files: Optional[int] = None) -> Optional[ArchiveIndex]:
    if data.startswith(b"BTDX"):
        return _parse_ba2_index(data)
        
    header_vals, pos = _unpack(_HEADER, data, 0)
    if not header_vals:
        return None

    (
        magic,
        version,
        _offset,
        archive_flags,
        folder_count,
        file_count,
        _total_folder_name_length,
        _total_file_name_length,
        _file_flags,
        _padding,
    ) = header_vals

    if magic != b"BSA\x00":
        return None

    folder_records: List[Tuple[int, int]] = []
    for _ in range(folder_count):
        if version == 105:
            vals, pos = _unpack(_FOLDER_RECORD_105, data, pos)
            if not vals:
                return None
            _name_hash, count, _pad1, offset_val, _pad2 = vals
        else:
            vals, pos = _unpack(_FOLDER_RECORD_104, data, pos)
            if not vals:
                return None
            _name_hash, count, offset_val = vals
        folder_records.append((count, offset_val))

    include_dirs = bool(archive_flags & 0x1)
    file_records: List[Tuple[str, int, bool]] = []
    for count, _offset_val in folder_records:
        folder_name = ""
        if include_dirs:
            folder_name, pos = _read_bzstring(data, pos)
        for _ in range(count):
            vals, pos = _unpack(_FILE_RECORD, data, pos)
            if not vals:
                return None
            _name_hash, size_raw, _foffset = vals
            is_compressed = bool(size_raw & 0x40000000)
            size = size_raw & 0x3FFFFFFF
            file_records.append((folder_name, size, is_compressed))

    file_names: List[str] = []
    for _ in range(file_count):
        name, pos = _read_cstring(data, pos)
        file_names.append(name)

    entries: List[BSAEntry] = []
    for idx, record in enumerate(file_records):
        folder_name, size, is_compressed = record
        file_name = file_names[idx] if idx < len(file_names) else ""
        if folder_name:
            full_name = f"{folder_name}\\{file_name}" if file_name else folder_name
        else:
            full_name = file_name
        if full_name:
            entries.append(BSAEntry(full_name.replace("/", "\\"), size, is_compressed))
        if max_files is not None and len(entries) >= max_files:
            break

    return ArchiveIndex(path=Path(""), version=version, files=tuple(entries))


def parse_bsa_index(path: Path, max_files: Optional[int] = None) -> Optional[ArchiveIndex]:
    try:
        import mmap

        with path.open("rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
                idx = _parse_bsa_index_from_bytes(data, max_files=max_files)
    except Exception:
        return None

    if idx is None:
        return None
    return ArchiveIndex(path=Path(path), version=idx.version, files=idx.files)


def find_associated_archives(plugin_path: Path) -> List[Path]:
    base = plugin_path.with_suffix("")
    archives = []
    # Skyrim/FO3/NV/FO4: .bsa, .ba2
    # Могут быть суффиксы - Textures.bsa, - Main.ba2 и т.д.
    extensions = [".bsa", ".ba2"]
    
    # Прямое совпадение имени
    for ext in extensions:
        p = plugin_path.with_suffix(ext)
        if p.exists():
            archives.append(p)
            
    # Совпадение с суффиксами (Skyrim/FO4 style)
    if plugin_path.parent.exists():
        stem = base.name.lower()
        for p in plugin_path.parent.iterdir():
            if p.suffix.lower() in extensions:
                if p.name.lower().startswith(stem):
                    if p not in archives:
                        archives.append(p)
    return archives


def build_archive_indices(archives: Iterable[Path]) -> Dict[Path, ArchiveIndex]:
    indices: Dict[Path, ArchiveIndex] = {}
    for ap in archives:
        idx = parse_bsa_index(ap)
        if idx is not None:
            indices[ap] = idx
    return indices


def compute_asset_conflicts(indices: Dict[Path, ArchiveIndex]) -> Dict[str, List[Path]]:
    paths: Dict[str, List[Path]] = {}
    for ap, idx in indices.items():
        for e in idx.files:
            key = e.path.lower()
            paths.setdefault(key, []).append(ap)
    return {k: v for k, v in paths.items() if len(v) > 1}


def attach_bsa_info(plugin: PluginFile) -> None:
    path = Path(plugin.path)
    data_dir = path.parent
    all_archives = [p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() in {".bsa", ".ba2"}]
    indices = build_archive_indices(all_archives)
    # Добавляем loose-файлы как ещё один условный контейнер, чтобы видеть конфликты
    # BSA ↔ loose аналогично bsplugins. Используем фиктивный путь
    # data_dir / "<loose>" для обозначения набора свободных файлов.
    loose_entries: List[BSAEntry] = []
    loose_container = data_dir / "<loose>"
    for root, _dirs, files in os.walk(data_dir):
        root_path = Path(root)
        for name in files:
            if name.lower().endswith((".bsa", ".ba2")):
                continue
            rel = root_path.joinpath(name).relative_to(data_dir)
            full_name = str(rel).replace("/", "\\")
            if full_name:
                loose_entries.append(BSAEntry(full_name, 0, False))

    if loose_entries:
        indices[loose_container] = ArchiveIndex(path=loose_container, version=0, files=tuple(loose_entries))

    conflicts = compute_asset_conflicts(indices)
    associated = find_associated_archives(path)
    plugin.bsa_archives = [str(p) for p in associated]
    associated_set = set(associated)
    is_base_game = not plugin.masters and plugin.path.lower().endswith(".esm")
    if is_base_game and loose_entries:
        associated_set.add(loose_container)

    conflict_map: Dict[str, List[str]] = {}
    for asset_path, owners in conflicts.items():
        # исключаем случаи, когда ресурс существует только в связанных с плагином
        # контейнерах (архивах или loose-папке для базовой игры)
        if all(owner in associated_set for owner in owners):
            continue

        if any(owner in associated_set for owner in owners) and any(
            owner not in associated_set for owner in owners
        ):
            conflict_map[asset_path] = [str(p) for p in owners]

    plugin.bsa_conflicts = conflict_map
