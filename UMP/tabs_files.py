import os

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QSplitterHandle,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .workers import FileSearchWorker
from .archive_core import AssetSource, GAME_DATA_OWNER
from .preview_bridge import can_preview_virtual_path, preview_asset_source


class CollapsibleSplitter(QSplitter):
    def __init__(self, orientation: Qt.Orientation, parent: QWidget = None, collapsed_index: int = 0):
        super().__init__(orientation, parent)
        self._collapsed_index = collapsed_index
        self._expanded_sizes = None

    def createHandle(self) -> QSplitterHandle:
        return CollapsibleSplitterHandle(self.orientation(), self)

    def _toggle(self) -> None:
        if self.count() < 2:
            return
        sizes = self.sizes()
        if sizes[self._collapsed_index] <= self.collapsed_size():
            expanded = self._expanded_sizes or self._default_expanded_sizes()
            self.setSizes(expanded)
            return
        self._expanded_sizes = sizes
        collapsed = sizes[:]
        collapsed[self._collapsed_index] = self.collapsed_size()
        if sum(collapsed) == 0:
            for i in range(len(collapsed)):
                if i != self._collapsed_index:
                    collapsed[i] = 1
        self.setSizes(collapsed)

    def collapse(self) -> None:
        if self.count() < 2:
            return
        sizes = self.sizes()
        if sum(sizes) == 0:
            sizes = self._default_expanded_sizes()
        self._expanded_sizes = sizes
        collapsed = sizes[:]
        collapsed[self._collapsed_index] = self.collapsed_size()
        if sum(collapsed) == 0:
            for i in range(len(collapsed)):
                if i != self._collapsed_index:
                    collapsed[i] = 1
        self.setSizes(collapsed)

    def collapsed_size(self) -> int:
        size = self.handleWidth()
        if size <= 0:
            size = 8
        return max(size, 8)

    def _default_expanded_sizes(self) -> list[int]:
        sizes = []
        for i in range(self.count()):
            widget = self.widget(i)
            if widget is None:
                sizes.append(1)
                continue
            hint = widget.sizeHint()
            sizes.append(hint.height() if self.orientation() == Qt.Orientation.Vertical else hint.width())
        if sum(sizes) <= 0:
            sizes = [1] * self.count()
        return sizes


class CollapsibleSplitterHandle(QSplitterHandle):
    def mousePressEvent(self, event):
        splitter = self.splitter()
        if isinstance(splitter, CollapsibleSplitter):
            splitter._toggle()
        super().mousePressEvent(event)


class FileSearchTab(QWidget):
    """Tab for searching mods by file content"""

    SETTINGS_KEY = "FullModSearch"
    MAX_RECENT_ITEMS = 10

    EXTENSION_PRESETS = {
        "All Files": [],
        "Meshes (.nif)": [".nif"],
        "Textures (.dds)": [".dds"],
        "Textures (All)": [".dds", ".png", ".tga", ".bmp", ".jpg", ".jpeg"],
        "Scripts (.pex, .psc)": [".pex", ".psc"],
        "Plugins (.esp, .esm, .esl)": [".esp", ".esm", ".esl"],
        "Sound (.wav, .xwm, .fuz)": [".wav", ".xwm", ".fuz", ".lip"],
        "Animations (.hkx)": [".hkx"],
        "Config (.ini, .json, .xml)": [".ini", ".json", ".xml", ".toml", ".yaml", ".cfg"],
        "Archives (.bsa, .ba2)": [".bsa", ".ba2"],
    }

    file_selected = pyqtSignal(str)
    include_bsas_changed = pyqtSignal(bool)

    def __init__(self, parent, organizer: "mobase.IOrganizer", mods_view: "QTreeView"):
        super().__init__(parent)
        self._organizer = organizer
        self._mods_view = mods_view
        self._mod_list = organizer.modList()
        self._search_worker: FileSearchWorker = None
        self.settings = QSettings("ModOrganizer2", "FullModSearchPlugin")

        self._setup_ui()
        self._load_recent_searches()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        search_group = QGroupBox("Search Options", self)
        search_group.setFlat(True)
        search_layout = QVBoxLayout(search_group)
        search_layout.setContentsMargins(4, 2, 4, 2)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("File Name:"))

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Enter file name to search (supports wildcards: *, ?)")
        self.search_input.setClearButtonEnabled(True)
        name_layout.addWidget(self.search_input)

        search_layout.addLayout(name_layout)

        ext_layout = QHBoxLayout()
        ext_layout.addWidget(QLabel("File Type:"))

        self.extension_combo = QComboBox(self)
        for preset_name in self.EXTENSION_PRESETS.keys():
            self.extension_combo.addItem(preset_name)
        ext_layout.addWidget(self.extension_combo)

        self.custom_ext_input = QLineEdit(self)
        self.custom_ext_input.setPlaceholderText("Custom extensions (e.g., .nif, .dds)")
        self.custom_ext_input.setMaximumWidth(200)
        ext_layout.addWidget(self.custom_ext_input)

        ext_layout.addStretch()
        search_layout.addLayout(ext_layout)

        btn_layout = QHBoxLayout()

        self.search_btn = QPushButton("Search", self)
        btn_layout.addWidget(self.search_btn)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_btn)

        self.clear_btn = QPushButton("Clear Results", self)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()

        self.include_bsas_cb = QCheckBox("Include BSAs (all mods + game data)", self)
        self.include_bsas_cb.setChecked(
            self.settings.value(f"{self.SETTINGS_KEY}/IncludeBSAs", False, type=bool)
        )
        btn_layout.addWidget(self.include_bsas_cb)

        self.active_mods_only_cb = QCheckBox("Active Mods Only", self)
        btn_layout.addWidget(self.active_mods_only_cb)
        self._apply_scope_controls()

        search_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        search_layout.addWidget(self.progress_bar)

        layout.addWidget(search_group)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.results_tree = QTreeWidget(self)
        self.results_tree.setHeaderLabels(["Mod / File Path", "Source", "Container / Full Path"])
        self.results_tree.setColumnWidth(0, 400)
        self.results_tree.setColumnWidth(1, 120)
        self.results_tree.setAlternatingRowColors(True)
        self.results_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._set_rows_height(self.results_tree, 20, fixed=True)
        results_layout.addWidget(self.results_tree)

        info_layout = QHBoxLayout()
        self.results_label = QLabel("No results", self)
        info_layout.addWidget(self.results_label)

        info_layout.addStretch()

        self.goto_mod_btn = QPushButton("Go to Mod", self)
        self.goto_mod_btn.setEnabled(False)
        info_layout.addWidget(self.goto_mod_btn)

        self.preview_btn = QPushButton("Preview", self)
        self.preview_btn.setEnabled(False)
        info_layout.addWidget(self.preview_btn)

        self.open_folder_btn = QPushButton("Open Folder", self)
        self.open_folder_btn.setEnabled(False)
        info_layout.addWidget(self.open_folder_btn)

        results_layout.addLayout(info_layout)

        splitter.addWidget(results_group)

        recent_group = QGroupBox("Recent Searches", self)
        recent_group.setFlat(True)
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(4, 2, 4, 2)

        self.recent_list = QListWidget(self)
        self.recent_list.setAlternatingRowColors(True)
        recent_layout.addWidget(self.recent_list)

        clear_recent_btn = QPushButton("Clear History", self)
        clear_recent_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_recent_btn)

        splitter.addWidget(recent_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _set_rows_height(self, view, rows: int, fixed: bool) -> int:
        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = view.fontMetrics().height() + 6
        height = row_height * rows + view.frameWidth() * 2
        header = getattr(view, "header", None)
        if callable(header):
            h = header()
            if h is not None:
                height += h.height()
        if fixed:
            view.setMinimumHeight(height)
            view.setMaximumHeight(height)
        else:
            view.setMinimumHeight(0)
            view.setMaximumHeight(height)
        return height

    def _connect_signals(self):
        self.search_btn.clicked.connect(self._start_search)
        self.cancel_btn.clicked.connect(self._cancel_search)
        self.clear_btn.clicked.connect(self._clear_results)

        self.search_input.returnPressed.connect(self._start_search)

        self.results_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self.goto_mod_btn.clicked.connect(self._goto_selected_mod)
        self.preview_btn.clicked.connect(self._preview_selected_file)
        self.open_folder_btn.clicked.connect(self._open_selected_folder)

        self.recent_list.itemDoubleClicked.connect(self._on_recent_clicked)
        self.include_bsas_cb.toggled.connect(self._on_include_bsas_toggled)

    def _apply_scope_controls(self):
        exhaustive = self.include_bsas_cb.isChecked()
        self.active_mods_only_cb.setEnabled(not exhaustive)
        self.active_mods_only_cb.setToolTip(
            "Include BSAs searches all installed mods and game data."
            if exhaustive
            else ""
        )

    def _on_include_bsas_toggled(self, checked: bool):
        self.settings.setValue(f"{self.SETTINGS_KEY}/IncludeBSAs", checked)
        self.settings.sync()
        self._apply_scope_controls()
        self.include_bsas_changed.emit(checked)

    def set_include_bsas(self, checked: bool):
        if self.include_bsas_cb.isChecked() != checked:
            self.include_bsas_cb.setChecked(checked)
        else:
            self._apply_scope_controls()

    def _load_recent_searches(self):
        self.recent_searches = self.settings.value(f"{self.SETTINGS_KEY}/RecentFileSearches", [], type=list)
        self._update_recent_list()

    def _save_recent_searches(self):
        self.settings.setValue(f"{self.SETTINGS_KEY}/RecentFileSearches", self.recent_searches)
        self.settings.sync()

    def _update_recent_list(self):
        self.recent_list.clear()
        for search in self.recent_searches:
            self.recent_list.addItem(search)

    def _add_to_recent(self, search_text: str):
        if search_text in self.recent_searches:
            self.recent_searches.remove(search_text)

        self.recent_searches.insert(0, search_text)
        self.recent_searches = self.recent_searches[:self.MAX_RECENT_ITEMS]

        self._save_recent_searches()
        self._update_recent_list()

    def _clear_recent(self):
        self.recent_searches = []
        self._save_recent_searches()
        self._update_recent_list()
        self.file_selected.emit("Recent history cleared")

    def _get_selected_extensions(self):
        preset_name = self.extension_combo.currentText()
        extensions = list(self.EXTENSION_PRESETS.get(preset_name, []))

        custom_text = self.custom_ext_input.text().strip()
        if custom_text:
            for ext in custom_text.split(","):
                ext = ext.strip().lower()
                if ext and not ext.startswith("."):
                    ext = "." + ext
                if ext and ext not in extensions:
                    extensions.append(ext)

        return extensions

    def _start_search(self):
        search_text = self.search_input.text().strip()

        if not search_text:
            QMessageBox.warning(self, "Search", "Please enter a file name to search.")
            return

        if len(search_text) < 2:
            QMessageBox.warning(self, "Search", "Please enter at least 2 characters.")
            return

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait()

        self._clear_results()
        self._add_to_recent(search_text)

        extensions = self._get_selected_extensions()

        self.search_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.file_selected.emit("Searching...")

        self._search_results = {}

        self._search_worker = FileSearchWorker(
            self._organizer,
            search_text,
            extensions,
            search_in_bsa=self.include_bsas_cb.isChecked(),
            only_active=self.active_mods_only_cb.isChecked() and not self.include_bsas_cb.isChecked(),
        )

        self._search_worker.progress.connect(self._on_search_progress)
        self._search_worker.results_batch.connect(self._on_results_batch)
        self._search_worker.finished_search.connect(self._on_search_finished)
        self._search_worker.warning.connect(self._on_search_warning)

        self._search_worker.start()

    def _cancel_search(self):
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self.file_selected.emit("Search cancelled")

    def _clear_results(self):
        self.results_tree.clear()
        self._search_results = {}
        self._result_items = {}
        self._result_file_count = 0
        self.results_label.setText("No results")
        self.goto_mod_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)

    def _on_search_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.file_selected.emit(f"Searching... ({current}/{total} assets)")
        else:
            self.progress_bar.setMaximum(0)
            self.file_selected.emit(f"Searching... ({current} assets)")

    def _on_results_batch(self, sources: list[AssetSource]):
        self.results_tree.setUpdatesEnabled(False)
        try:
            for source in sources:
                self._on_result_found(source)
        finally:
            self.results_tree.setUpdatesEnabled(True)

    def _on_result_found(self, source: AssetSource):
        if source.owner not in self._search_results:
            self._search_results[source.owner] = []
            mod_item = QTreeWidgetItem([source.owner, "", ""])
            font = QFont()
            font.setBold(True)
            mod_item.setFont(0, font)
            mod_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "mod", "name": source.owner})
            self.results_tree.addTopLevelItem(mod_item)
            self._result_items[source.owner] = mod_item

        self._search_results[source.owner].append(source)
        source_label = source.archive_name or "Loose file"
        file_item = QTreeWidgetItem(
            [source.virtual_path, source_label, source.location_text]
        )
        file_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "file",
            "source": source,
        })
        self._result_items[source.owner].addChild(file_item)
        self._result_file_count += 1
        self.results_label.setText(
            f"{self._result_file_count} files in {len(self._search_results)} sources"
        )

    def _on_search_warning(self, message: str):
        self.file_selected.emit(f"Archive warning: {message}")

    def _on_search_finished(self, total_results: int):
        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

        mod_count = len(self._search_results)
        self.file_selected.emit(f"Search complete: {total_results} files in {mod_count} sources")

        if mod_count <= 20:
            self.results_tree.expandAll()

    def _on_selection_changed(self):
        items = self.results_tree.selectedItems()
        if not items:
            self.goto_mod_btn.setEnabled(False)
            self.preview_btn.setEnabled(False)
            self.open_folder_btn.setEnabled(False)
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole) or {}
        source = data.get("source")
        owner = source.owner if source else data.get("name")
        self.goto_mod_btn.setEnabled(bool(owner and owner != GAME_DATA_OWNER))
        self.preview_btn.setEnabled(bool(source and can_preview_virtual_path(source.virtual_path)))
        self.open_folder_btn.setEnabled(True)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "mod":
            if data["name"] != GAME_DATA_OWNER:
                self._goto_mod(data["name"])
        else:
            self._preview_source(data["source"])

    def _goto_selected_mod(self):
        items = self.results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        source = data.get("source")
        mod_name = data.get("name") or (source.owner if source else None)
        if mod_name and mod_name != GAME_DATA_OWNER:
            self._goto_mod(mod_name)

    def _goto_mod(self, mod_name: str):
        if not self._mods_view or not self._mods_view.model():
            self.file_selected.emit("Error: Mods view not available")
            return

        display_name = self._mod_list.displayName(mod_name)
        model = self._mods_view.model()

        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            display_name,
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )

        if not matches:
            matches = model.match(
                model.index(0, 0),
                Qt.ItemDataRole.DisplayRole,
                display_name,
                1,
                Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive,
            )

        if matches:
            index = matches[0]
            parent = index.parent()

            if parent.isValid():
                self._mods_view.expand(parent)

            self._mods_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            self._mods_view.setCurrentIndex(index)
            self._mods_view.setFocus()

            self.file_selected.emit(f"Selected: {display_name}")
        else:
            self.file_selected.emit(f"Could not find mod: {display_name}")

    def _preview_selected_file(self):
        items = self.results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "file":
            return

        self._preview_source(data["source"])

    def _preview_source(self, source: AssetSource):
        if preview_asset_source(self, source, self._organizer):
            self.file_selected.emit(f"Preview: {source.virtual_path}")

    def _open_selected_folder(self):
        items = self.results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "file":
            source = data["source"]
            target_path = source.navigation_path
            folder_path = os.path.dirname(target_path)
        else:
            target_path = ""
            if data["name"] == GAME_DATA_OWNER:
                return
            mod_info = self._mod_list.getMod(data["name"])
            if mod_info:
                folder_path = mod_info.absolutePath()
            else:
                return

        if os.path.exists(folder_path):
            import subprocess
            import sys

            if sys.platform == "win32":
                if target_path and os.path.exists(target_path):
                    subprocess.run(["explorer", "/select,", target_path])
                else:
                    os.startfile(folder_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

            self.file_selected.emit(f"Opened: {folder_path}")
        else:
            self.file_selected.emit(f"Folder not found: {folder_path}")

    def _on_recent_clicked(self, item: QListWidgetItem):
        self.search_input.setText(item.text())
        self._start_search()

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def refresh_if_needed(self):
        self.set_include_bsas(
            self.settings.value(f"{self.SETTINGS_KEY}/IncludeBSAs", False, type=bool)
        )

    def handle_key_press(self, key: int) -> bool:
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.search_input.hasFocus():
                self._start_search()
                return True
        elif key == Qt.Key.Key_Down and self.search_input.hasFocus():
            self.results_tree.setFocus()
            if self.results_tree.topLevelItemCount() > 0:
                self.results_tree.setCurrentItem(self.results_tree.topLevelItem(0))
            return True
        return False


__all__ = ["FileSearchTab"]
