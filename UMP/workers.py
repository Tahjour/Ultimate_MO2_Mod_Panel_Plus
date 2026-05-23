import fnmatch
import os

import mobase
from PyQt6.QtCore import QThread, pyqtSignal


class FileSearchWorker(QThread):
    """Background worker for file searching"""

    progress = pyqtSignal(int, int)
    result_found = pyqtSignal(str, str, str)
    finished_search = pyqtSignal(int)

    def __init__(self, organizer: "mobase.IOrganizer", search_pattern: str,
                 file_extensions: list, search_in_bsa: bool = False):
        super().__init__()
        self._organizer = organizer
        self._search_pattern = search_pattern
        self._file_extensions = file_extensions
        self._search_in_bsa = search_in_bsa
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        results_count = 0
        mod_list = self._organizer.modList()
        all_mods = mod_list.allMods()
        total_mods = len(all_mods)

        search_lower = self._search_pattern.lower()

        for i, mod_name in enumerate(all_mods):
            if self._cancelled:
                break

            self.progress.emit(i + 1, total_mods)

            state = mod_list.state(mod_name)
            if not (state & mobase.ModState.EXISTS):
                continue

            mod_info = self._organizer.getMod(mod_name)
            if not mod_info:
                continue

            mod_path = mod_info.absolutePath()
            if not mod_path or not os.path.exists(mod_path):
                continue

            try:
                for root, dirs, files in os.walk(mod_path):
                    if self._cancelled:
                        break

                    for file_name in files:
                        if self._cancelled:
                            break

                        file_lower = file_name.lower()

                        if self._file_extensions:
                            ext = os.path.splitext(file_lower)[1]
                            if ext and ext not in self._file_extensions:
                                continue

                        if search_lower in file_lower or fnmatch.fnmatch(file_lower, f"*{search_lower}*"):
                            full_path = os.path.join(root, file_name)
                            relative_path = os.path.relpath(full_path, mod_path)

                            self.result_found.emit(mod_name, relative_path, full_path)
                            results_count += 1

            except Exception:
                continue

        self.finished_search.emit(results_count)


__all__ = ["FileSearchWorker"]
