"""
ESP/ESL/ESM Viewer for Mod Organizer 2.
Based on ModFilesTab logic.
"""

import mobase
import os
import sys
import logging
import traceback
from collections import Counter
from pathlib import Path
from typing import List, Optional, Set

# Совместимость Qt5 / Qt6
try:
    from PyQt6.QtCore import Qt, QSize, QCoreApplication
    from PyQt6.QtGui import QFont, QAction
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout
    _RICH_TEXT = Qt.TextFormat.RichText
    _NO_WRAP = QTextEdit.LineWrapMode.NoWrap
    _MONOSPACE = QFont.StyleHint.Monospace
except ImportError:
    from PyQt5.QtCore import Qt, QSize, QCoreApplication
    from PyQt5.QtGui import QFont, QAction
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout
    _RICH_TEXT = Qt.RichText
    _NO_WRAP = QTextEdit.NoWrap
    _MONOSPACE = QFont.Monospace

# Настройка логирования
logger = logging.getLogger(__name__)

# Добавляем родительскую директорию в sys.path, чтобы 'import esp_viewer' работал
plugin_dir = Path(__file__).parent.absolute()
parent_dir = plugin_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Импортируем внутренние модули
try:
    from .core.plugin_file import parse_plugin
    from .core.search_engine import iter_records
    from .formatting.record_formatter import StructuredSubrecordParser
    from .ui.main_window import MainWindow, PluginViewerWidget
except ImportError as e:
    logger.error(f"Failed to import internal modules: {e}")
    # В случае ошибки импорта при первом запуске (когда пакет еще не в sys.path)
    # Попробуем импортировать через абсолютное имя, если мы уже в системе
    try:
        from esp_viewer.core.plugin_file import parse_plugin
        from esp_viewer.core.search_engine import iter_records
        from esp_viewer.formatting.record_formatter import StructuredSubrecordParser
        from esp_viewer.ui.main_window import MainWindow
    except ImportError:
        logger.error("Double import failure")

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QTabWidget, QWidget

def _is_widget_alive(widget: QWidget) -> bool:
    """Проверяет, что C++ объект виджета ещё существует."""
    try:
        # Попытка вызвать любой метод, чтобы проверить жив ли объект
        widget.objectName()
        return True
    except (RuntimeError, AttributeError):
        return False

class DialogWatcher(QObject):
    """Специальный QObject для отслеживания открытия окон свойств мода."""
    _TAB_TITLE = "ESP Structure"
    _PROPERTY_MARKER = "_espStructureTabInjected"
    _MIN_EXISTING_TABS = 3

    def __init__(self, organizer: mobase.IOrganizer, cache: dict):
        super().__init__()
        self._organizer = organizer
        self._cache = cache
        self._active_pages: List[Any] = []

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(obj, QDialog):
            if _is_widget_alive(obj) and not obj.property(self._PROPERTY_MARKER):
                # Небольшая задержка, чтобы MO2 успел наполнить окно вкладками
                QTimer.singleShot(150, lambda dlg=obj: self._try_inject_tab(dlg))
        return False

    def _try_inject_tab(self, dialog: QDialog) -> None:
        if not _is_widget_alive(dialog):
            return

        if dialog.property(self._PROPERTY_MARKER):
            return

        # Ищем виджет вкладок
        tab_widget = dialog.findChild(QTabWidget)
        if not tab_widget:
            # Если не нашли сразу, попробуем еще пару раз
            if not hasattr(dialog, "_retry_count"): dialog._retry_count = 0
            if dialog._retry_count < 3:
                dialog._retry_count += 1
                QTimer.singleShot(200, lambda dlg=dialog: self._try_inject_tab(dlg))
            return

        # Проверка на минимальное количество вкладок
        if tab_widget.count() < self._MIN_EXISTING_TABS:
            if not hasattr(dialog, "_retry_count"): dialog._retry_count = 0
            if dialog._retry_count < 3:
                dialog._retry_count += 1
                QTimer.singleShot(300, lambda dlg=dialog: self._try_inject_tab(dlg))
            return

        # Проверяем, не добавлена ли вкладка уже
        for idx in range(tab_widget.count()):
            if tab_widget.tabText(idx) == self._TAB_TITLE:
                dialog.setProperty(self._PROPERTY_MARKER, True)
                return

        # Пытаемся определить имя мода по заголовку окна
        title = dialog.windowTitle()
        if not title:
            QTimer.singleShot(200, lambda dlg=dialog: self._try_inject_tab(dlg))
            return

        mod_name = title.split(" - ")[0].split(" — ")[0].strip()
        mod = self._organizer.modList().getMod(mod_name)
        
        if not mod:
            all_mods = self._organizer.modList().allMods()
            for m_name in all_mods:
                if m_name == title or title.startswith(m_name + " "):
                    mod = self._organizer.modList().getMod(m_name)
                    break
        
        if not mod:
            return

        logger.info(f"!!! [ESP Viewer] Found mod '{mod.name()}' for dialog '{title}'")
        logger.info(f"!!! [ESP Viewer] Injecting structure tab...")
        
        try:
            from .ui.esp_structure_tab import EspStructureTabPage
            page = EspStructureTabPage(mod, self._cache, self._organizer)
            
            # ВАЖНО: сохраняем ссылку на страницу, чтобы Python не удалил её и её сигналы!
            self._active_pages.append(page)
            # При уничтожении виджета (закрытии окна) удаляем его из списка активных
            page.destroyed.connect(lambda _=None, p=page: self._active_pages.remove(p) if p in self._active_pages else None)
            
            tab_widget.addTab(page, self._TAB_TITLE)
            dialog.setProperty(self._PROPERTY_MARKER, True)
        except Exception as e:
            logger.error(f"Failed to inject tab: {e}")
            traceback.print_exc()

class ESPViewerPlugin(mobase.IPluginPreview):
    NAME = "ESP Viewer"
    
    def __init__(self):
        mobase.IPluginPreview.__init__(self)
        self._organizer = None
        self._main_window = None
        self._cache = {}
        self._watcher = None
        print("!!! [ESP Viewer] Plugin instance created.")

    def init(self, organizer: mobase.IOrganizer):
        self._organizer = organizer
        
        # Интеграция вкладки в свойства мода через отдельный QObject
        app = QApplication.instance()
        if app:
            self._watcher = DialogWatcher(self._organizer, self._cache)
            app.installEventFilter(self._watcher)
            print("!!! [ESP Viewer] Event filter installed successfully.")
        
        return True

    def name(self):
        return self.NAME

    def author(self):
        return "ModFilesTab Team"

    def version(self):
        return mobase.VersionInfo(1, 1, 0)

    def description(self):
        return "Advanced ESP/ESL/ESM plugin viewer with record analysis"

    def settings(self):
        return [
            mobase.PluginSetting("enabled", "Enable esp_viewer preview plugin", True),
            mobase.PluginSetting(
                "pythonPath",
                "Python executable with PyQt6 (for external viewer)",
                "python",
            ),
        ]

    def preview(self, filename: str):
        """
        Открывает полноценное окно вьювера как отдельный процесс.
        Это позволяет избежать блокировки интерфейса MO2 и обеспечивает стабильность.
        """
        root = os.path.dirname(__file__)
        script = os.path.join(root, "main.py")
        python = self._organizer.pluginSetting(self.name(), "pythonPath") or "python"
        
        try:
            import subprocess
            # CREATE_NO_WINDOW для Windows, чтобы не мелькала консоль
            creationflags = 0
            if sys.platform == "win32":
                creationflags = 0x08000000 # CREATE_NO_WINDOW
            
            subprocess.Popen(
                [python, script, filename],
                creationflags=creationflags,
                cwd=root # Важно для корректных импортов в main.py
            )
        except Exception as e:
            logger.error(f"Failed to launch external viewer: {e}")
            # Если не удалось запустить внешне, попробуем внутри (fallback)
            self._open_full_viewer(filename)
        
        return None

    def supportedExtensions(self):
        return {"esp", "esl", "esm"}

    def genFilePreview(self, filename: str, max_size: QSize):
        """
        Генерирует виджет предварительного просмотра.
        Теперь использует PluginViewerWidget напрямую.
        """
        try:
            viewer = PluginViewerWidget()
            viewer.load_plugin(filename)
            return viewer
        except Exception as e:
            logger.error(f"Failed to create embedded viewer: {e}")
            traceback.print_exc()
            return self._gen_simple_preview(filename)

    def _gen_simple_preview(self, filename: str):
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        layout.setContentsMargins(4, 4, 4, 4)
        
        btn_open = QPushButton("Open Full Viewer")
        btn_open.clicked.connect(lambda: self._open_full_viewer(filename))
        layout.addWidget(btn_open)

        try:
            path = Path(filename)
            plugin = parse_plugin(str(path))
            
            sig_counts = Counter()
            total_records = 0
            full_names = set()
            asset_paths = set()
            form_ids = set()

            # Анализ записей (ограничим для превью, если файл огромный, 
            # но parse_plugin обычно быстрый, так как он ленивый)
            for record in iter_records(plugin.children):
                sig_counts[record.signature] += 1
                total_records += 1
                form_ids.add(record.form_id)
                if record.full_name:
                    full_names.add(record.full_name)
                
                # Поиск путей к ассетам (как в ModFilesTab)
                try:
                    # Для превью ограничим глубокий парсинг ассетов, если записей слишком много
                    if total_records < 5000: 
                        parser = StructuredSubrecordParser(record, plugin)
                        for node in parser.iter_nodes():
                            value = getattr(node, "value", None)
                            if not value or not isinstance(value, str):
                                continue
                            if not ("/" in value or "\\" in value):
                                continue
                            lower = value.lower()
                            if lower.endswith((".nif", ".dds", ".wav", ".xwm", ".hkx", ".pex")):
                                asset_paths.add(value)
                except Exception:
                    pass

            # Формирование текстового отчета
            lines = []
            lines.append(f"<b>File:</b> {path.name}")
            lines.append(f"<b>ESL:</b> {'Yes' if plugin.is_esl else 'No'}")
            lines.append(f"<b>Localized:</b> {'Yes' if plugin.localized else 'No'}")
            
            if plugin.masters:
                lines.append("<br><b>Masters:</b>")
                for name in plugin.masters[:15]:
                    lines.append(f"  - {name}")
                if len(plugin.masters) > 15:
                    lines.append(f"  ... and {len(plugin.masters) - 15} more")

            lines.append(f"<br><b>Total Records:</b> {total_records}")
            
            if form_ids:
                lines.append(f"<b>Unique FormIDs:</b> {len(form_ids)}")
                lines.append(f"<b>FormID Range:</b> 0x{min(form_ids):08X} - 0x{max(form_ids):08X}")

            if sig_counts:
                lines.append("<br><b>Top Record Types:</b>")
                for sig, count in sorted(sig_counts.items(), key=lambda x: -x[1])[:15]:
                    lines.append(f"  {sig}: {count}")

            if asset_paths:
                lines.append("<br><b>Referenced Assets (first 20):</b>")
                for asset in sorted(list(asset_paths))[:20]:
                    lines.append(f"  {asset}")
                if len(asset_paths) > 20:
                    lines.append(f"  ... and {len(asset_paths) - 20} more")

            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setHtml("<br>".join(lines))
            
            font = QFont("Consolas", 10)
            font.setStyleHint(_MONOSPACE)
            text_edit.setFont(font)
            text_edit.setLineWrapMode(_NO_WRAP)
            
            layout.addWidget(text_edit)

        except Exception as e:
            err_label = QLabel(f"Error parsing plugin: {e}")
            err_label.setStyleSheet("color: red;")
            layout.addWidget(err_label)
            logger.error(traceback.format_exc())

        return widget

    def _open_full_viewer(self, filename: str):
        """Открывает полноценное окно вьювера."""
        try:
            if self._main_window is None:
                self._main_window = MainWindow()
            
            self._main_window.show()
            self._main_window.raise_()
            self._main_window.activateWindow()
            self._main_window.load_plugin(filename)
        except Exception as e:
            logger.error(f"Failed to open full viewer: {e}")
            traceback.print_exc()

def createPlugin():
    return ESPViewerPlugin()
