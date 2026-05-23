"""
HTTP-сервер, принимающий данные от браузерного расширения.
Работает в отдельном потоке, чтобы не блокировать GUI MO2.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    import mobase
    from .collection_storage import CollectionStorage


class SyncRequestHandler(BaseHTTPRequestHandler):
    """Обработчик HTTP-запросов от расширения."""

    # Ссылка на сервер для доступа к storage
    server: "SyncHTTPServer"

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/sync":
            self._handle_sync()
        elif self.path == "/add":
            self._handle_add_single()
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/collection":
            self._handle_get_collection()
        else:
            self.send_error(404, "Not Found")

    def _handle_sync(self):
        """Принимает массив модов от расширения."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            mods = data.get("mods", [])

            storage = self.server.storage
            added = storage.add_mods_bulk(mods)

            # Уведомляем GUI
            self.server.sync_signal.data_received.emit(added)

            self._send_json(200, {
                "status": "ok",
                "added": added,
                "total": len(storage.get_all_mod_ids()),
            })
        except Exception as e:
            self._send_json(500, {"status": "error", "message": str(e)})

    def _handle_add_single(self):
        """Добавляет один мод."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            storage = self.server.storage
            success = storage.add_mod(data)

            if success:
                self.server.sync_signal.data_received.emit(1)

            self._send_json(200, {
                "status": "ok",
                "added": 1 if success else 0,
                "duplicate": not success,
            })
        except Exception as e:
            self._send_json(500, {"status": "error", "message": str(e)})

    def _handle_status(self):
        """Проверка статуса сервера."""
        self._send_json(200, {
            "status": "running",
            "plugin": "Nexus Mod Collector",
            "version": "1.0.0",
        })

    def _handle_get_collection(self):
        """Возвращает текущую коллекцию."""
        storage = self.server.storage
        self._send_json(200, {
            "status": "ok",
            "tree": storage.get_tree(),
        })

    def _send_json(self, code: int, data: dict):
        self.send_response(code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        """Подавляем стандартный вывод в консоль."""
        pass


class SyncSignal(QObject):
    """Qt-сигнал для передачи событий из потока сервера в GUI."""
    data_received = pyqtSignal(int)  # количество добавленных модов


class SyncHTTPServer(HTTPServer):
    """Расширенный HTTPServer с доступом к хранилищу."""

    def __init__(self, address, handler, storage, sync_signal):
        super().__init__(address, handler)
        self.storage: "CollectionStorage" = storage
        self.sync_signal: SyncSignal = sync_signal


class SyncServer:
    """Управляет жизненным циклом HTTP-сервера."""

    def __init__(self, port: int, storage: "CollectionStorage", organizer: "mobase.IOrganizer"):
        self._port = port
        self._storage = storage
        self._organizer = organizer
        self._server: SyncHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._sync_signal = SyncSignal()

    @property
    def signal(self) -> SyncSignal:
        return self._sync_signal

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        try:
            self._server = SyncHTTPServer(
                ("127.0.0.1", self._port),
                SyncRequestHandler,
                self._storage,
                self._sync_signal,
            )
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="NexusCollectorSyncServer",
            )
            self._thread.start()
        except OSError as e:
            # Порт уже занят
            print(f"[NexusCollector] Failed to start server on port {self._port}: {e}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def restart(self, new_port: int | None = None):
        self.stop()
        if new_port is not None:
            self._port = new_port
        self.start()
