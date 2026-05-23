import struct
import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import mobase
from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class NifTextureEntry:
    mod_name: str
    relative_path: str
    textures: list[str] = field(default_factory=list)
    file_mtime: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.mod_name}|{self.relative_path}"

    @property
    def filename(self) -> str:
        return Path(self.relative_path).name


class LightweightNifParser:
    VER_10_0_1_0 = 0x0A000100
    VER_10_0_1_2 = 0x0A000102
    VER_10_1_0_0 = 0x0A010000
    VER_20_0_0_4 = 0x14000004

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.textures: list[str] = []
        self.version: int = 0
        self.user_version: int = 0
        self.user_version_2: int = 0

    def parse(self) -> list[str]:
        try:
            with open(self.filepath, "rb") as f:
                data = f.read()
        except IOError:
            return []

        self.textures = []

        try:
            self._parse_header(data)
        except Exception:
            pass

        self._find_textures_by_pattern(data)

        return sorted(set(self.textures))

    def _parse_header(self, data: bytes) -> None:
        pos = 0

        newline = data.find(b"\n", pos)
        if newline < 0:
            return

        header_str = data[pos:newline].decode("ascii", errors="ignore")
        pos = newline + 1

        match = re.search(r"Version (\d+)\.(\d+)\.(\d+)\.(\d+)", header_str)
        if match:
            v = [int(x) for x in match.groups()]
            self.version = (v[0] << 24) | (v[1] << 16) | (v[2] << 8) | v[3]

        if self.version < self.VER_10_0_1_0:
            return

        if pos + 4 > len(data):
            return
        self.version = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        if self.version >= self.VER_20_0_0_4:
            pos += 1

        if self.version >= self.VER_10_1_0_0:
            if pos + 4 > len(data):
                return
            self.user_version = struct.unpack_from("<I", data, pos)[0]
            pos += 4

        if pos + 4 > len(data):
            return
        num_blocks = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        if self.version >= self.VER_10_0_1_2 and self.user_version >= 3:
            if pos + 4 > len(data):
                return
            self.user_version_2 = struct.unpack_from("<I", data, pos)[0]
            pos += 4

            if pos >= len(data):
                return
            author_len = data[pos]
            pos += 1 + author_len

            if self.user_version_2 >= 130:
                pos += 4

            if pos >= len(data):
                return
            proc_len = data[pos]
            pos += 1 + proc_len

            if pos >= len(data):
                return
            exp_len = data[pos]
            pos += 1 + exp_len

            if self.user_version_2 >= 130:
                if pos >= len(data):
                    return
                max_len = data[pos]
                pos += 1 + max_len

        if pos + 2 > len(data):
            return
        num_block_types = struct.unpack_from("<H", data, pos)[0]
        pos += 2

        for _ in range(num_block_types):
            if pos + 4 > len(data):
                return
            str_len = struct.unpack_from("<I", data, pos)[0]
            pos += 4 + str_len

        pos += num_blocks * 2
        pos += num_blocks * 4

        if pos + 8 > len(data):
            return
        num_strings = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        max_string_len = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        for _ in range(num_strings):
            if pos + 4 > len(data):
                break
            str_len = struct.unpack_from("<I", data, pos)[0]
            pos += 4

            if str_len > 0 and str_len < 1000 and pos + str_len <= len(data):
                try:
                    s = data[pos : pos + str_len].decode("utf-8", errors="ignore")
                    if s.lower().endswith(".dds"):
                        self.textures.append(s)
                except Exception:
                    pass
            pos += str_len

    def _find_textures_by_pattern(self, data: bytes) -> None:
        pattern = rb"textures[/\\][^\x00\r\n\xff]{3,200}\.dds"

        for match in re.finditer(pattern, data, re.IGNORECASE):
            try:
                tex = match.group().decode("ascii", errors="ignore")
                tex = tex.replace("\\", "/")
                if tex not in self.textures:
                    self.textures.append(tex)
            except Exception:
                pass


class NifTextureIndex:
    CACHE_VERSION = 2
    PATH_CLEANUP_RE = re.compile(r"^(?:\.?/?(?:data|textures|meshes)/?)+", re.IGNORECASE)
    MULTI_SLASH_RE = re.compile(r"/+")

    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._cache_file = cache_dir / "nif_texture_index.json"

        self._nif_entries: dict[str, NifTextureEntry] = {}

        self._texture_to_nifs: dict[str, set[str]] = {}

        self._texture_filename_cache: dict[str, set[str]] = {}

        self._is_loaded = False
        self._is_dirty = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def nif_count(self) -> int:
        return len(self._nif_entries)

    @property
    def texture_count(self) -> int:
        return len(self._texture_to_nifs)

    @staticmethod
    @lru_cache(maxsize=10000)
    def normalize_path(path: str) -> str:
        if not path:
            return ""

        p = path.lower().replace("\\", "/").strip()
        p = NifTextureIndex.PATH_CLEANUP_RE.sub("", p)
        p = NifTextureIndex.MULTI_SLASH_RE.sub("/", p)
        return p.strip("/")

    @staticmethod
    def get_filename(path: str) -> str:
        normalized = NifTextureIndex.normalize_path(path)
        return normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized

    @staticmethod
    def remove_extension(path: str) -> str:
        return path[:-4] if path.lower().endswith(".dds") else path

    def load_from_cache(self) -> bool:
        if not self._cache_file.exists():
            return False

        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("version") != self.CACHE_VERSION:
                return False

            entries = data.get("entries", [])

            for entry_data in entries:
                entry = NifTextureEntry(
                    mod_name=entry_data["mod"],
                    relative_path=entry_data["path"],
                    textures=entry_data["textures"],
                    file_mtime=entry_data.get("mtime", 0),
                )
                self._add_entry(entry)

            self._is_loaded = True
            self._is_dirty = False
            return True

        except Exception:
            return False

    def save_to_cache(self) -> bool:
        if not self._is_dirty:
            return True

        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

            entries = []
            for entry in self._nif_entries.values():
                entries.append(
                    {
                        "mod": entry.mod_name,
                        "path": entry.relative_path,
                        "textures": entry.textures,
                        "mtime": entry.file_mtime,
                    }
                )

            data = {"version": self.CACHE_VERSION, "entries": entries}

            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            self._is_dirty = False
            return True

        except Exception:
            return False

    def _add_entry(self, entry: NifTextureEntry) -> None:
        key = entry.key
        self._nif_entries[key] = entry

        for tex in entry.textures:
            normalized = self.normalize_path(tex)

            if normalized not in self._texture_to_nifs:
                self._texture_to_nifs[normalized] = set()
            self._texture_to_nifs[normalized].add(key)

            filename = self.get_filename(tex)
            filename_no_ext = self.remove_extension(filename)

            for fn in [filename, filename_no_ext]:
                if fn:
                    if fn not in self._texture_filename_cache:
                        self._texture_filename_cache[fn] = set()
                    self._texture_filename_cache[fn].add(normalized)

    def add_nif(
        self,
        mod_name: str,
        relative_path: str,
        textures: list[str],
        mtime: float = 0,
    ) -> None:
        entry = NifTextureEntry(
            mod_name=mod_name,
            relative_path=relative_path,
            textures=textures,
            file_mtime=mtime,
        )
        self._add_entry(entry)
        self._is_dirty = True
        self._is_loaded = True

    def get_entry(self, mod_name: str, relative_path: str) -> Optional[NifTextureEntry]:
        key = f"{mod_name}|{relative_path}"
        return self._nif_entries.get(key)

    def find_nifs_by_texture(
        self,
        texture_query: str,
        limit: int = 500,
    ) -> list[tuple[NifTextureEntry, int]]:
        query = self.normalize_path(texture_query)
        query_no_ext = self.remove_extension(query)
        query_filename = self.get_filename(query)
        query_filename_no_ext = self.remove_extension(query_filename)

        candidates: dict[str, int] = {}

        for tex_path, nif_keys in self._texture_to_nifs.items():
            tex_no_ext = self.remove_extension(tex_path)
            tex_filename = self.get_filename(tex_path)
            tex_filename_no_ext = self.remove_extension(tex_filename)

            score = 0

            if query == tex_path:
                score = 100
            elif query_no_ext == tex_no_ext:
                score = 90
            elif query_filename == tex_filename:
                score = 80
            elif query_filename_no_ext == tex_filename_no_ext:
                score = 75
            elif tex_path.endswith(query):
                score = 60
            elif tex_no_ext.endswith(query_no_ext):
                score = 55
            elif tex_filename.endswith(query_filename):
                score = 50
            elif query in tex_path:
                score = 30
            elif query_no_ext in tex_no_ext:
                score = 25
            elif query_filename_no_ext in tex_filename_no_ext:
                score = 20

            if score > 0:
                for nif_key in nif_keys:
                    if nif_key not in candidates or candidates[nif_key] < score:
                        candidates[nif_key] = score

        if not candidates and query_filename_no_ext:
            for cached_fn, tex_paths in self._texture_filename_cache.items():
                if query_filename_no_ext in cached_fn or cached_fn in query_filename_no_ext:
                    for tex_path in tex_paths:
                        if tex_path in self._texture_to_nifs:
                            for nif_key in self._texture_to_nifs[tex_path]:
                                candidates[nif_key] = 15

        results = []
        for nif_key, score in candidates.items():
            if nif_key in self._nif_entries:
                results.append((self._nif_entries[nif_key], score))

        results.sort(key=lambda x: -x[1])
        return results[:limit]

    def find_textures_by_nif(
        self,
        nif_query: str,
        limit: int = 100,
    ) -> list[tuple[NifTextureEntry, int]]:
        query = nif_query.lower().strip()
        query_no_ext = query.removesuffix(".nif")

        results = []

        for entry in self._nif_entries.values():
            filename_lower = entry.filename.lower()
            path_lower = entry.relative_path.lower()
            filename_no_ext = filename_lower.removesuffix(".nif")

            score = 0

            if query == filename_lower:
                score = 100
            elif query_no_ext == filename_no_ext:
                score = 95
            elif filename_lower.startswith(query):
                score = 80
            elif filename_no_ext.startswith(query_no_ext):
                score = 75
            elif query in filename_lower:
                score = 60
            elif query_no_ext in filename_no_ext:
                score = 55
            elif query in path_lower:
                score = 40

            if score > 0:
                results.append((entry, score))

        results.sort(key=lambda x: -x[1])
        return results[:limit]

    def clear(self) -> None:
        self._nif_entries.clear()
        self._texture_to_nifs.clear()
        self._texture_filename_cache.clear()
        self.normalize_path.cache_clear()
        self._is_loaded = False
        self._is_dirty = False

    def invalidate_mod(self, mod_name: str) -> None:
        keys_to_remove = [k for k in self._nif_entries if k.startswith(f"{mod_name}|")]

        for key in keys_to_remove:
            entry = self._nif_entries.pop(key, None)
            if entry:
                for tex in entry.textures:
                    normalized = self.normalize_path(tex)
                    if normalized in self._texture_to_nifs:
                        self._texture_to_nifs[normalized].discard(key)

        self._is_dirty = True


class NifIndexWorker(QThread):
    started = pyqtSignal()
    progress = pyqtSignal(int, int, str)
    entry_ready = pyqtSignal(str, str, list, float)
    finished = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        organizer: "mobase.IOrganizer",
        index: NifTextureIndex,
        only_active: bool = True,
        incremental: bool = True,
    ):
        super().__init__()
        self._organizer = organizer
        self._index = index
        self._only_active = only_active
        self._incremental = incremental
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        self.started.emit()
        self._cancelled = False

        mod_list = self._organizer.modList()
        mods_path = Path(self._organizer.modsPath())

        nif_files: list[tuple[str, Path]] = []

        for mod_name in mod_list.allMods():
            if self._cancelled:
                break

            state = mod_list.state(mod_name)

            if self._only_active and not (state & mobase.ModState.ACTIVE):
                continue

            if not (state & mobase.ModState.EXISTS):
                continue

            mod_path = mods_path / mod_name

            if not mod_path.exists():
                continue

            try:
                for nif_path in mod_path.rglob("*.nif"):
                    nif_files.append((mod_name, nif_path))
            except Exception:
                continue

        if self._cancelled:
            self.finished.emit(0, 0)
            return

        total = len(nif_files)
        processed = 0
        new_textures = 0

        for mod_name, nif_path in nif_files:
            if self._cancelled:
                break

            processed += 1
            self.progress.emit(processed, total, nif_path.name)

            try:
                mod_path = mods_path / mod_name
                relative = str(nif_path.relative_to(mod_path))
                mtime = nif_path.stat().st_mtime

                if self._incremental:
                    existing = self._index.get_entry(mod_name, relative)
                    if existing and existing.file_mtime >= mtime:
                        continue

                parser = LightweightNifParser(nif_path)
                textures = parser.parse()

                if textures:
                    new_textures += len(textures)
                    self.entry_ready.emit(mod_name, relative, textures, mtime)

            except Exception:
                continue

        self.finished.emit(processed, new_textures)


__all__ = [
    "NifTextureEntry",
    "LightweightNifParser",
    "NifTextureIndex",
    "NifIndexWorker",
]

