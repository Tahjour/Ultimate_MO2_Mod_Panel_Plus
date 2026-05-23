"""
Custom Tab Plugin for Mod Organizer 2 (2.5+, Qt6/PyQt6).
Добавляет вкладку «ESP Structure» в диалог свойств мода.
"""

print("!!! [ESP Structure Tab] Plugin file is being LOADED !!!")

import mobase
import os
import sys
import logging
import traceback
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTreeView,
    QHeaderView,
    QLineEdit,
    QProgressBar,
)

# ═══════════════════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.DEBUG)
_console.setFormatter(logging.Formatter("[ESP Structure Tab] %(levelname)s: %(message)s"))
if not logger.handlers:
    logger.addHandler(_console)

# ═══════════════════════════════════════════════════════════════════
#  Path setup
# ═══════════════════════════════════════════════════════════════════

plugin_file_path = os.path.abspath(__file__)
plugin_dir = os.path.dirname(plugin_file_path)
logger.info("Plugin directory: %s", plugin_dir)

esp_viewer_pkg_dir = None
if os.path.basename(plugin_dir) == "esp_viewer":
    esp_viewer_pkg_dir = os.path.dirname(plugin_dir)
elif os.path.isdir(os.path.join(plugin_dir, "esp_viewer")):
    esp_viewer_pkg_dir = plugin_dir

if esp_viewer_pkg_dir and esp_viewer_pkg_dir not in sys.path:
    sys.path.insert(0, esp_viewer_pkg_dir)
    logger.info("Added to sys.path: %s", esp_viewer_pkg_dir)

try:
    from esp_viewer.ui.esp_structure_loader import EspStructureLoader
    from esp_viewer.ui.esp_structure_tab import EspStructureTabPage
    logger.info("EspStructure components imported successfully.")
except ImportError as e:
    logger.error("FAILED to import EspStructure components: %s", e)
    EspStructureLoader = None
    EspStructureTabPage = None

# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════

_TAB_TITLE = "ESP Structure"
_PROPERTY_MARKER = "_espStructureTabInjected"
_MIN_EXISTING_TABS = 3
_LOADER_TIMEOUT_MS = 60_000          # 60 секунд на парсинг
_INJECT_DELAY_MS = 150               # задержка перед инъекцией
_RETRY_DELAY_MS = 300                # задержка между ретраями
_MAX_RETRIES = 5                     # макс. попыток инъекции
_ESP_EXTENSIONS = (".esp", ".esm", ".esl")

# ═══════════════════════════════════════════════════════════════════
#  Event-filter: инъекция вкладки в диалог свойств мода
# ═══════════════════════════════════════════════════════════════════

class _DialogWatcher(QObject):
    """Глобальный event-filter. Перехватывает открытие диалогов и
    ищет QTabWidget для инъекции вкладки ESP Structure."""

    def __init__(self, organizer: mobase.IOrganizer):
        super().__init__()
        self._organizer = organizer
        self._cache: Dict[str, Any] = {}
        # Множество id() диалогов, которые уже обработаны/в процессе
        self._seen_dialogs: set = set()
        # Список активных страниц, чтобы избежать garbage collection
        self._active_pages: List[Any] = []

    # ── Event filter ──────────────────────────────────────────────

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        try:
            if event.type() != QEvent.Type.Show:
                return False
            if not isinstance(obj, QDialog):
                return False
            if not _is_widget_alive(obj):
                return False

            dlg_id = id(obj)
            if dlg_id in self._seen_dialogs:
                return False

            # Помечаем СРАЗУ, чтобы избежать race condition
            self._seen_dialogs.add(dlg_id)

            # Убираем из множества когда диалог уничтожается
            obj.destroyed.connect(lambda _=None, d=dlg_id: self._seen_dialogs.discard(d))

            logger.debug("Dialog Show: '%s' (id=%d)", obj.windowTitle(), dlg_id)
            QTimer.singleShot(
                _INJECT_DELAY_MS,
                lambda dlg=obj: self._try_inject(dlg, attempt=1),
            )
        except Exception:
            logger.error("eventFilter error:\n%s", traceback.format_exc())

        return False

    # ── Injection logic ──────────────────────────────────────────

    def _try_inject(self, dialog: QDialog, attempt: int = 1) -> None:
        try:
            # Проверка: диалог ещё жив?
            if not _is_widget_alive(dialog):
                return

            # Уже инъецировали?
            if dialog.property(_PROPERTY_MARKER):
                return

            # Ищем QTabWidget
            tab_widget: Optional[QTabWidget] = dialog.findChild(QTabWidget)
            if tab_widget is None:
                if attempt < _MAX_RETRIES:
                    logger.debug(
                        "No QTabWidget in '%s', retry %d/%d",
                        dialog.windowTitle(), attempt, _MAX_RETRIES,
                    )
                    QTimer.singleShot(
                        _RETRY_DELAY_MS,
                        lambda dlg=dialog, a=attempt + 1: self._try_inject(dlg, a),
                    )
                return

            # Достаточно ли вкладок? (защита от чужих диалогов)
            if tab_widget.count() < _MIN_EXISTING_TABS:
                if attempt < _MAX_RETRIES:
                    logger.debug(
                        "Only %d tabs in '%s', retry %d/%d",
                        tab_widget.count(), dialog.windowTitle(),
                        attempt, _MAX_RETRIES,
                    )
                    QTimer.singleShot(
                        _RETRY_DELAY_MS,
                        lambda dlg=dialog, a=attempt + 1: self._try_inject(dlg, a),
                    )
                return

            # Дубликат?
            for idx in range(tab_widget.count()):
                if tab_widget.tabText(idx) == _TAB_TITLE:
                    dialog.setProperty(_PROPERTY_MARKER, True)
                    return

            # Определяем мод
            mod = self._resolve_mod(dialog)
            if mod is None:
                logger.debug("Could not resolve mod from '%s'", dialog.windowTitle())
                return

            # Инъекция
            logger.info("Injecting tab for mod '%s'", mod.name())
            page = EspStructureTabPage(mod, self._cache)
            
            # Важно: держим ссылку на страницу в Python, чтобы избежать GC
            self._active_pages.append(page)
            # Удаляем ссылку когда страница уничтожается
            page.destroyed.connect(lambda _=None, p=page: self._active_pages.remove(p))
            
            tab_widget.addTab(page, _TAB_TITLE)
            dialog.setProperty(_PROPERTY_MARKER, True)

        except Exception:
            logger.error("_try_inject error:\n%s", traceback.format_exc())

    # ── Mod resolution ────────────────────────────────────────────

    def _resolve_mod(self, dialog: QDialog) -> Optional[mobase.IModInterface]:
        title = dialog.windowTitle()
        if not title:
            return None

        # Извлекаем имя мода из заголовка
        # MO2 обычно: "Mod Name" или "Mod Name — something"
        mod_name = title.split(" — ")[0].split(" - ")[0].strip()

        mod_list = self._organizer.modList()
        mod = self._get_mod_by_name(mod_name, mod_list)
        if mod:
            return mod

        # Fuzzy: ищем имя мода, которое содержится в заголовке
        all_mods = mod_list.allMods()
        # Сортируем по длине (сначала длинные — точнее совпадение)
        for m_name in sorted(all_mods, key=len, reverse=True):
            if m_name in title:
                mod = self._get_mod_by_name(m_name, mod_list)
                if mod:
                    return mod

        return None

    def _get_mod_by_name(
        self, name: str, mod_list
    ) -> Optional[mobase.IModInterface]:
        """Пробуем несколько API, т.к. разные версии MO2 имеют разные методы."""
        try:
            if hasattr(mod_list, "getMod"):
                mod = mod_list.getMod(name)
                if mod:
                    return mod
        except Exception:
            pass

        try:
            if hasattr(self._organizer, "getMod"):
                mod = self._organizer.getMod(name)
                if mod:
                    return mod
        except Exception:
            pass

        try:
            if hasattr(self._organizer, "modDataContents"):
                # Проверяем существование мода
                if name in mod_list.allMods():
                    # Создаём proxy через modList
                    if hasattr(mod_list, "getMod"):
                        return mod_list.getMod(name)
        except Exception:
            pass

        return None


# ═══════════════════════════════════════════════════════════════════
#  Utilities
# ═══════════════════════════════════════════════════════════════════

def _is_widget_alive(widget: QWidget) -> bool:
    """Проверяет, что C++ объект виджета ещё существует."""
    try:
        # Попытка вызвать метод, чтобы проверить жив ли объект
        widget.objectName()
        return True
    except (RuntimeError, AttributeError):
        return False


# ═══════════════════════════════════════════════════════════════════
#  MO2 Plugin
# ═══════════════════════════════════════════════════════════════════

class CustomTabPlugin(mobase.IPlugin):
    """Плагин MO2: добавляет вкладку ESP Structure в окно свойств мода."""

    _NAME = "ESP Structure Tab"
    _AUTHOR = "Senior Developer"
    _VERSION = mobase.VersionInfo(1, 3, 0)
    _DESCRIPTION = (
        "Adds an 'ESP Structure' tab to the mod properties dialog, "
        "showing internal file paths referenced by .esp/.esm/.esl plugins."
    )

    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._watcher: Optional[_DialogWatcher] = None
        logger.info("CustomTabPlugin instance created.")

    def init(self, organizer: mobase.IOrganizer) -> bool:
        logger.info("init() called.")
        self._organizer = organizer

        self._watcher = _DialogWatcher(organizer)

        app = QApplication.instance()
        if app is None:
            logger.error("QApplication instance not found!")
            return False

        app.installEventFilter(self._watcher)
        logger.info("Event filter installed. Plugin ready.")
        return True

    # ── IPlugin interface ─────────────────────────────────────────

    def name(self) -> str:
        return self._NAME

    def author(self) -> str:
        return self._AUTHOR

    def version(self) -> mobase.VersionInfo:
        return self._VERSION

    def description(self) -> str:
        return self._DESCRIPTION

    def isActive(self) -> bool:
        return True

    def settings(self) -> List[mobase.PluginSetting]:
        return []


# ═══════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════

def createPlugin() -> mobase.IPlugin:
    logger.info("createPlugin() called.")
    return CustomTabPlugin()