from PyQt6.QtCore import QObject, QThread, pyqtSignal as Signal

from esp_viewer.core.exporter2 import ExportConfig, ExportEngine, ExportResult
from esp_viewer.core.data_types import PluginFile


class ExportWorker(QObject):
    finished = Signal(ExportResult)
    progress = Signal(int, int)

    def __init__(self, plugin: PluginFile, config: ExportConfig, resolve_full_name) -> None:
        super().__init__()
        self._plugin = plugin
        self._config = config
        self._resolve_full_name = resolve_full_name
        self._cancel_requested = False

    def run(self) -> None:
        engine = ExportEngine(self._plugin, self._config, self._resolve_full_name)
        result = engine.export(progress_callback=self._on_progress, cancel_check=self._cancel_check)
        self.finished.emit(result)

    def cancel(self) -> None:
        self._cancel_requested = True

    def _cancel_check(self) -> bool:
        return self._cancel_requested

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)


class ExportThread(QThread):
    def __init__(self, worker: ExportWorker) -> None:
        super().__init__()
        self._worker = worker

    def run(self) -> None:
        self._worker.run()
