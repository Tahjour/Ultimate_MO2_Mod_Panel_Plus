from __future__ import annotations

from typing import Optional

import mobase
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMenu, QTreeView

from .dock import AdvancedSearchDock


class FullModSearchPlugin(mobase.IPlugin):
    def __init__(self) -> None:
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._mods_view: Optional[QTreeView] = None
        self._plugins_view: Optional[QTreeView] = None
        self._search_dialog = None
        self._dock: Optional[AdvancedSearchDock] = None
        self._main_window: Optional[QMainWindow] = None
        self._settings = QSettings("ModOrganizer2", "FullModSearchPlugin")
        self._toggle_shortcut: Optional[QShortcut] = None

    def name(self) -> str:
        return "UMP"

    def author(self) -> str:
        return "Enhanced Plugin Developer"

    def description(self) -> str:
        return (
            "UMP: unified search plugin for MO2 with tabs for mods, plugins, files, "
            "and NIF↔DDS texture search. Features: recent history, separator "
            "formatting, file content search, NIF texture indexing with caching. "
            "Hotkey: F1"
        )

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(4, 0, 0, mobase.ReleaseType.FINAL)

    def isActive(self) -> bool:
        return True

    def settings(self) -> list:
        return []

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        organizer.onUserInterfaceInitialized(self._setup)
        return True

    def _setup(self, main_window) -> None:
        for widget in QApplication.allWidgets():
            if not isinstance(widget, QTreeView):
                continue
            name = widget.objectName()
            if name == "modList":
                self._mods_view = widget
            elif name == "pluginList":
                self._plugins_view = widget
            elif name == "espList" and self._plugins_view is None:
                self._plugins_view = widget

        if isinstance(main_window, QMainWindow):
            self._main_window = main_window
            self._dock = AdvancedSearchDock(
                main_window,
                self._organizer,
                self._mods_view,
                self._plugins_view,
            )

            log_dock = self._find_log_dock(main_window)

            if log_dock:
                self._dock.set_log_dock(log_dock)
                area = main_window.dockWidgetArea(log_dock)
                if area == Qt.DockWidgetArea.NoDockWidgetArea:
                    area = Qt.DockWidgetArea.BottomDockWidgetArea
                main_window.addDockWidget(area, self._dock)
                main_window.splitDockWidget(
                    self._dock,
                    log_dock,
                    Qt.Orientation.Horizontal,
                )
            else:
                main_window.addDockWidget(
                    Qt.DockWidgetArea.BottomDockWidgetArea,
                    self._dock,
                )

            self._restore_main_window_state()

            view_menu = self._find_view_menu(main_window)
            if view_menu is not None:
                action = self._dock.toggleViewAction()
                if action not in view_menu.actions():
                    view_menu.addAction(action)

            self._install_toggle_shortcut()

        app = QApplication.instance()
        if app:
            setattr(app, "ump_find_nif_references", self.find_nif_references)
            app.aboutToQuit.connect(self._save_main_window_state)

    def _show_search(self) -> None:
        if self._dock:
            self._dock.setVisible(True)
            self._dock.raise_()
            self._dock.activateWindow()
            self._dock.focus_current_tab_search()

    def find_nif_references(self, texture_path: str) -> bool:
        if not self._dock:
            return False
        self._show_search()
        return bool(self._dock.find_nif_references(texture_path))

    def _toggle_dock(self) -> None:
        if not self._dock:
            return
        if self._dock.isVisible():
            self._dock.hide()
        else:
            self._show_search()

    def _install_toggle_shortcut(self) -> None:
        if not self._main_window:
            return
        if self._toggle_shortcut is not None:
            try:
                self._toggle_shortcut.activated.disconnect()
            except Exception:
                pass
        self._toggle_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_F1),
            self._main_window,
        )
        self._toggle_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._toggle_shortcut.activated.connect(self._show_search)

    def _save_main_window_state(self) -> None:
        if not isinstance(self._main_window, QMainWindow):
            return
        try:
            self._settings.setValue("MainWindow/state", self._main_window.saveState())
            self._settings.sync()
        except Exception:
            pass

    def _restore_main_window_state(self) -> None:
        if not isinstance(self._main_window, QMainWindow):
            return
        try:
            state = self._settings.value("MainWindow/state", None)
            if not state:
                return
            self._main_window.restoreState(state)
        except Exception:
            pass

    def _find_log_dock(self, window: QMainWindow) -> Optional[QDockWidget]:
        known_names = [
            "logDock",
            "LogDock",
            "logPanel",
            "logList",
            "LogList",
        ]

        for name in known_names:
            dock = window.findChild(QDockWidget, name)
            if dock:
                return dock

        all_docks = window.findChildren(QDockWidget)

        for dock in all_docks:
            obj_name = dock.objectName() or ""
            title = dock.windowTitle() or ""
            check = (obj_name + title).lower()
            if any(word in check for word in ["log", "лог", "message", "output"]):
                return dock

        for dock in all_docks:
            if not dock.isVisible():
                continue
            area = window.dockWidgetArea(dock)
            if area == Qt.DockWidgetArea.BottomDockWidgetArea:
                return dock

        return None

    def _find_view_menu(self, window: QMainWindow) -> Optional[QMenu]:
        menu_bar = window.menuBar()
        if menu_bar is None:
            return None

        candidates = []
        for action in menu_bar.actions():
            menu = action.menu()
            if menu is None:
                continue
            title = menu.title().replace("&", "").strip().lower()
            if title in {"view", "вид"}:
                return menu
            candidates.append(menu)

        for menu in candidates:
            title = menu.title().replace("&", "").strip().lower()
            if "view" in title or "вид" in title:
                return menu

        return None


__all__ = ["FullModSearchPlugin"]
