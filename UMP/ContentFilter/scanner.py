"""Модуль сканирования контента модов."""

import os
from pathlib import Path
from typing import Dict, Optional, Set, Callable
from dataclasses import dataclass, field
import logging

try:
    import mobase
except ImportError:
    mobase = None

from .content_flags import ContentFlags

logger = logging.getLogger("ContentFilter.Scanner")


@dataclass
class ContentCache:
    """Кеш результатов сканирования."""

    data: Dict[str, ContentFlags] = field(default_factory=dict)
    version: int = 0

    def get(self, mod_name: str) -> ContentFlags:
        return self.data.get(mod_name, ContentFlags.NONE)

    def set(self, mod_name: str, flags: ContentFlags) -> None:
        self.data[mod_name] = flags

    def remove(self, mod_name: str) -> None:
        self.data.pop(mod_name, None)

    def clear(self) -> None:
        self.data.clear()
        self.version += 1

    def __contains__(self, mod_name: str) -> bool:
        return mod_name in self.data


class ModContentScanner:
    """Сканер контента модов с кешированием."""

    PLUGIN_EXTENSIONS: Set[str] = {".esp", ".esm", ".esl"}
    ARCHIVE_EXTENSIONS: Set[str] = {".bsa", ".ba2"}
    CONFIG_EXTENSIONS: Set[str] = {".ini", ".toml", ".json", ".xml"}
    BINARY_EXTENSIONS: Set[str] = {".dll", ".asi"}

    CONTENT_FOLDERS: Dict[str, ContentFlags] = {
        "textures": ContentFlags.TEXTURES,
        "meshes": ContentFlags.MESHES,
        "scripts": ContentFlags.SCRIPTS,
        "interface": ContentFlags.INTERFACE,
        "music": ContentFlags.MUSIC,
        "sound": ContentFlags.SOUND,
        "skse": ContentFlags.SKSE,
        "mcm": ContentFlags.CONFIG,
    }

    def __init__(self, organizer: "mobase.IOrganizer"):
        self._organizer = organizer
        self._cache = ContentCache()
        self._scanning = False
        logger.info("ModContentScanner initialized")

    @property
    def cache(self) -> ContentCache:
        return self._cache

    def get_content_flags(self, mod_name: str) -> ContentFlags:
        """Получает флаги из кеша. O(1)."""

        return self._cache.get(mod_name)

    def scan_all_mods(
        self, progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> int:
        """Сканирует все моды и заполняет кеш."""

        logger.info("=" * 50)
        logger.info("scan_all_mods() called")

        if self._scanning:
            logger.warning("Scan already in progress")
            return 0

        self._scanning = True
        self._cache.clear()
        scanned = 0

        try:
            mod_list = self._organizer.modList()
            all_mods = mod_list.allMods()
            if not all_mods:
                logger.warning("No mods found!")
                return 0

            total = len(all_mods)
            mods_path = self._get_mods_directory()
            if mods_path is None:
                logger.error("Could not determine mods directory!")
                return 0

            for i, mod_name in enumerate(all_mods):
                try:
                    mod_path = mods_path / mod_name
                    if mod_path.exists():
                        flags = self._scan_mod_folder(mod_path)
                        self._cache.set(mod_name, flags)
                        scanned += 1
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Error scanning '{mod_name}': {e}")

                if progress_callback:
                    progress_callback(i + 1, total, mod_name)

            logger.info(f"Scan complete: {scanned}/{total} mods")
            logger.info(f"Statistics: {self.get_statistics()}")
            return scanned
        except Exception as e:  # noqa: BLE001
            logger.error(f"Exception in scan_all_mods: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return scanned
        finally:
            self._scanning = False

    def _get_mods_directory(self) -> Optional[Path]:
        """Получает путь к папке mods."""

        try:
            mods_path = self._organizer.modsPath()
            if hasattr(mods_path, "absolutePath"):
                mods_path = mods_path.absolutePath()
            if isinstance(mods_path, str) and mods_path:
                path = Path(mods_path)
                if path.exists():
                    return path

            base_path = self._organizer.basePath()
            if hasattr(base_path, "absolutePath"):
                base_path = base_path.absolutePath()
            if base_path:
                path = Path(str(base_path)) / "mods"
                if path.exists():
                    return path
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error getting mods directory: {e}")

        return None

    def _scan_mod_folder(self, mod_path: Path) -> ContentFlags:
        """Сканирует папку мода."""

        flags = ContentFlags.NONE
        try:
            for entry in mod_path.iterdir():
                name_lower = entry.name.lower()
                if entry.is_dir():
                    if name_lower in self.CONTENT_FOLDERS:
                        flags |= self.CONTENT_FOLDERS[name_lower]
                elif entry.is_file():
                    if name_lower == "meta.ini":
                        continue

                    ext_lower = entry.suffix.lower()
                    if ext_lower in self.PLUGIN_EXTENSIONS:
                        flags |= ContentFlags.PLUGINS
                    elif ext_lower in self.ARCHIVE_EXTENSIONS:
                        flags |= ContentFlags.BSA
                    elif ext_lower in self.CONFIG_EXTENSIONS:
                        flags |= ContentFlags.CONFIG
                    elif ext_lower in self.BINARY_EXTENSIONS:
                        flags |= ContentFlags.DLL

            if not (flags & ContentFlags.DLL) or not (flags & ContentFlags.CONFIG):
                for root, _, files in os.walk(mod_path):
                    rel_path = Path(root).relative_to(mod_path)
                    if len(rel_path.parts) >= 3:
                        continue

                    for file in files:
                        if file.lower() == "meta.ini":
                            continue

                        ext = Path(file).suffix.lower()
                        if ext in self.BINARY_EXTENSIONS:
                            flags |= ContentFlags.DLL
                        elif ext in self.CONFIG_EXTENSIONS:
                            flags |= ContentFlags.CONFIG

                    if (flags & ContentFlags.DLL) and (flags & ContentFlags.CONFIG):
                        break
        except PermissionError:
            pass
        except OSError as e:  # noqa: PERF203
            logger.debug(f"OS error scanning {mod_path}: {e}")

        return flags

    def get_statistics(self) -> Dict[str, int]:
        """Возвращает статистику по типам контента."""

        stats: Dict[str, int] = {}
        for flag, name, _ in ContentFlags.get_flag_info():
            stats[name] = 0

        for flags in self._cache.data.values():
            for flag, name, _ in ContentFlags.get_flag_info():
                if flags & flag:
                    stats[name] += 1

        return stats

    def clear_cache(self) -> None:
        """Очищает кеш."""

        self._cache.clear()

