import fnmatch

from PyQt6.QtCore import QThread, pyqtSignal

from .archive_core import AssetCatalog


class FileSearchWorker(QThread):
    """Background worker for file searching"""

    progress = pyqtSignal(int, int)
    results_batch = pyqtSignal(list)
    finished_search = pyqtSignal(int)
    warning = pyqtSignal(str)
    BATCH_SIZE = 50

    def __init__(self, organizer: "mobase.IOrganizer", search_pattern: str,
                 file_extensions: list, search_in_bsa: bool = False,
                 only_active: bool = False):
        super().__init__()
        self._organizer = organizer
        self._search_pattern = search_pattern
        self._file_extensions = file_extensions
        self._search_in_bsa = search_in_bsa
        self._only_active = only_active
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        results_count = 0
        search_lower = self._search_pattern.lower()
        catalog = None
        try:
            catalog = AssetCatalog(
                self._organizer,
                include_archives=self._search_in_bsa,
                exhaustive=self._search_in_bsa,
                active_only=self._only_active,
            )
        except Exception as exc:
            self.warning.emit(str(exc))
            self.finished_search.emit(0)
            return

        try:
            processed = 0
            batch = []
            for source in catalog.iter_sources(
                self._file_extensions or None,
                include_archive_members=self._search_in_bsa,
                cancelled=lambda: self._cancelled,
            ):
                if self._cancelled:
                    break
                processed += 1
                if processed == 1 or processed % 250 == 0:
                    self.progress.emit(processed, 0)
                file_lower = source.filename.lower()
                if search_lower in file_lower or fnmatch.fnmatch(file_lower, f"*{search_lower}*"):
                    batch.append(source)
                    results_count += 1
                    if len(batch) >= self.BATCH_SIZE:
                        self.results_batch.emit(batch)
                        batch = []

            if batch:
                self.results_batch.emit(batch)

            for message in catalog.errors:
                self.warning.emit(message)

            self.finished_search.emit(results_count)
        finally:
            catalog.close()


__all__ = ["FileSearchWorker"]
