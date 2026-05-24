from __future__ import annotations

from typing import Optional

import mobase
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .tabs import FileSearchTab, ModNameSearchTab, NifTextureSearchTab, PluginSearchTab


class UnifiedSearchDialog(QDialog):
    def __init__(
        self,
        parent,
        organizer: mobase.IOrganizer,
        mods_view: QTreeView,
        plugins_view: QTreeView,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MO2 Advanced Search")
        self.setMinimumSize(750, 600)
        self.resize(900, 700)

        self._organizer = organizer
        self._mods_view = mods_view
        self._plugins_view = plugins_view
        self._first_show = True

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.tab_widget = QTabWidget(self)

        self.mod_search_tab: Optional[QWidget] = None
        if self._mods_view:
            self.mod_search_tab = ModNameSearchTab(
                self,
                self._mods_view,
                self._organizer.modList(),
            )
            self.tab_widget.addTab(self.mod_search_tab, "🔍 Mods")

        self.plugin_search_tab: Optional[QWidget] = None
        if self._plugins_view:
            self.plugin_search_tab = PluginSearchTab(
                self,
                self._plugins_view,
                self._organizer.pluginList(),
            )
            self.tab_widget.addTab(self.plugin_search_tab, "📦 Plugins")

        self.file_search_tab: Optional[QWidget] = None
        if self._mods_view:
            self.file_search_tab = FileSearchTab(
                self,
                self._organizer,
                self._mods_view,
            )
            self.tab_widget.addTab(self.file_search_tab, "📁 Files")

        self.nif_texture_tab: Optional[QWidget] = None
        if self._mods_view:
            self.nif_texture_tab = NifTextureSearchTab(
                self,
                self._organizer,
                self._mods_view,
            )
            self.tab_widget.addTab(self.nif_texture_tab, "🔗 NIF ↔ DDS")

        layout.addWidget(self.tab_widget)

        self.status_label = QLabel(
            "F1 to open | Tabs: Mods, Plugins, Files, NIF↔DDS | Escape to close",
            self,
        )
        layout.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        if self.mod_search_tab:
            self.mod_search_tab.mod_selected.connect(self._update_status)
        if self.plugin_search_tab:
            self.plugin_search_tab.plugin_selected.connect(self._update_status)
        if self.file_search_tab:
            self.file_search_tab.file_selected.connect(self._update_status)
        if self.nif_texture_tab:
            self.nif_texture_tab.status_changed.connect(self._update_status)

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _update_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.setWindowTitle(f"UMP  {message}")

    def _on_tab_changed(self, index: int) -> None:
        current_widget = self.tab_widget.currentWidget()
        if current_widget and hasattr(current_widget, "refresh_if_needed"):
            current_widget.refresh_if_needed()
        if current_widget and hasattr(current_widget, "focus_search"):
            current_widget.focus_search()


__all__ = ["UnifiedSearchDialog"]
