import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import mobase
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QMainWindow,
    QMenu,
    QToolBar,
    QToolButton,
)


class ThemeSelector(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._toolbar_combo: Optional[QComboBox] = None
        self._retry_count = 0
        self._themes: List[Tuple[str, str]] = []
        self._stylesheets_dir: Optional[str] = None
        self._active_file: Optional[str] = None
        self._original_app_qss: str = ""
        self._original_captured = False

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        self._detect_stylesheets_dir()
        self._load_active_style()
        QTimer.singleShot(3000, self._setup_toolbar)
        return True

    def name(self) -> str:
        return "Theme Selector"

    def author(self) -> str:
        return "User"

    def description(self) -> str:
        return "Switch MO2 themes from the toolbar"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 4, 0)

    def settings(self):
        return [
            mobase.PluginSetting("last_theme", "Last selected theme file", ""),
        ]

    def displayName(self) -> str:
        return "Theme Selector"

    def tooltip(self) -> str:
        return "Switch MO2 theme"

    def icon(self) -> QIcon:
        return QIcon()

    def display(self):
        if self._toolbar_combo and self._toolbar_combo.isVisible():
            self._toolbar_combo.showPopup()
        else:
            self._setup_toolbar()

    # ------------------------------------------------------------------ #
    #  Toolbar setup
    # ------------------------------------------------------------------ #

    def _setup_toolbar(self) -> None:
        if self._toolbar_combo is not None:
            return

        mw = self._main_window()
        if not mw:
            self._retry()
            return

        self._capture_original_qss()

        target_toolbar = None
        for tb in mw.findChildren(QToolBar):
            for action in tb.actions():
                menu = self._find_menu(action, tb)
                if self._is_tools_menu(menu):
                    target_toolbar = tb
                    break
            if target_toolbar:
                break

        if not target_toolbar:
            toolbars = mw.findChildren(QToolBar)
            if toolbars:
                target_toolbar = toolbars[0]

        if not target_toolbar:
            self._retry()
            return

        self._create_widgets(target_toolbar)

    def _create_widgets(self, toolbar: QToolBar) -> None:
        if self._toolbar_combo is not None:
            return

        combo = QComboBox()
        combo.setObjectName("ThemeSelectorCombo")
        combo.setToolTip("Interface theme")
        combo.setMinimumWidth(200)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        font = combo.font()
        if font.pointSize() < 10:
            font.setPointSize(10)
        combo.setFont(font)

        self._toolbar_combo = combo

        self._populate_themes()

        self._toolbar_combo.currentIndexChanged.connect(self._on_theme_changed)

        # Просто добавляем в конец тулбара — он встанет правее всех
        toolbar.addWidget(self._toolbar_combo)
        self._toolbar_combo.show()

    # ------------------------------------------------------------------ #
    #  Theme discovery
    # ------------------------------------------------------------------ #

    def _populate_themes(self) -> None:
        if self._toolbar_combo is None:
            return

        if not self._stylesheets_dir or not os.path.isdir(self._stylesheets_dir):
            self._detect_stylesheets_dir()

        self._themes = self._discover_theme_files()

        self._toolbar_combo.blockSignals(True)
        self._toolbar_combo.clear()
        self._toolbar_combo.addItem("Default", "")

        selected_idx = 0
        for name, path in self._themes:
            display_name = name.replace(".qss", "").replace(".QSS", "")
            self._toolbar_combo.addItem(display_name, path)

            if self._active_file and self._paths_equal(path, self._active_file):
                selected_idx = self._toolbar_combo.count() - 1

        self._toolbar_combo.setCurrentIndex(selected_idx)
        self._toolbar_combo.blockSignals(False)

        # Автоматически применяем сохранённую тему при старте
        current_path = self._toolbar_combo.currentData()
        if isinstance(current_path, str) and current_path:
            self._apply_theme(current_path)

    def _discover_theme_files(self) -> List[Tuple[str, str]]:
        if not self._stylesheets_dir or not os.path.isdir(self._stylesheets_dir):
            return []

        candidates = []
        try:
            for entry in os.listdir(self._stylesheets_dir):
                if entry.lower().endswith(".qss"):
                    full_path = os.path.join(self._stylesheets_dir, entry)
                    if os.path.isfile(full_path):
                        candidates.append((entry, full_path))
        except Exception:
            return []

        candidates.sort(key=lambda x: x[0].lower())
        return candidates

    def _detect_stylesheets_dir(self) -> None:
        if self._organizer:
            try:
                base = Path(self._organizer.basePath())
                ss = base / "stylesheets"
                if ss.is_dir():
                    self._stylesheets_dir = str(ss)
                    return
            except Exception:
                pass

        try:
            exe_dir = Path(sys.executable).parent
            ss = exe_dir / "stylesheets"
            if ss.is_dir():
                self._stylesheets_dir = str(ss)
                return
        except Exception:
            pass

        self._stylesheets_dir = str(Path.cwd())

    # ------------------------------------------------------------------ #
    #  Theme application
    # ------------------------------------------------------------------ #

    def _on_theme_changed(self, index: int) -> None:
        if not self._toolbar_combo:
            return
        path = self._toolbar_combo.currentData()
        self._apply_theme(path)

    def _apply_theme(self, path: Optional[str]) -> None:
        app = QApplication.instance()
        if not app:
            return

        if not path:
            app.setStyleSheet(self._original_app_qss)
            self._active_file = None
            self._save_theme("")
            return

        if not os.path.exists(path):
            return

        qss = self._read_text_file(path)
        if qss is None:
            return

        qss = self._resolve_urls(qss, path)
        app.setStyleSheet(qss)
        self._active_file = path
        self._save_theme(path)

    def _resolve_urls(self, qss: str, qss_path: str) -> str:
        base_dir = os.path.dirname(os.path.abspath(qss_path))

        def _replace(match: re.Match) -> str:
            prefix = match.group(1)
            raw = match.group(3)

            if raw.startswith((":/", "qrc:", "data:", "http:", "https:")):
                return match.group(0)
            if os.path.isabs(raw):
                return match.group(0)

            absolute = os.path.normpath(os.path.join(base_dir, raw))
            absolute = absolute.replace("\\", "/")
            return f'{prefix}"{absolute}")'

        pattern = r"""(url\s*\(\s*)(["']?)([^"')]+)["']?\s*\)"""
        return re.sub(pattern, _replace, qss)

    # ------------------------------------------------------------------ #
    #  State management
    # ------------------------------------------------------------------ #

    def _capture_original_qss(self) -> None:
        if self._original_captured:
            return
        app = QApplication.instance()
        if app:
            self._original_app_qss = app.styleSheet()
            self._original_captured = True

    def _save_theme(self, theme_path: str) -> None:
        if self._organizer:
            try:
                self._organizer.setPluginSetting(self.name(), "last_theme", theme_path)
            except Exception:
                pass

    def _load_active_style(self) -> None:
        if not self._organizer:
            return
        try:
            saved = self._organizer.pluginSetting(self.name(), "last_theme")
            if saved and os.path.isfile(str(saved)):
                self._active_file = str(saved)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _read_text_file(path: str) -> Optional[str]:
        for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1251"):
            try:
                with open(path, "r", encoding=encoding) as f:
                    return f.read()
            except Exception:
                continue
        return None

    @staticmethod
    def _paths_equal(a: str, b: str) -> bool:
        try:
            return Path(a).resolve() == Path(b).resolve()
        except Exception:
            return False

    def _retry(self) -> None:
        self._retry_count += 1
        if self._retry_count < 10:
            delay = 2000 + self._retry_count * 500
            QTimer.singleShot(delay, self._setup_toolbar)

    @staticmethod
    def _main_window() -> Optional[QMainWindow]:
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMainWindow):
                return w
        return None

    @staticmethod
    def _find_menu(action, toolbar: QToolBar) -> Optional[QMenu]:
        menu = action.menu()
        if menu:
            return menu
        widget = toolbar.widgetForAction(action)
        if isinstance(widget, QToolButton):
            da = widget.defaultAction()
            if da:
                return da.menu()
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        return text.replace("&", "").replace("\u2014", "-").replace("\u2013", "-").strip().lower()

    def _is_tools_menu(self, menu: Optional[QMenu]) -> bool:
        if not menu:
            return False
        title = self._normalize_text(menu.title())
        if title in ("tool plugins", "плагины-программы", "tools"):
            return True
        target = self._normalize_text(self.displayName())
        for action in menu.actions():
            if self._normalize_text(action.text()) == target:
                return True
        return False


def createPlugin() -> ThemeSelector:
    return ThemeSelector()
