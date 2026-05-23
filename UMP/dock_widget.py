from __future__ import annotations

from typing import Optional

import mobase
from PyQt6.QtCore import Qt, QSettings, QTimer, QEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QScrollArea,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .tabs import FileSearchTab, ModNameSearchTab, ModNotesSearchTab, NifTextureSearchTab, PluginSearchTab, ContentFilterTab
from .esp_search_tab import EspFieldSearchTab
from .bookmarks_tab import BookmarksTab


class AdvancedSearchDock(QDockWidget):
    _S_PREFIX = "AdvancedSearchDock"
    _S_FLOATING = f"{_S_PREFIX}/floating"
    _S_VISIBLE = f"{_S_PREFIX}/visible"
    _S_GEOMETRY = f"{_S_PREFIX}/geometry"
    _S_WIDTH = f"{_S_PREFIX}/width"
    _S_HEIGHT = f"{_S_PREFIX}/height"
    _S_AREA = f"{_S_PREFIX}/area"
    _S_LOG_WIDTH = f"{_S_PREFIX}/log_width"
    _S_LOG_HEIGHT = f"{_S_PREFIX}/log_height"
    _S_LOG_NAME = f"{_S_PREFIX}/log_name"
    _S_ORIENTATION = f"{_S_PREFIX}/split_orientation"
    _S_INITIALIZED = f"{_S_PREFIX}/initialized"
    _S_TAB_INDEX = f"{_S_PREFIX}/tab_index"

    def __init__(
        self,
        parent: QMainWindow,
        organizer: mobase.IOrganizer,
        mods_view: QTreeView,
        plugins_view: QTreeView,
    ) -> None:
        super().__init__("UMP - created by Alhimik", parent)
        self._organizer = organizer
        self._mods_view = mods_view
        self._plugins_view = plugins_view
        self._settings = QSettings("ModOrganizer2", "FullModSearchPlugin")
        self._tab_objects: list[QWidget] = []
        self._main_window = parent
        self._log_dock: Optional[QDockWidget] = None
        self._restore_attempts = 0
        self._state_saved = False
        self._expanded = True
        self._collapsed_height = 28
        self._saved_height = 300

        self.topLevelChanged.connect(self._on_top_level_changed)
        self.visibilityChanged.connect(self._on_visibility_changed)
        QTimer.singleShot(0, self._install_title_click_handler)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        self.tab_widget = QTabWidget(container)
        self.tab_widget.setDocumentMode(True)

        self.mod_search_tab: Optional[QWidget] = None
        if self._mods_view:
            self.mod_search_tab = ModNameSearchTab(
                container,
                self._mods_view,
                self._organizer.modList(),
            )
            self._add_tab(self.mod_search_tab, "🔍 Mods")

        self.plugin_search_tab: Optional[QWidget] = None
        if self._plugins_view:
            self.plugin_search_tab = PluginSearchTab(
                container,
                self._plugins_view,
                self._organizer.pluginList(),
            )
            self._add_tab(self.plugin_search_tab, "🔍 Plugins")

        self.mod_notes_tab: Optional[QWidget] = None
        if self._mods_view:
            self.mod_notes_tab = ModNotesSearchTab(
                container,
                self._organizer,
                self._mods_view,
                self._organizer.modList(),
            )
            self._add_tab(self.mod_notes_tab, "📝 Notes/Desc")

        self.file_search_tab: Optional[QWidget] = None
        if self._mods_view:
            self.file_search_tab = FileSearchTab(
                container,
                self._organizer,
                self._mods_view,
            )
            self._add_tab(self.file_search_tab, "🔍 Files")

        self.esp_field_search_tab: Optional[QWidget] = None
        if self._mods_view:
            self.esp_field_search_tab = EspFieldSearchTab(
                container,
                self._organizer,
                self._mods_view,
            )
            self._add_tab(self.esp_field_search_tab, "🔍 ESP Fields")

        self.nif_texture_tab: Optional[QWidget] = None
        if self._mods_view:
            self.nif_texture_tab = NifTextureSearchTab(
                container,
                self._organizer,
                self._mods_view,
            )
            self._add_tab(self.nif_texture_tab, "🔍 NIF ↔ DDS")

        self.content_filter_tab: Optional[QWidget] = None
        if self._mods_view:
            self.content_filter_tab = ContentFilterTab(
                container,
                self._organizer,
                self._mods_view,
            )
            self._add_tab(self.content_filter_tab, "🧹 Content Filter")

        self.bookmarks_tab: Optional[QWidget] = None
        if self._mods_view and self._organizer:
            self.bookmarks_tab = BookmarksTab(
                container,
                self._mods_view,
                self._organizer,
                self._plugins_view,
            )
            self._add_tab(self.bookmarks_tab, "🔖 Bookmarks")

        layout.addWidget(self.tab_widget)
        container.setLayout(layout)
        self.setWidget(container)
        self.setObjectName("fullModSearchDock")

        if self.mod_search_tab:
            self.mod_search_tab.mod_selected.connect(self._update_status)
        if self.plugin_search_tab:
            self.plugin_search_tab.plugin_selected.connect(self._update_status)
        if self.file_search_tab:
            self.file_search_tab.file_selected.connect(self._update_status)
        if self.esp_field_search_tab:
            self.esp_field_search_tab.search_status.connect(self._update_status)
        if self.nif_texture_tab:
            self.nif_texture_tab.status_changed.connect(self._update_status)

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        if self.mod_search_tab:
            self.mod_search_tab.load_mods()
        if self.plugin_search_tab:
            self.plugin_search_tab.load_plugins()

        saved_tab = self._settings.value(self._S_TAB_INDEX, 0, type=int)
        if 0 <= saved_tab < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(saved_tab)

        current_tab = self._get_current_tab()
        if current_tab and hasattr(current_tab, "focus_search"):
            current_tab.focus_search()

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._save_state)

    def _add_tab(self, tab: QWidget, title: str) -> None:
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(tab)
        self._tab_objects.append(tab)
        self.tab_widget.addTab(scroll_area, title)

    def _get_current_tab(self) -> Optional[QWidget]:
        index = self.tab_widget.currentIndex()
        if 0 <= index < len(self._tab_objects):
            return self._tab_objects[index]
        return None

    def set_log_dock(self, log_dock: Optional[QDockWidget]) -> None:
        self._log_dock = log_dock

    def _save_state(self) -> None:
        if self._state_saved:
            return
        self._state_saved = True

        try:
            self._settings.setValue(self._S_FLOATING, self.isFloating())
            self._settings.setValue(self._S_VISIBLE, self.isVisible())
            self._settings.setValue(self._S_TAB_INDEX, self.tab_widget.currentIndex())

            if self.isFloating():
                self._settings.setValue(self._S_GEOMETRY, self.saveGeometry())
            else:
                w = self.width()
                h = self.height()
                if w > 50 and h > 50:
                    self._settings.setValue(self._S_WIDTH, w)
                    self._settings.setValue(self._S_HEIGHT, h)

                if self._main_window:
                    area = int(self._main_window.dockWidgetArea(self))
                    self._settings.setValue(self._S_AREA, area)

                if self._log_dock and self._log_dock.isVisible():
                    lw = self._log_dock.width()
                    lh = self._log_dock.height()
                    if lw > 50 and lh > 50:
                        self._settings.setValue(self._S_LOG_WIDTH, lw)
                        self._settings.setValue(self._S_LOG_HEIGHT, lh)
                    self._settings.setValue(
                        self._S_LOG_NAME,
                        self._log_dock.objectName(),
                    )

                    dg = self.geometry()
                    lg = self._log_dock.geometry()
                    horiz = abs(dg.x() - lg.x()) >= abs(dg.y() - lg.y())
                    self._settings.setValue(
                        self._S_ORIENTATION,
                        int(
                            Qt.Orientation.Horizontal
                            if horiz
                            else Qt.Orientation.Vertical
                        ),
                    )

            self._settings.setValue(self._S_INITIALIZED, True)
            self._settings.sync()
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._state_saved = False
        self._save_state()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        if not self._state_saved:
            self._state_saved = False
            self._save_state()
        super().hideEvent(event)

    def _update_status(self, message: str) -> None:
        self.setWindowTitle("UMP")

    def _on_tab_changed(self, index: int) -> None:
        current_tab = self._get_current_tab()
        if current_tab and hasattr(current_tab, "refresh_if_needed"):
            current_tab.refresh_if_needed()
        if current_tab and hasattr(current_tab, "focus_search"):
            current_tab.focus_search()

    def focus_current_tab_search(self) -> None:
        current_tab = self._get_current_tab()
        if current_tab and hasattr(current_tab, "focus_search"):
            current_tab.focus_search()

    def _install_title_click_handler(self) -> None:
        bar = self.titleBarWidget()
        if bar is not None:
            bar.installEventFilter(self)

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self.titleBarWidget() and event.type() == QEvent.Type.MouseButtonRelease:
            self._toggle_panel()
            return True
        return super().eventFilter(obj, event)

    def _toggle_panel(self) -> None:
        if self.isFloating():
            return
        if self._expanded:
            self._collapse_panel()
        else:
            self._expand_panel()

    def _collapse_panel(self) -> None:
        self._expanded = False
        h = self.height()
        if h > self._collapsed_height:
            self._saved_height = h
        self.setMinimumHeight(self._collapsed_height)
        self.setMaximumHeight(self._collapsed_height)
        try:
            self.resize(self.width(), self._collapsed_height)
        except Exception:
            pass

    def _expand_panel(self) -> None:
        self._expanded = True
        self.setMaximumHeight(16777215)
        target = max(self._saved_height, self._collapsed_height * 2)
        self.setMinimumHeight(self._collapsed_height)
        try:
            self.resize(self.width(), target)
        except Exception:
            pass

    def _on_top_level_changed(self, floating: bool) -> None:
        if floating and not self._expanded:
            self._expand_panel()

    def _on_visibility_changed(self, visible: bool) -> None:
        if visible and not self.isFloating() and not self._expanded:
            self._collapse_panel()


__all__ = ["AdvancedSearchDock"]
