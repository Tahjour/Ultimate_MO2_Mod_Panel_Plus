from __future__ import annotations

import ctypes
import mmap
import os
import struct
import threading
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional


GAME_DATA_OWNER = "[Game Data]"
_BSA_HEADER = struct.Struct("<4s8I")
_BSA_FOLDER_104 = struct.Struct("<QII")
_BSA_FOLDER_105 = struct.Struct("<QIIQ")
_BSA_FILE = struct.Struct("<QII")
_FLAG_DIRECTORY_NAMES = 0x1
_FLAG_FILE_NAMES = 0x2
_FLAG_COMPRESSED = 0x4
_FLAG_EMBED_FILE_NAMES = 0x100
_FILE_COMPRESSION_TOGGLE = 0x40000000
_FILE_SIZE_MASK = 0x3FFFFFFF


def normalize_virtual_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


@dataclass(frozen=True)
class AssetSource:
    owner: str
    virtual_path: str
    source_kind: str
    container_path: str
    physical_path: str = ""
    archive_name: str = ""
    is_game: bool = False
    mtime: float = 0.0

    @property
    def filename(self) -> str:
        return self.virtual_path.rsplit("/", 1)[-1]

    @property
    def location_text(self) -> str:
        if self.source_kind == "bsa":
            return f"{self.container_path} :: {self.virtual_path}"
        return self.physical_path or self.container_path

    @property
    def navigation_path(self) -> str:
        return self.container_path if self.source_kind == "bsa" else self.physical_path


@dataclass(frozen=True)
class BsaMember:
    virtual_path: str
    offset: int
    stored_size: int
    compressed: bool


@dataclass(frozen=True)
class BsaIndex:
    path: Path
    version: int
    archive_flags: int
    members: tuple[BsaMember, ...]


_INDEX_CACHE: dict[tuple[str, int, int], BsaIndex] = {}
_INDEX_CACHE_LOCK = threading.Lock()
_LZ4_CACHE: dict[str, object] = {}


def _fingerprint(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return (str(path.resolve()).lower(), stat.st_size, stat.st_mtime_ns)


def _read_bzstring(data: memoryview, pos: int) -> tuple[str, int]:
    if pos >= len(data):
        raise ValueError("BSA directory name is truncated")
    length = data[pos]
    pos += 1
    end = pos + length
    if end > len(data):
        raise ValueError("BSA directory name is truncated")
    value = bytes(data[pos:end]).rstrip(b"\x00").decode("utf-8", errors="ignore")
    return value, end


def _read_cstring(data: memoryview, pos: int) -> tuple[str, int]:
    end = pos
    while end < len(data) and data[end] != 0:
        end += 1
    if end >= len(data):
        raise ValueError("BSA filename table is truncated")
    value = bytes(data[pos:end]).decode("utf-8", errors="ignore")
    return value, end + 1


def _parse_bsa_index_data(path: Path, data: memoryview) -> BsaIndex:
    if len(data) < _BSA_HEADER.size:
        raise ValueError("Archive is smaller than a BSA header")

    (
        magic,
        version,
        folder_offset,
        archive_flags,
        folder_count,
        file_count,
        _folder_name_length,
        _file_name_length,
        _file_flags,
    ) = _BSA_HEADER.unpack_from(data, 0)

    if magic != b"BSA\x00":
        raise ValueError("Not a BSA archive")
    if version not in (104, 105):
        raise ValueError(f"Unsupported BSA version: {version}")
    if not (archive_flags & _FLAG_FILE_NAMES):
        raise ValueError("BSA archives without filenames are unsupported")

    folder_struct = _BSA_FOLDER_105 if version == 105 else _BSA_FOLDER_104
    pos = folder_offset
    folder_file_counts: list[int] = []
    for _ in range(folder_count):
        if pos + folder_struct.size > len(data):
            raise ValueError("BSA folder records are truncated")
        values = folder_struct.unpack_from(data, pos)
        folder_file_counts.append(values[1])
        pos += folder_struct.size

    raw_records: list[tuple[str, int, int]] = []
    for count in folder_file_counts:
        folder_name = ""
        if archive_flags & _FLAG_DIRECTORY_NAMES:
            folder_name, pos = _read_bzstring(data, pos)
        for _ in range(count):
            if pos + _BSA_FILE.size > len(data):
                raise ValueError("BSA file records are truncated")
            _name_hash, raw_size, file_offset = _BSA_FILE.unpack_from(data, pos)
            raw_records.append((folder_name, raw_size, file_offset))
            pos += _BSA_FILE.size

    if len(raw_records) != file_count:
        raise ValueError("BSA file count does not match folder records")

    names: list[str] = []
    for _ in range(file_count):
        name, pos = _read_cstring(data, pos)
        names.append(name)

    default_compressed = bool(archive_flags & _FLAG_COMPRESSED)
    members: list[BsaMember] = []
    for name, (folder, raw_size, file_offset) in zip(names, raw_records):
        virtual_path = normalize_virtual_path(f"{folder}/{name}" if folder else name)
        if not virtual_path:
            continue
        compressed = default_compressed ^ bool(raw_size & _FILE_COMPRESSION_TOGGLE)
        members.append(
            BsaMember(
                virtual_path=virtual_path,
                offset=file_offset,
                stored_size=raw_size & _FILE_SIZE_MASK,
                compressed=compressed,
            )
        )

    return BsaIndex(path=path, version=version, archive_flags=archive_flags, members=tuple(members))


def _parse_bsa_index(path: Path) -> BsaIndex:
    with path.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            data = memoryview(mapped)
            try:
                return _parse_bsa_index_data(path, data)
            finally:
                data.release()


def _get_bsa_index(path: Path) -> BsaIndex:
    key = _fingerprint(path)
    with _INDEX_CACHE_LOCK:
        cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    index = _parse_bsa_index(path)
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE[key] = index
    return index


def _load_lz4(explicit_path: Optional[Path] = None):
    candidates: list[Path | str] = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    env_path = os.environ.get("MO2_LZ4_PATH")
    if env_path:
        candidates.append(Path(env_path))
    try:
        candidates.append(Path(__file__).resolve().parents[2] / "dlls" / "liblz4.dll")
    except IndexError:
        pass
    candidates.extend(["liblz4.dll", "lz4.dll"])

    errors: list[str] = []
    for candidate in candidates:
        key = str(candidate)
        if key in _LZ4_CACHE:
            return _LZ4_CACHE[key]
        try:
            lib = ctypes.CDLL(key)
            lib.LZ4_decompress_safe.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
            ]
            lib.LZ4_decompress_safe.restype = ctypes.c_int
            lib.LZ4F_createDecompressionContext.argtypes = [
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_uint,
            ]
            lib.LZ4F_createDecompressionContext.restype = ctypes.c_size_t
            lib.LZ4F_freeDecompressionContext.argtypes = [ctypes.c_void_p]
            lib.LZ4F_freeDecompressionContext.restype = ctypes.c_size_t
            lib.LZ4F_decompress.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.c_void_p,
            ]
            lib.LZ4F_decompress.restype = ctypes.c_size_t
            lib.LZ4F_isError.argtypes = [ctypes.c_size_t]
            lib.LZ4F_isError.restype = ctypes.c_uint
            lib.LZ4F_getErrorName.argtypes = [ctypes.c_size_t]
            lib.LZ4F_getErrorName.restype = ctypes.c_char_p
            _LZ4_CACHE[key] = lib
            return lib
        except (OSError, AttributeError) as exc:
            errors.append(f"{candidate}: {exc}")

    raise RuntimeError("Could not load liblz4 for Skyrim BSA decompression: " + "; ".join(errors))


def _lz4_error(lib, code: int) -> str:
    if not lib.LZ4F_isError(code):
        return ""
    name = lib.LZ4F_getErrorName(code)
    return name.decode("ascii", errors="ignore") if name else "unknown LZ4 error"


def _decompress_lz4_frame(packed: bytes, expected_size: int, lib) -> bytes:
    context = ctypes.c_void_p()
    result = lib.LZ4F_createDecompressionContext(ctypes.byref(context), 100)
    error = _lz4_error(lib, result)
    if error:
        raise ValueError(f"LZ4 context creation failed: {error}")

    source = ctypes.create_string_buffer(packed)
    output = bytearray()
    source_pos = 0
    try:
        while True:
            remaining = max(expected_size - len(output), 1)
            target = ctypes.create_string_buffer(remaining)
            target_size = ctypes.c_size_t(remaining)
            source_size = ctypes.c_size_t(len(packed) - source_pos)
            source_ptr = ctypes.cast(ctypes.byref(source, source_pos), ctypes.c_void_p)
            result = lib.LZ4F_decompress(
                context,
                target,
                ctypes.byref(target_size),
                source_ptr,
                ctypes.byref(source_size),
                None,
            )
            error = _lz4_error(lib, result)
            if error:
                raise ValueError(f"LZ4 decompression failed: {error}")
            output.extend(target.raw[: target_size.value])
            source_pos += source_size.value
            if result == 0:
                break
            if source_size.value == 0 and target_size.value == 0:
                raise ValueError("LZ4 decompression made no progress")
    finally:
        lib.LZ4F_freeDecompressionContext(context)

    if len(output) != expected_size:
        raise ValueError("LZ4 decompression size mismatch")
    return bytes(output)


class BsaArchive:
    def __init__(self, path: Path, lz4_path: Optional[Path] = None):
        self.path = Path(path)
        self._lz4_path = lz4_path
        self._index: Optional[BsaIndex] = None
        self._by_path: Optional[dict[str, BsaMember]] = None
        self._handle = None
        self._read_lock = threading.Lock()

    @property
    def index(self) -> BsaIndex:
        if self._index is None:
            self._index = _get_bsa_index(self.path)
        return self._index

    @property
    def members(self) -> tuple[BsaMember, ...]:
        return self.index.members

    def find_member(self, virtual_path: str) -> Optional[BsaMember]:
        if self._by_path is None:
            self._by_path = {member.virtual_path: member for member in self.members}
        return self._by_path.get(normalize_virtual_path(virtual_path))

    def extract(self, member: BsaMember) -> bytes:
        with self._read_lock:
            if self._handle is None or self._handle.closed:
                self._handle = self.path.open("rb")
            self._handle.seek(member.offset)
            payload = self._handle.read(member.stored_size)
        if len(payload) != member.stored_size:
            raise ValueError(f"Truncated BSA member: {member.virtual_path}")

        if self.index.archive_flags & _FLAG_EMBED_FILE_NAMES:
            if not payload:
                raise ValueError(f"Missing embedded name: {member.virtual_path}")
            name_size = payload[0] + 1
            payload = payload[name_size:]

        if not member.compressed:
            return payload
        if len(payload) < 4:
            raise ValueError(f"Missing uncompressed size: {member.virtual_path}")

        expected_size = struct.unpack_from("<I", payload, 0)[0]
        packed = payload[4:]
        if self.index.version == 105:
            lib = _load_lz4(self._lz4_path)
            if packed.startswith(b"\x04\x22\x4d\x18"):
                return _decompress_lz4_frame(packed, expected_size, lib)
            out = ctypes.create_string_buffer(expected_size)
            source = ctypes.create_string_buffer(packed)
            result = lib.LZ4_decompress_safe(source, out, len(packed), expected_size)
            if result < 0 or result != expected_size:
                raise ValueError(f"LZ4 decompression failed: {member.virtual_path}")
            return out.raw[:result]

        raw = zlib.decompress(packed)
        if len(raw) != expected_size:
            raise ValueError(f"Zlib size mismatch: {member.virtual_path}")
        return raw

    def close(self) -> None:
        with self._read_lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _state_matches(state, active_only: bool) -> bool:
    try:
        import mobase

        if not (state & mobase.ModState.EXISTS):
            return False
        return not active_only or bool(state & mobase.ModState.ACTIVE)
    except Exception:
        return True


def _game_data_path(organizer) -> Optional[Path]:
    try:
        game = organizer.managedGame()
        directory = game.dataDirectory()
        value = directory.absolutePath() if hasattr(directory, "absolutePath") else str(directory)
        path = Path(value)
        if path.exists():
            return path
    except Exception:
        pass
    return None


def _iter_mod_roots(organizer, active_only: bool) -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    mod_list = organizer.modList()
    for mod_name in mod_list.allMods():
        try:
            if not _state_matches(mod_list.state(mod_name), active_only):
                continue
            mod = mod_list.getMod(mod_name)
            root = Path(mod.absolutePath()) if mod else Path(organizer.modsPath()) / mod_name
            if root.exists():
                roots.append((mod_name, root))
        except Exception:
            continue
    return roots


def _feature_archive_names(organizer) -> list[str]:
    names: list[str] = []
    try:
        import mobase

        feature = organizer.gameFeatures().gameFeature(mobase.DataArchives)
        profile = organizer.profile()
        for value in list(feature.archives(profile)) + list(feature.vanillaArchives()):
            if value not in names:
                names.append(value)
    except Exception:
        pass
    return names


class AssetCatalog:
    def __init__(
        self,
        organizer,
        include_archives: bool = False,
        exhaustive: bool = False,
        active_only: bool = False,
        lz4_path: Optional[Path] = None,
    ):
        self.organizer = organizer
        self.include_archives = include_archives
        self.exhaustive = exhaustive
        self.active_only = active_only and not exhaustive
        self.lz4_path = lz4_path
        self.mod_roots = _iter_mod_roots(organizer, self.active_only)
        self.game_data_root = _game_data_path(organizer) if exhaustive else None
        self.errors: list[str] = []
        self._archive_containers: Optional[list[tuple[str, bool, Path]]] = None
        self._archive_sources: Optional[list[tuple[str, bool, BsaArchive]]] = None

    def _discover_archive_containers(self) -> list[tuple[str, bool, Path]]:
        if not self.include_archives:
            return []

        found: list[tuple[str, bool, Path]] = []
        seen: set[str] = set()

        def add(owner: str, is_game: bool, path: Path) -> None:
            try:
                key = str(path.resolve()).lower()
            except Exception:
                return
            if key not in seen and path.exists() and path.suffix.lower() == ".bsa":
                seen.add(key)
                found.append((owner, is_game, path))

        for owner, root in self.mod_roots:
            try:
                for path in root.rglob("*.bsa"):
                    add(owner, False, path)
            except Exception as exc:
                self.errors.append(f"{owner}: {exc}")

        if self.game_data_root is not None:
            for name in _feature_archive_names(self.organizer):
                candidate = Path(name)
                add(GAME_DATA_OWNER, True, candidate if candidate.is_absolute() else self.game_data_root / candidate)
            try:
                for path in self.game_data_root.iterdir():
                    if path.is_file() and path.suffix.lower() == ".bsa":
                        add(GAME_DATA_OWNER, True, path)
            except Exception as exc:
                self.errors.append(f"{GAME_DATA_OWNER}: {exc}")

        return found

    @property
    def archive_containers(self) -> list[tuple[str, bool, Path]]:
        if self._archive_containers is None:
            self._archive_containers = self._discover_archive_containers()
        return self._archive_containers

    def _load_archives(self) -> list[tuple[str, bool, BsaArchive]]:
        archives: list[tuple[str, bool, BsaArchive]] = []
        for owner, is_game, path in self.archive_containers:
            archive = BsaArchive(path, self.lz4_path)
            try:
                archive.members
            except Exception as exc:
                self.errors.append(f"{path.name}: {exc}")
                continue
            archives.append((owner, is_game, archive))
        return archives

    @property
    def archives(self) -> list[tuple[str, bool, BsaArchive]]:
        if self._archive_sources is None:
            self._archive_sources = self._load_archives()
        return self._archive_sources

    def archive_fingerprints(self) -> list[list[object]]:
        if not self.include_archives:
            return []
        fingerprints: list[list[object]] = []
        for _owner, _is_game, archive_path in self.archive_containers:
            path, size, mtime = _fingerprint(archive_path)
            fingerprints.append([path, size, mtime])
        fingerprints.sort(key=lambda item: str(item[0]))
        return fingerprints

    def iter_sources(
        self,
        extensions: Optional[Iterable[str]] = None,
        include_archive_members: bool = True,
        cancelled: Optional[Callable[[], bool]] = None,
    ):
        wanted = {ext.lower() for ext in extensions} if extensions else None
        roots = list(self.mod_roots)
        if self.game_data_root is not None:
            roots.append((GAME_DATA_OWNER, self.game_data_root))

        for owner, root in roots:
            is_game = owner == GAME_DATA_OWNER
            try:
                for current_root, _dirs, files in os.walk(root):
                    if cancelled and cancelled():
                        return
                    for name in files:
                        ext = Path(name).suffix.lower()
                        if wanted is not None and ext not in wanted:
                            continue
                        full_path = Path(current_root) / name
                        virtual_path = normalize_virtual_path(str(full_path.relative_to(root)))
                        yield AssetSource(
                            owner=owner,
                            virtual_path=virtual_path,
                            source_kind="loose",
                            container_path=str(full_path),
                            physical_path=str(full_path),
                            is_game=is_game,
                            mtime=full_path.stat().st_mtime,
                        )
            except Exception as exc:
                self.errors.append(f"{owner}: {exc}")

        if not (self.include_archives and include_archive_members):
            return
        for owner, is_game, archive in self.archives:
            if cancelled and cancelled():
                return
            mtime = archive.path.stat().st_mtime
            for member in archive.members:
                if cancelled and cancelled():
                    return
                ext = Path(member.virtual_path).suffix.lower()
                if wanted is not None and ext not in wanted:
                    continue
                yield AssetSource(
                    owner=owner,
                    virtual_path=member.virtual_path,
                    source_kind="bsa",
                    container_path=str(archive.path),
                    archive_name=archive.path.name,
                    is_game=is_game,
                    mtime=mtime,
                )

    def find_virtual_path(self, virtual_path: str) -> list[AssetSource]:
        normalized = normalize_virtual_path(virtual_path)
        matches: list[AssetSource] = []
        roots = list(self.mod_roots)
        if self.game_data_root is not None:
            roots.append((GAME_DATA_OWNER, self.game_data_root))

        disk_relative = Path(*normalized.split("/"))
        for owner, root in roots:
            candidate = root / disk_relative
            if candidate.exists():
                matches.append(
                    AssetSource(
                        owner=owner,
                        virtual_path=normalized,
                        source_kind="loose",
                        container_path=str(candidate),
                        physical_path=str(candidate),
                        is_game=owner == GAME_DATA_OWNER,
                        mtime=candidate.stat().st_mtime,
                    )
                )

        for owner, is_game, archive in self.archives:
            member = archive.find_member(normalized)
            if member is not None:
                matches.append(
                    AssetSource(
                        owner=owner,
                        virtual_path=member.virtual_path,
                        source_kind="bsa",
                        container_path=str(archive.path),
                        archive_name=archive.path.name,
                        is_game=is_game,
                        mtime=archive.path.stat().st_mtime,
                    )
                )
        return matches

    def read_bytes(self, source: AssetSource) -> bytes:
        if source.source_kind == "loose":
            return Path(source.physical_path).read_bytes()
        archive_path = str(Path(source.container_path).resolve()).lower()
        for _owner, _is_game, archive in self.archives:
            if str(archive.path.resolve()).lower() == archive_path:
                member = archive.find_member(source.virtual_path)
                if member is None:
                    break
                return archive.extract(member)
        raise FileNotFoundError(source.location_text)

    def close(self) -> None:
        if self._archive_sources is None:
            return
        for _owner, _is_game, archive in self._archive_sources:
            archive.close()


def build_index_scope(organizer, include_archives: bool, only_active: bool) -> dict:
    exhaustive = bool(include_archives)
    catalog = AssetCatalog(
        organizer,
        include_archives=include_archives,
        exhaustive=exhaustive,
        active_only=only_active,
    )
    return {
        "include_archives": bool(include_archives),
        "only_active": bool(only_active and not exhaustive),
        "archive_fingerprints": catalog.archive_fingerprints(),
    }


__all__ = [
    "AssetCatalog",
    "AssetSource",
    "BsaArchive",
    "BsaIndex",
    "BsaMember",
    "GAME_DATA_OWNER",
    "build_index_scope",
    "normalize_virtual_path",
]
