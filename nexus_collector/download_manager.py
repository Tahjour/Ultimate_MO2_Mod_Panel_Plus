"""
Менеджер скачивания модов.
Поддерживает два режима:
  1. Premium — через Nexus API (прямые ссылки)
  2. Non-Premium — через nxm:// URL (MO2 перехватывает его)
"""

import webbrowser
import sys
import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal, QThread

if TYPE_CHECKING:
    import mobase
    from .nexus_api import NexusApi
    from .collection_storage import CollectionStorage


class DownloadWorker(QThread):
    """Фоновый поток для скачивания через API."""

    finished = pyqtSignal(str, bool, str)  # unique_id, success, message
    progress = pyqtSignal(str, int)  # unique_id, percent

    def __init__(
        self,
        unique_id: str,
        game: str,
        mod_id: int,
        file_id: int,
        api: "NexusApi",
        organizer: "mobase.IOrganizer",
    ):
        super().__init__()
        self._unique_id = unique_id
        self._game = game
        self._mod_id = mod_id
        self._file_id = file_id
        self._api = api
        self._organizer = organizer

    def run(self):
        try:
            # Получаем ссылку на скачивание (только для Premium)
            links = self._api.get_download_links(
                self._game, self._mod_id, self._file_id
            )
            if not links:
                self.finished.emit(
                    self._unique_id, False, "No download links available"
                )
                return

            download_url = links[0].uri

            # Пробуем через MO2 download manager
            self._download_via_mo2(download_url)

        except Exception as e:
            error_msg = str(e)
            # Если 403 — non-premium, используем nxm://
            if "403" in error_msg or "Premium" in error_msg:
                self._download_via_nxm()
            else:
                self.finished.emit(self._unique_id, False, error_msg)

    def _download_via_mo2(self, url: str):
        """Скачивание через MO2 download manager."""
        try:
            dm = self._organizer.downloadManager()

            # Пробуем startDownloadURLs
            if hasattr(dm, 'startDownloadURLs'):
                download_id = dm.startDownloadURLs([url])
                if download_id >= 0:
                    self.finished.emit(
                        self._unique_id, True,
                        f"Download started in MO2 (ID: {download_id})"
                    )
                    return

            # Пробуем addDownload
            if hasattr(dm, 'addDownload'):
                download_id = dm.addDownload(url)
                if download_id >= 0:
                    self.finished.emit(
                        self._unique_id, True,
                        f"Download started in MO2 (ID: {download_id})"
                    )
                    return

        except Exception:
            pass

        # Fallback на nxm://
        self._download_via_nxm()

    def _download_via_nxm(self):
        """Скачивание через nxm:// протокол — MO2 перехватит."""
        nxm_url = f"nxm://{self._game}/mods/{self._mod_id}/files/{self._file_id}"

        try:
            if sys.platform == 'win32':
                os.startfile(nxm_url)
            else:
                webbrowser.open(nxm_url)

            self.finished.emit(
                self._unique_id, True,
                f"Sent to MO2 via nxm:// (mod {self._mod_id}, file {self._file_id})"
            )
        except Exception as e:
            self.finished.emit(
                self._unique_id, False,
                f"Failed to open nxm link: {e}"
            )


class DownloadManager(QObject):
    """
    Координирует скачивание модов.
    """

    download_started = pyqtSignal(str)  # unique_id
    download_finished = pyqtSignal(str, bool, str)  # unique_id, success, message
    download_progress = pyqtSignal(str, int)  # unique_id, percent

    def __init__(
        self,
        api: "NexusApi",
        organizer: "mobase.IOrganizer",
        storage: "CollectionStorage",
    ):
        super().__init__()
        self._api = api
        self._organizer = organizer
        self._storage = storage
        self._active_downloads: dict[str, DownloadWorker] = {}

    def download_mod(
        self, unique_id: str, game: str, mod_id: int, file_id: int | None = None
    ):
        """
        Начинает скачивание мода.
        Если file_id не указан, выбирает основной файл.
        """
        if unique_id in self._active_downloads:
            return

        self._storage.update_mod_status(unique_id, "downloading")
        self.download_started.emit(unique_id)

        if file_id is None:
            # Нужно определить file_id — получаем список файлов
            try:
                files = self._api.get_mod_files(game, int(mod_id))
                if not files:
                    self._on_download_finished(
                        unique_id, False, "No files found"
                    )
                    return
                # Выбираем Primary или первый MAIN файл
                primary = next((f for f in files if f.is_primary), None)
                main = next(
                    (f for f in files if f.category_name == "MAIN"), None
                )
                chosen = primary or main or files[0]
                file_id = chosen.file_id
            except Exception as e:
                self._on_download_finished(unique_id, False, str(e))
                return

        worker = DownloadWorker(
            unique_id=unique_id,
            game=game,
            mod_id=int(mod_id),
            file_id=file_id,
            api=self._api,
            organizer=self._organizer,
        )
        worker.finished.connect(self._on_download_finished)
        worker.progress.connect(self.download_progress.emit)
        self._active_downloads[unique_id] = worker
        worker.start()

    def download_via_browser(self, game: str, mod_id: str):
        """
        Открывает страницу скачивания в браузере (для non-premium).
        """
        url = f"https://www.nexusmods.com/{game}/mods/{mod_id}?tab=files"
        webbrowser.open(url)

    def download_via_nxm(self, game: str, mod_id: int, file_id: int):
        """Запускает скачивание через nxm:// протокол."""
        nxm_url = f"nxm://{game}/mods/{mod_id}/files/{file_id}"
        try:
            if sys.platform == 'win32':
                os.startfile(nxm_url)
            else:
                webbrowser.open(nxm_url)
        except Exception:
            webbrowser.open(nxm_url)

    def _on_download_finished(
        self, unique_id: str, success: bool, message: str
    ):
        status = "installed" if success else "error"
        self._storage.update_mod_status(unique_id, status)
        self.download_finished.emit(unique_id, success, message)

        # Убираем из активных
        worker = self._active_downloads.pop(unique_id, None)
        if worker:
            worker.deleteLater()