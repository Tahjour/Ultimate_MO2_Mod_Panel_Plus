from __future__ import annotations

from typing import List

import mobase
from PyQt6.QtCore import Qt, QSettings, QModelIndex, QEvent, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QMenu,
)


class BookmarksTab(QWidget):
    def __init__(
        self,
        parent: QWidget,
        mods_view: QTreeView,
        organizer: mobase.IOrganizer,
        plugins_view: QTreeView | None = None,
    ) -> None:
        super().__init__(parent)
        self._mods_view = mods_view
        self._plugins_view = plugins_view
        self._organizer = organizer
        self._settings = QSettings("QuickModBookmarks", "MO2Plugin")
        self._bookmarks: List[str] = []
        self._plugin_settings = QSettings("QuickPluginBookmarks", "MO2Plugin")
        self._plugin_bookmarks: List[str] = []

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(4)
        self._main_layout.setContentsMargins(4, 4, 4, 4)

        info = QLabel(
            "Bookmarks: Select a mod or plugin in the panels and use the corresponding "
            "Save button or context menu to store it. Double click - go to item"
        )
        info.setWordWrap(True)
        self._main_layout.addWidget(info)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(4)

        self._controls_container = QWidget(self)
        controls_layout = QVBoxLayout(self._controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

        self._save_button = QPushButton("Save", self._controls_container)
        self._save_button.clicked.connect(self._on_save_clicked)
        controls_layout.addWidget(self._save_button)

        self._clear_button = QPushButton("Clear", self._controls_container)
        self._clear_button.clicked.connect(self._on_clear_clicked)
        controls_layout.addWidget(self._clear_button)

        self._clear_all_button = QPushButton("Clear All", self._controls_container)
        self._clear_all_button.clicked.connect(self._on_clear_all_clicked)
        controls_layout.addWidget(self._clear_all_button)

        controls_layout.addStretch(1)

        content_layout.addWidget(self._controls_container)

        self._bookmarks_view = QTreeWidget(self)
        self._bookmarks_view.setHeaderHidden(True)
        self._bookmarks_view.setRootIsDecorated(False)
        self._bookmarks_view.setAlternatingRowColors(True)
        self._bookmarks_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._bookmarks_view.itemActivated.connect(self._on_bookmark_activated)

        content_layout.addWidget(self._bookmarks_view, 1)

        self._plugin_controls_container = QWidget(self)
        plugin_controls_layout = QVBoxLayout(self._plugin_controls_container)
        plugin_controls_layout.setContentsMargins(0, 0, 0, 0)
        plugin_controls_layout.setSpacing(4)

        self._plugin_save_button = QPushButton("Save", self._plugin_controls_container)
        self._plugin_save_button.clicked.connect(self._on_plugin_save_clicked)
        plugin_controls_layout.addWidget(self._plugin_save_button)

        self._plugin_clear_button = QPushButton("Clear", self._plugin_controls_container)
        self._plugin_clear_button.clicked.connect(self._on_plugin_clear_clicked)
        plugin_controls_layout.addWidget(self._plugin_clear_button)

        self._plugin_clear_all_button = QPushButton("Clear All", self._plugin_controls_container)
        self._plugin_clear_all_button.clicked.connect(self._on_plugin_clear_all_clicked)
        plugin_controls_layout.addWidget(self._plugin_clear_all_button)

        plugin_controls_layout.addStretch(1)

        content_layout.addWidget(self._plugin_controls_container)

        self._plugin_bookmarks_view = QTreeWidget(self)
        self._plugin_bookmarks_view.setHeaderHidden(True)
        self._plugin_bookmarks_view.setRootIsDecorated(False)
        self._plugin_bookmarks_view.setAlternatingRowColors(True)
        self._plugin_bookmarks_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._plugin_bookmarks_view.itemActivated.connect(self._on_plugin_bookmark_activated)

        content_layout.addWidget(self._plugin_bookmarks_view, 1)

        self._main_layout.addLayout(content_layout)
        self._main_layout.addStretch(1)

        self._load_bookmarks()
        self._rebuild_view()
        self._load_plugin_bookmarks()
        self._rebuild_plugin_view()

        if self._mods_view is not None and self._mods_view.selectionModel() is not None:
            self._mods_view.selectionModel().currentChanged.connect(self._on_mod_current_changed)

        if self._plugins_view is not None and self._plugins_view.selectionModel() is not None:
            self._plugins_view.selectionModel().currentChanged.connect(self._on_plugin_current_changed)

        if self._mods_view is not None:
            self._mods_view.viewport().installEventFilter(self)
        if self._plugins_view is not None:
            self._plugins_view.viewport().installEventFilter(self)

    def _rebuild_view(self) -> None:
        self._bookmarks_view.clear()

        if not self._organizer:
            return

        mod_list = self._organizer.modList()
        for internal_name in self._bookmarks:
            try:
                display_name = mod_list.displayName(internal_name)
            except Exception:
                display_name = internal_name

            item = QTreeWidgetItem([display_name])
            item.setData(0, Qt.ItemDataRole.UserRole, internal_name)
            self._bookmarks_view.addTopLevelItem(item)

    def _resolve_mod_internal_from_index(self, index: QModelIndex) -> str | None:
        if not self._mods_view or not self._organizer:
            return None

        if not index.isValid():
            return None

        model = self._mods_view.model()
        if model is None:
            return None

        name_index = model.index(index.row(), 0, index.parent())
        display_name = name_index.data(Qt.ItemDataRole.DisplayRole)
        if not display_name:
            return None

        mod_list = self._organizer.modList()
        try:
            all_mods = mod_list.allMods()
        except Exception:
            all_mods = []

        for internal in all_mods:
            try:
                if mod_list.displayName(internal) == display_name:
                    return internal
            except Exception:
                continue

        return None

    def _on_save_clicked(self) -> None:
        if not self._mods_view or not self._organizer:
            return

        current_index = self._mods_view.currentIndex()
        if not current_index.isValid():
            QMessageBox.information(self, "Quick Bookmarks", "No mod selected.")
            return

        internal_name = self._resolve_mod_internal_from_index(current_index)
        if not internal_name:
            QMessageBox.warning(self, "Quick Bookmarks", "Could not resolve selected mod.")
            return

        if internal_name in self._bookmarks:
            self._focus_bookmark(internal_name)
            return

        self._bookmarks.append(internal_name)
        self._persist_bookmarks()
        self._rebuild_view()
        self._focus_bookmark(internal_name)

    def _on_clear_clicked(self) -> None:
        current_item = self._bookmarks_view.currentItem()
        if current_item is None:
            return

        internal_name = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not internal_name:
            return

        try:
            self._bookmarks.remove(internal_name)
        except ValueError:
            return

        self._persist_bookmarks()
        self._rebuild_view()

    def _on_clear_all_clicked(self) -> None:
        if not self._bookmarks:
            return

        self._bookmarks.clear()
        self._persist_bookmarks()
        self._rebuild_view()

    def _on_bookmark_activated(self, item: QTreeWidgetItem) -> None:
        internal_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not internal_name:
            return
        self._scroll_to_mod(str(internal_name))

    def _on_mod_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        internal_name = self._resolve_mod_internal_from_index(current)
        if not internal_name:
            return
        self._focus_bookmark(internal_name)

    def _focus_bookmark(self, internal_name: str) -> None:
        count = self._bookmarks_view.topLevelItemCount()
        for i in range(count):
            item = self._bookmarks_view.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == internal_name:
                self._bookmarks_view.setCurrentItem(item)
                self._bookmarks_view.scrollToItem(item)
                break

    def _rebuild_plugin_view(self) -> None:
        self._plugin_bookmarks_view.clear()

        if not self._organizer:
            return

        for plugin_name in self._plugin_bookmarks:
            item = QTreeWidgetItem([plugin_name])
            item.setData(0, Qt.ItemDataRole.UserRole, plugin_name)
            self._plugin_bookmarks_view.addTopLevelItem(item)

    def _resolve_plugin_from_index(self, index: QModelIndex) -> str | None:
        if not self._plugins_view or not self._organizer:
            return None

        if not index.isValid():
            return None

        model = self._plugins_view.model()
        if model is None:
            return None

        name_index = model.index(index.row(), 0, index.parent())
        display_name = name_index.data(Qt.ItemDataRole.DisplayRole)
        if not display_name:
            return None

        return str(display_name)

    def _on_plugin_save_clicked(self) -> None:
        if not self._plugins_view or not self._organizer:
            return

        current_index = self._plugins_view.currentIndex()
        if not current_index.isValid():
            QMessageBox.information(self, "Quick Bookmarks", "No plugin selected.")
            return

        plugin_name = self._resolve_plugin_from_index(current_index)
        if not plugin_name:
            QMessageBox.warning(self, "Quick Bookmarks", "Could not resolve selected plugin.")
            return

        if plugin_name in self._plugin_bookmarks:
            self._focus_plugin_bookmark(plugin_name)
            return

        self._plugin_bookmarks.append(plugin_name)
        self._persist_plugin_bookmarks()
        self._rebuild_plugin_view()
        self._focus_plugin_bookmark(plugin_name)

    def _on_plugin_clear_clicked(self) -> None:
        current_item = self._plugin_bookmarks_view.currentItem()
        if current_item is None:
            return

        plugin_name = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not plugin_name:
            return

        try:
            self._plugin_bookmarks.remove(plugin_name)
        except ValueError:
            return

        self._persist_plugin_bookmarks()
        self._rebuild_plugin_view()

    def _on_plugin_clear_all_clicked(self) -> None:
        if not self._plugin_bookmarks:
            return

        self._plugin_bookmarks.clear()
        self._persist_plugin_bookmarks()
        self._rebuild_plugin_view()

    def _on_plugin_bookmark_activated(self, item: QTreeWidgetItem) -> None:
        plugin_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not plugin_name:
            return
        self._scroll_to_plugin(str(plugin_name))

    def _on_plugin_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        plugin_name = self._resolve_plugin_from_index(current)
        if not plugin_name:
            return
        self._focus_plugin_bookmark(plugin_name)

    def _focus_plugin_bookmark(self, plugin_name: str) -> None:
        count = self._plugin_bookmarks_view.topLevelItemCount()
        for i in range(count):
            item = self._plugin_bookmarks_view.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == plugin_name:
                self._plugin_bookmarks_view.setCurrentItem(item)
                self._plugin_bookmarks_view.scrollToItem(item)
                break

    def eventFilter(self, obj, event):
        mods_viewport = None
        plugins_viewport = None

        if self._mods_view is not None:
            try:
                mods_viewport = self._mods_view.viewport()
            except RuntimeError:
                self._mods_view = None

        if self._plugins_view is not None:
            try:
                plugins_viewport = self._plugins_view.viewport()
            except RuntimeError:
                self._plugins_view = None

        if mods_viewport is not None and obj is mods_viewport:
            if event.type() == QEvent.Type.ContextMenu:
                QTimer.singleShot(0, self._inject_bookmark_menu_action)
        elif plugins_viewport is not None and obj is plugins_viewport:
            if event.type() == QEvent.Type.ContextMenu:
                QTimer.singleShot(0, self._inject_plugin_bookmark_menu_action)
        return super().eventFilter(obj, event)

    def _inject_bookmark_menu_action(self) -> None:
        app = QApplication.instance()
        if app is None:
            return

        menu = app.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(50, self._inject_bookmark_menu_action)
            return

        for action in menu.actions():
            if action.objectName() == "ump_add_bookmark_action":
                return

        action = menu.addAction("Add bookmark")
        action.setObjectName("ump_add_bookmark_action")
        action.triggered.connect(self._on_save_clicked)

    def _inject_plugin_bookmark_menu_action(self) -> None:
        app = QApplication.instance()
        if app is None:
            return

        menu = app.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(50, self._inject_plugin_bookmark_menu_action)
            return

        for action in menu.actions():
            if action.objectName() == "ump_add_plugin_bookmark_action":
                return

        action = menu.addAction("Add plugin bookmark")
        action.setObjectName("ump_add_plugin_bookmark_action")
        action.triggered.connect(self._on_plugin_save_clicked)

    def _scroll_to_mod(self, mod_internal_name: str) -> None:
        if not self._mods_view or not self._organizer:
            return

        model = self._mods_view.model()
        if model is None:
            return

        mod_list = self._organizer.modList()
        try:
            display_name = mod_list.displayName(mod_internal_name)
        except Exception:
            display_name = mod_internal_name

        index = self._find_mod_index(model, display_name)
        if index and index.isValid():
            self._expand_parents(index)
            self._mods_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
            self._mods_view.setCurrentIndex(index)
            self._mods_view.setFocus()

    def _find_mod_index(self, model, display_name: str, parent: QModelIndex | None = None) -> QModelIndex:
        if parent is None:
            parent = QModelIndex()

        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            item_name = index.data(Qt.ItemDataRole.DisplayRole)
            if item_name and str(item_name).lower() == display_name.lower():
                return index
            if model.hasChildren(index):
                child = self._find_mod_index(model, display_name, index)
                if child.isValid():
                    return child

        return QModelIndex()

    def _expand_parents(self, index: QModelIndex) -> None:
        if not index.isValid():
            return

        parents = []
        current = index.parent()
        while current.isValid():
            parents.append(current)
            current = current.parent()

        for parent in reversed(parents):
            if not self._mods_view.isExpanded(parent):
                self._mods_view.expand(parent)

    def _scroll_to_plugin(self, plugin_name: str) -> None:
        if not self._plugins_view:
            return

        model = self._plugins_view.model()
        if model is None:
            return

        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            plugin_name,
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )

        if matches:
            index = matches[0]
            self._plugins_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            self._plugins_view.setCurrentIndex(index)
            self._plugins_view.setFocus()

    def _load_bookmarks(self) -> None:
        if self._settings is None:
            return

        self._bookmarks.clear()
        size = self._settings.beginReadArray("bookmarks")
        for i in range(size):
            self._settings.setArrayIndex(i)
            mod_name = self._settings.value("mod_name", type=str)
            if mod_name:
                self._bookmarks.append(str(mod_name))
        self._settings.endArray()

    def _load_plugin_bookmarks(self) -> None:
        if self._plugin_settings is None:
            return

        self._plugin_bookmarks.clear()
        size = self._plugin_settings.beginReadArray("bookmarks")
        for i in range(size):
            self._plugin_settings.setArrayIndex(i)
            plugin_name = self._plugin_settings.value("plugin_name", type=str)
            if plugin_name:
                self._plugin_bookmarks.append(str(plugin_name))
        self._plugin_settings.endArray()

    def _persist_bookmarks(self) -> None:
        if self._settings is None:
            return

        self._settings.beginWriteArray("bookmarks", len(self._bookmarks))
        for index, mod_name in enumerate(self._bookmarks):
            self._settings.setArrayIndex(index)
            self._settings.setValue("slot", index + 1)
            self._settings.setValue("mod_name", mod_name)
        self._settings.endArray()
        self._settings.sync()

    def _persist_plugin_bookmarks(self) -> None:
        if self._plugin_settings is None:
            return

        self._plugin_settings.beginWriteArray("bookmarks", len(self._plugin_bookmarks))
        for index, plugin_name in enumerate(self._plugin_bookmarks):
            self._plugin_settings.setArrayIndex(index)
            self._plugin_settings.setValue("slot", index + 1)
            self._plugin_settings.setValue("plugin_name", plugin_name)
        self._plugin_settings.endArray()
        self._plugin_settings.sync()


__all__ = ["BookmarksTab"]
