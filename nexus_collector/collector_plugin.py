"""
Nexus Mod Collector — MO2 Plugin (IPluginTool)
Принимает моды от браузерного расширения и позволяет
управлять коллекцией прямо из MO2.
"""

import mobase
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QSize, Qt, QTimer, QPoint
from PyQt6.QtGui import QIcon, QPainter, QColor
from PyQt6.QtWidgets import QMessageBox, QToolButton, QToolBar, QMainWindow, QApplication

from .sync_server import SyncServer
from .collection_storage import CollectionStorage
from .collection_window import CollectionWindow


class NexusCollectorPlugin(mobase.IPluginTool):
    """
    Основной класс плагина. Регистрируется в MO2 как инструмент
    (появляется в меню Tools и на панели инструментов).
    """

    NAME = "Nexus Mod Collector"
    AUTHOR = "NexusCollector"
    VERSION = mobase.VersionInfo(1, 0, 0, 0)
    DESCRIPTION = "Collect mods from Nexus via browser extension and manage them in MO2"

    def __init__(self):
        super().__init__()
        self._organizer: mobase.IOrganizer | None = None
        self._sync_server: SyncServer | None = None
        self._storage: CollectionStorage | None = None
        self._window: CollectionWindow | None = None
        self._parent_widget = None
        self._toolbar_button: QToolButton | None = None
        self._tools_menu = None
        self._retry_count = 0

    # ──────────────────── IPlugin interface ────────────────────

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer

        # Путь для хранения данных коллекции в папке самого плагина
        plugin_path = Path(__file__).parent.absolute()
        storage_path = plugin_path / "data"
        storage_path.mkdir(parents=True, exist_ok=True)

        # Инициализация хранилища
        self._storage = CollectionStorage(storage_path / "collection.json")

        # Запуск HTTP-сервера для приёма данных от расширения
        self._sync_server = SyncServer(
            port=6555,
            storage=self._storage,
            organizer=self._organizer,
        )
        self._sync_server.start()

        # Настройка кнопки в тулбаре через небольшую задержку
        QTimer.singleShot(3000, self._setup_toolbar)

        return True

    def _setup_toolbar(self):
        """Настройка кнопки в тулбаре MO2."""
        mw = self._main_window()
        if not mw:
            self._retry()
            return

        for tb in mw.findChildren(QToolBar):
            actions_list = tb.actions()

            for action in actions_list:
                menu = self._find_menu(action, tb)
                if self._is_tools_menu(menu):
                    self._tools_menu = menu

                    btn = QToolButton(tb)
                    btn.setToolTip(self.tooltip())
                    btn.setAutoRaise(True)
                    btn.setIcon(self.icon())
                    btn.setIconSize(QSize(30, 30))
                    btn.clicked.connect(self.display)

                    # Вставляем перед Tools
                    tb.insertWidget(action, btn)

                    self._toolbar_button = btn
                    self._hide_self_from_menu()
                    return

        self._retry()

    def _retry(self):
        self._retry_count += 1
        if self._retry_count < 5:
            QTimer.singleShot(2000, self._setup_toolbar)

    def _find_menu(self, toolbar_action, toolbar):
        menu = toolbar_action.menu()
        if menu:
            return menu
        widget = toolbar.widgetForAction(toolbar_action)
        if isinstance(widget, QToolButton):
            da = widget.defaultAction()
            if da:
                menu = da.menu()
                if menu:
                    return menu
        return None

    def _normalize_text(self, text):
        return text.replace("&", "").replace("—", "-").replace("–", "-").strip().lower()

    def _menu_title_matches(self, menu):
        title = self._normalize_text(menu.title())
        return title in ("tool plugins", "плагины-программы")

    def _menu_has_plugin_action(self, menu):
        target = self._normalize_text(self.displayName())
        for a in menu.actions():
            if self._normalize_text(a.text()) == target:
                return True
        return False

    def _is_tools_menu(self, menu):
        if not menu:
            return False
        return self._menu_title_matches(menu) or self._menu_has_plugin_action(menu)

    def _hide_self_from_menu(self):
        if not self._tools_menu:
            return

        def _do_hide():
            for a in self._tools_menu.actions():
                if a.text().replace("&", "") == self.displayName():
                    a.setVisible(False)
                    break

        _do_hide()
        self._tools_menu.aboutToShow.connect(_do_hide)

    def _main_window(self) -> QMainWindow | None:
        """Получение главного окна MO2."""
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMainWindow):
                return widget
        return None

    def name(self) -> str:
        return self.NAME

    def author(self) -> str:
        return self.AUTHOR

    def description(self) -> str:
        return self.DESCRIPTION

    def version(self) -> mobase.VersionInfo:
        return self.VERSION

    def settings(self) -> list[mobase.PluginSetting]:
        """
        Настройки плагина, доступные через MO2 Settings → Plugins.
        """
        return [
            mobase.PluginSetting(
                "server_port",
                "HTTP server port for browser extension sync",
                6555,
            ),
            mobase.PluginSetting(
                "auto_start_server",
                "Automatically start sync server on MO2 launch",
                True,
            ),
            mobase.PluginSetting(
                "nexus_api_key",
                "Nexus Mods API key (leave empty to use MO2 key)",
                "",
            ),
        ]

    def isActive(self) -> bool:
        return bool(self._organizer)

    # ──────────────────── IPluginTool interface ────────────────────

    def displayName(self) -> str:
        return self.NAME

    def tooltip(self) -> str:
        return "Open Nexus Mod Collector — manage your wishlisted mods"

    def icon(self) -> QIcon:
        # Попытка загрузить иконку из ресурсов плагина
        icon_path = Path(__file__).parent / "resources" / "icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        
        # Генерация иконки на лету, если файл не найден
        pixmap = QIcon().pixmap(QSize(32, 32))
        if pixmap.isNull():
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor("transparent"))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor("#da70d6")) # Orchid color
            painter.setPen(QColor("#ffffff"))
            painter.drawEllipse(2, 2, 28, 28)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "NC")
            painter.end()
        return QIcon(pixmap)

    def setParentWidget(self, widget):
        self._parent_widget = widget

    def display(self):
        """
        Вызывается при нажатии на кнопку плагина в MO2.
        Открывает главное окно коллекции в режиме flyout.
        """
        if not self._organizer:
            return

        mw = self._main_window()
        if not mw:
            return

        # Toggle: если окно видимо — скрываем
        if self._window is not None and self._window.isVisible():
            self._window.hide()
            return

        # Создаём при первом вызове
        if self._window is None:
            # Получение API ключа Nexus
            api_key = self._get_nexus_api_key()
            
            self._window = CollectionWindow(
                parent=mw,
                storage=self._storage,
                organizer=self._organizer,
                api_key=api_key,
                sync_server=self._sync_server,
            )
            # Устанавливаем флаги для flyout-панели
            self._window.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )

        # Позиционирование под кнопкой (логика из flyout.py)
        anchor = self._toolbar_button or mw
        if isinstance(anchor, QToolButton):
            # Маппим локальные координаты кнопки в глобальные
            global_pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        else:
            global_pos = mw.mapToGlobal(QPoint(0, 0))

        self._window.move(global_pos)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    # ──────────────────── Helpers ────────────────────

    def _get_nexus_api_key(self) -> str:
        """
        Получение Nexus API ключа.
        Приоритет:
            1. Сохраненный ключ в JSON коллекции (storage.get_api_key)
            2. Настройка плагина nexus_api_key (MO2 Plugin Settings)
            3. Ключ из настроек MO2 (NexusModsPlugin)
        """
        # 1. Сначала проверяем наше хранилище (JSON)
        if self._storage:
            json_key = self._storage.get_api_key()
            if json_key:
                return json_key

        # 2. Собственная настройка плагина MO2
        custom_key = self._organizer.pluginSetting(self.NAME, "nexus_api_key")
        if custom_key:
            return str(custom_key)

        # 3. Попытка получить ключ из встроенного Nexus-плагина MO2
        for plugin_name in ["NexusModsPlugin", "Nexus"]:
            try:
                key = self._organizer.pluginSetting(plugin_name, "api_key")
                if key:
                    return str(key)
            except Exception:
                continue

        return ""

    def __del__(self):
        """Корректное завершение сервера при уничтожении плагина."""
        if self._sync_server:
            self._sync_server.stop()
