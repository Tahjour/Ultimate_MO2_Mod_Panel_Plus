import os
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSplitter,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .nif_core import NifTextureEntry, NifTextureIndex, NifIndexWorker
from .archive_core import AssetCatalog, build_index_scope


class NifTextureSearchTab(QWidget):
    """
    Вкладка поиска NIF ↔ DDS.
    Автоматически индексирует при первом открытии, кэширует между сессиями.
    """

    SETTINGS_KEY = "FullModSearch"

    status_changed = pyqtSignal(str)
    goto_mod = pyqtSignal(str)
    include_bsas_changed = pyqtSignal(bool)

    def __init__(self, parent, organizer: "mobase.IOrganizer", mods_view: "QTreeView"):
        super().__init__(parent)
        self._organizer = organizer
        self._mods_view = mods_view
        self._mod_list = organizer.modList()

        cache_dir = Path(organizer.basePath()) / "cache" / "nif_texture_index"
        self._index = NifTextureIndex(cache_dir)

        self._index_worker: NifIndexWorker = None
        self._first_activation = True
        self._is_indexing = False
        self._pending_scope_rebuild = False
        self._asset_catalog: AssetCatalog = None

        self.settings = QSettings("ModOrganizer2", "FullModSearchPlugin")

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        top_frame = QGroupBox("Index Status")
        top_frame.setFlat(True)
        top_layout = QVBoxLayout(top_frame)
        top_layout.setSpacing(2)
        top_layout.setContentsMargins(4, 2, 4, 2)

        status_row = QHBoxLayout()

        self._index_icon = QLabel("⏳")
        self._index_icon.setFixedWidth(24)
        status_row.addWidget(self._index_icon)

        self._index_status = QLabel("Index not loaded")
        status_row.addWidget(self._index_status)

        status_row.addStretch()

        self._rebuild_btn = QPushButton("🔄 Rebuild Index")
        self._rebuild_btn.setToolTip("Force full reindex of all NIF files")
        status_row.addWidget(self._rebuild_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setEnabled(False)
        status_row.addWidget(self._stop_btn)

        top_layout.addLayout(status_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        top_layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        top_layout.addWidget(self._progress_label)

        layout.addWidget(top_frame)

        search_frame = QGroupBox("Search")
        search_frame.setFlat(True)
        search_layout = QVBoxLayout(search_frame)
        search_layout.setSpacing(2)
        search_layout.setContentsMargins(4, 2, 4, 2)

        mode_row = QHBoxLayout()

        self._nif_to_dds_radio = QRadioButton("NIF → DDS (find textures used by mesh)")
        self._nif_to_dds_radio.setChecked(True)
        mode_row.addWidget(self._nif_to_dds_radio)

        self._dds_to_nif_radio = QRadioButton("DDS → NIF (find meshes using texture)")
        mode_row.addWidget(self._dds_to_nif_radio)

        mode_row.addStretch()
        search_layout.addLayout(mode_row)

        input_row = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Enter filename (e.g. armor01, rock, landscape/dirt)...")
        self._search_input.setClearButtonEnabled(True)
        input_row.addWidget(self._search_input)

        self._search_btn = QPushButton("🔍 Search")
        input_row.addWidget(self._search_btn)

        search_layout.addLayout(input_row)

        layout.addWidget(search_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        results_group = QGroupBox("Results")
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)
        results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels(["Item", "Score", "Details"])
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.setRootIsDecorated(True)
        self._results_tree.setIndentation(16)
        self._set_rows_height(self._results_tree, 20)

        header = self._results_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._results_tree.setColumnWidth(1, 50)
        self._results_tree.setColumnWidth(2, 120)

        results_layout.addWidget(self._results_tree)

        self._results_label = QLabel("No results")
        results_layout.addWidget(self._results_label)

        splitter.addWidget(results_group)

        details_group = QGroupBox("Details")
        details_group.setFlat(True)
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(4, 2, 4, 2)
        details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._details_tree = QTreeWidget()
        self._details_tree.setHeaderLabels(["Property", "Value"])
        self._details_tree.setAlternatingRowColors(True)
        self._details_tree.setRootIsDecorated(False)

        header2 = self._details_tree.header()
        header2.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header2.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._details_tree.setColumnWidth(0, 100)

        details_layout.addWidget(self._details_tree)

        splitter.addWidget(details_group)
        splitter.setSizes([450, 350])

        layout.addWidget(splitter, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(4)

        self._copy_btn = QPushButton("📋 Copy Results")
        bottom_row.addWidget(self._copy_btn)

        bottom_row.addStretch()

        self._active_only_cb = QCheckBox("Active mods only")
        self._active_only_cb.setChecked(True)
        bottom_row.addWidget(self._active_only_cb)

        self._include_bsas_cb = QCheckBox("Include BSAs (all mods + game data)")
        self._include_bsas_cb.setChecked(
            self.settings.value(f"{self.SETTINGS_KEY}/IncludeBSAs", False, type=bool)
        )
        bottom_row.addWidget(self._include_bsas_cb)
        self._apply_scope_controls()

        bottom_row.addStretch()

        self._goto_btn = QPushButton("➡️ Go to Mod")
        self._goto_btn.setEnabled(False)
        bottom_row.addWidget(self._goto_btn)

        self._open_folder_btn = QPushButton("📂 Open Folder")
        self._open_folder_btn.setEnabled(False)
        bottom_row.addWidget(self._open_folder_btn)

        layout.addLayout(bottom_row)

    def _set_rows_height(self, view: QTreeWidget, rows: int) -> None:
        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = view.fontMetrics().height() + 6
        height = row_height * rows + view.frameWidth() * 2
        header = view.header()
        if header is not None:
            height += header.height()
        view.setMinimumHeight(0)
        view.setMaximumHeight(height)

    def _connect_signals(self) -> None:
        self._search_btn.clicked.connect(self._do_search)
        self._search_input.returnPressed.connect(self._do_search)
        self._rebuild_btn.clicked.connect(self._rebuild_index)
        self._stop_btn.clicked.connect(self._stop_indexing)

        self._results_tree.itemClicked.connect(self._on_result_clicked)
        self._results_tree.itemDoubleClicked.connect(self._on_result_double_clicked)
        self._details_tree.itemDoubleClicked.connect(self._copy_detail_item)

        self._copy_btn.clicked.connect(self._copy_results)
        self._goto_btn.clicked.connect(self._goto_selected_mod)
        self._open_folder_btn.clicked.connect(self._open_selected_folder)

        self._nif_to_dds_radio.toggled.connect(self._on_mode_changed)
        self._include_bsas_cb.toggled.connect(self._on_include_bsas_toggled)
        self._active_only_cb.toggled.connect(self._on_active_only_toggled)

    def _apply_scope_controls(self) -> None:
        exhaustive = self._include_bsas_cb.isChecked()
        self._active_only_cb.setEnabled(not exhaustive)
        self._active_only_cb.setToolTip(
            "Include BSAs indexes all installed mods and game data."
            if exhaustive
            else ""
        )

    def _current_scope(self) -> dict:
        include_bsas = self._include_bsas_cb.isChecked()
        only_active = self._active_only_cb.isChecked() and not include_bsas
        return build_index_scope(self._organizer, include_bsas, only_active)

    def _on_include_bsas_toggled(self, checked: bool) -> None:
        self.settings.setValue(f"{self.SETTINGS_KEY}/IncludeBSAs", checked)
        self.settings.sync()
        self._apply_scope_controls()
        self._asset_catalog = None
        self.include_bsas_changed.emit(checked)
        self._index.clear()
        self._update_index_status()
        if self._is_indexing:
            self._pending_scope_rebuild = True
            self._stop_indexing()
        elif not self._first_activation:
            QTimer.singleShot(0, lambda: self._start_indexing(force_rebuild=True))

    def _on_active_only_toggled(self, _checked: bool) -> None:
        if self._include_bsas_cb.isChecked():
            return
        self._asset_catalog = None
        self._index.clear()
        self._update_index_status()
        if self._is_indexing:
            self._pending_scope_rebuild = True
            self._stop_indexing()
        elif not self._first_activation:
            QTimer.singleShot(0, lambda: self._start_indexing(force_rebuild=True))

    def set_include_bsas(self, checked: bool) -> None:
        if self._include_bsas_cb.isChecked() != checked:
            self._include_bsas_cb.setChecked(checked)
        else:
            self._apply_scope_controls()

    def refresh_if_needed(self) -> None:
        self.set_include_bsas(
            self.settings.value(f"{self.SETTINGS_KEY}/IncludeBSAs", False, type=bool)
        )
        if self._first_activation:
            self._first_activation = False

            scope = self._current_scope()
            self._index.set_scope(scope)
            if self._index.load_from_cache(scope):
                self._update_index_status()
                self.status_changed.emit(f"Index loaded: {self._index.nif_count} NIFs")
            else:
                QTimer.singleShot(100, lambda: self._start_indexing(force_rebuild=True))

    def _start_indexing(self, force_rebuild: bool = False) -> None:
        if self._is_indexing:
            return

        if force_rebuild:
            self._index.clear()
        self._index.set_scope(self._current_scope())

        self._is_indexing = True
        self._rebuild_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._search_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setVisible(True)

        self._index_icon.setText("🔄")
        self._index_status.setText("Indexing NIF files...")

        include_bsas = self._include_bsas_cb.isChecked()
        only_active = self._active_only_cb.isChecked() and not include_bsas

        self._index_worker = NifIndexWorker(
            self._organizer,
            self._index,
            only_active=only_active,
            incremental=not force_rebuild,
            include_archives=include_bsas,
        )

        self._index_worker.progress.connect(self._on_index_progress)
        self._index_worker.entry_ready.connect(self._on_entry_ready)
        self._index_worker.finished.connect(self._on_index_finished)
        self._index_worker.error.connect(self._on_index_error)
        self._index_worker.warning.connect(self._on_index_warning)

        self._index_worker.start()

    def _rebuild_index(self) -> None:
        self._start_indexing(force_rebuild=True)

    def _stop_indexing(self) -> None:
        if self._index_worker and self._index_worker.isRunning():
            self._index_worker.cancel()
            self._stop_btn.setEnabled(False)
            self._progress_label.setText("Stopping...")

    def _on_index_progress(self, current: int, total: int, filename: str) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_label.setText(f"{current}/{total}: {filename}")

    def _on_entry_ready(self, entry: NifTextureEntry) -> None:
        self._index.add_entry(entry)

    def _on_index_finished(self, total_nifs: int, total_textures: int) -> None:
        self._is_indexing = False
        self._rebuild_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._search_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        self._index.save_to_cache()

        self._update_index_status()
        self.status_changed.emit(
            f"Indexing complete: {self._index.nif_count} NIFs, "
            f"{self._index.texture_count} textures",
        )
        if self._pending_scope_rebuild:
            self._pending_scope_rebuild = False
            QTimer.singleShot(0, lambda: self._start_indexing(force_rebuild=True))

    def _on_index_warning(self, message: str) -> None:
        self.status_changed.emit(f"Archive warning: {message}")

    def _on_index_error(self, message: str) -> None:
        self._is_indexing = False
        self._rebuild_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._search_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        self._index_icon.setText("❌")
        self._index_status.setText(f"Error: {message}")
        self.status_changed.emit(f"Index error: {message}")

    def _update_index_status(self) -> None:
        if self._index.is_loaded:
            self._index_icon.setText("✅")
            self._index_status.setText(
                f"Ready: {self._index.nif_count:,} NIFs, "
                f"{self._index.texture_count:,} textures",
            )
        else:
            self._index_icon.setText("⚠️")
            self._index_status.setText("Index not loaded")

    def _on_mode_changed(self, checked: bool) -> None:
        if checked:
            self._search_input.setPlaceholderText(
                "Enter NIF filename (e.g. armor01, weapons/sword)...",
            )
        else:
            self._search_input.setPlaceholderText(
                "Enter texture filename (e.g. rock01, landscape/dirt)...",
            )

    def _do_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            return

        if not self._index.is_loaded:
            QMessageBox.information(
                self,
                "Index Required",
                "Please wait for indexing to complete or click 'Rebuild Index'.",
            )
            return

        self._results_tree.clear()
        self._details_tree.clear()
        self._goto_btn.setEnabled(False)
        self._open_folder_btn.setEnabled(False)

        if self._nif_to_dds_radio.isChecked():
            self._search_nif_textures(query)
        else:
            self._search_texture_nifs(query)

    def _search_nif_textures(self, query: str) -> None:
        results = self._index.find_textures_by_nif(query)

        if not results:
            self._results_label.setText("No NIFs found")
            return

        total_textures = 0

        for entry, score in results:
            source_label = entry.mod_name
            if entry.source_kind == "bsa":
                source_label = f"{entry.mod_name} [{Path(entry.container_path).name}]"
            nif_item = QTreeWidgetItem([
                f"📄 {entry.filename}",
                str(score),
                source_label,
            ])
            nif_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "nif",
                "entry": entry,
            })
            nif_item.setToolTip(0, self._entry_location(entry))

            font = QFont()
            font.setBold(True)
            nif_item.setFont(0, font)

            for tex in entry.textures:
                total_textures += 1
                tex_filename = tex.rsplit("/", 1)[-1] if "/" in tex else tex

                tex_item = QTreeWidgetItem([f"🖼️ {tex_filename}", "", ""])
                tex_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "texture",
                    "path": tex,
                    "nif_entry": entry,
                })
                tex_item.setToolTip(0, tex)

                nif_item.addChild(tex_item)

            self._results_tree.addTopLevelItem(nif_item)

        if self._results_tree.topLevelItemCount() > 0:
            self._results_tree.expandItem(self._results_tree.topLevelItem(0))

        self._results_label.setText(f"{len(results)} NIFs, {total_textures} textures")

    def _search_texture_nifs(self, query: str) -> None:
        results = self._index.find_nifs_by_texture(query)

        if not results:
            self._results_label.setText("No NIFs found using this texture")
            self._check_texture_exists(query)
            return

        high = [(e, s) for e, s in results if s >= 70]
        medium = [(e, s) for e, s in results if 40 <= s < 70]
        low = [(e, s) for e, s in results if s < 40]

        def add_group(name: str, items: list, icon: str):
            if not items:
                return

            group = QTreeWidgetItem([f"{icon} {name} ({len(items)})", "", ""])
            group.setData(0, Qt.ItemDataRole.UserRole, {"type": "group"})

            font = QFont()
            font.setBold(True)
            group.setFont(0, font)

            for entry, score in items:
                source_label = entry.mod_name
                if entry.source_kind == "bsa":
                    source_label = f"{entry.mod_name} [{Path(entry.container_path).name}]"
                item = QTreeWidgetItem([
                    entry.filename,
                    str(score),
                    source_label,
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "nif",
                    "entry": entry,
                })
                item.setToolTip(0, self._entry_location(entry))

                group.addChild(item)

            self._results_tree.addTopLevelItem(group)
            group.setExpanded(True)

        add_group("Exact matches", high, "🎯")
        add_group("Partial matches", medium, "🔍")
        add_group("Possible matches", low, "❓")

        self._results_label.setText(f"{len(results)} NIFs found")
        self._check_texture_exists(query)

    def _check_texture_exists(self, texture_path: str) -> None:
        self._add_detail("--- Texture Check ---", "")

        normalized = texture_path.lower().replace("\\", "/")
        if not normalized.startswith("textures/"):
            normalized = f"textures/{normalized}"
        if not normalized.endswith(".dds"):
            normalized += ".dds"

        if self._include_bsas_cb.isChecked():
            if self._asset_catalog is None:
                self._asset_catalog = AssetCatalog(
                    self._organizer,
                    include_archives=True,
                    exhaustive=True,
                )
            matches = self._asset_catalog.find_virtual_path(normalized)
            if matches:
                self._add_detail("Status", f"Found ({len(matches)} providers)")
                for number, source in enumerate(matches, start=1):
                    self._add_detail(
                        f"Source {number}",
                        f"{source.owner}: {source.location_text}",
                    )
            else:
                self._add_detail("Status", "NOT FOUND")
                self._add_detail("Query", texture_path)
                self._add_detail("Note", "Not present in loose files or BSAs")
            return

        resolved = self._organizer.resolvePath(normalized)

        if resolved and Path(resolved).exists():
            self._add_detail("Status", "✅ Found")
            self._add_detail("Path", resolved)

            mods_path = Path(self._organizer.modsPath())
            try:
                rel = Path(resolved).relative_to(mods_path)
                mod_name = rel.parts[0]
                self._add_detail("Mod", mod_name)
            except ValueError:
                self._add_detail("Mod", "[Game Data]")
        else:
            self._add_detail("Status", "❌ NOT FOUND")
            self._add_detail("Query", texture_path)
            self._add_detail("Note", "Missing or in disabled mod")

    def _add_detail(self, key: str, value: str) -> None:
        item = QTreeWidgetItem([key, value])
        item.setToolTip(1, value)
        self._details_tree.addTopLevelItem(item)

    def _on_result_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        self._details_tree.clear()
        item_type = data.get("type")

        if item_type == "nif":
            self._show_nif_details(data["entry"])
            self._goto_btn.setEnabled(not data["entry"].is_game)
            self._open_folder_btn.setEnabled(True)
        elif item_type == "texture":
            self._show_texture_details(data)
            self._goto_btn.setEnabled(not data["nif_entry"].is_game)
            self._open_folder_btn.setEnabled(True)
        else:
            self._goto_btn.setEnabled(False)
            self._open_folder_btn.setEnabled(False)

    def _show_nif_details(self, entry: NifTextureEntry) -> None:
        self._add_detail("--- NIF Info ---", "")
        self._add_detail("File", entry.filename)
        self._add_detail("Path", entry.relative_path)
        self._add_detail("Mod", entry.mod_name)
        self._add_detail("Source", "BSA" if entry.source_kind == "bsa" else "Loose file")
        if entry.source_kind == "bsa":
            self._add_detail("Archive", entry.container_path)
        self._add_detail("Textures", str(len(entry.textures)))

    def _show_texture_details(self, data: dict) -> None:
        self._add_detail("--- Texture Info ---", "")
        self._add_detail("Path", data.get("path", ""))
        entry = data.get("nif_entry")
        if entry:
            self._add_detail("NIF", entry.relative_path)
            self._add_detail("Mod", entry.mod_name)
            self._add_detail("Source", "BSA" if entry.source_kind == "bsa" else "Loose file")

    @staticmethod
    def _entry_location(entry: NifTextureEntry) -> str:
        if entry.source_kind == "bsa":
            return f"{entry.container_path} :: {entry.relative_path}"
        return entry.container_path or f"{entry.mod_name}/{entry.relative_path}"

    def _copy_detail_item(self, item: QTreeWidgetItem, column: int) -> None:
        value = item.text(1)
        if value:
            QApplication.clipboard().setText(value)
            self.status_changed.emit(f"Copied: {value}")

    def _on_result_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        entry = None
        if data.get("type") == "nif":
            entry = data["entry"]
        elif data.get("type") == "texture":
            entry = data.get("nif_entry")

        if entry and not entry.is_game:
            self._goto_mod_in_view(entry.mod_name)

    def _goto_mod_in_view(self, mod_name: str) -> None:
        if not self._mods_view or not self._mods_view.model():
            self.status_changed.emit("Error: Mods view not available")
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

            self.status_changed.emit(f"Selected: {display_name}")
            self.goto_mod.emit(mod_name)
        else:
            self.status_changed.emit(f"Could not find mod: {display_name}")

    def _open_selected_folder(self) -> None:
        items = self._results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        entry = None
        if data.get("type") == "nif":
            entry = data["entry"]
        elif data.get("type") == "texture":
            entry = data.get("nif_entry")

        if not entry:
            return

        file_path = entry.container_path
        if not file_path:
            if entry.is_game:
                return
            mod_info = self._organizer.getMod(entry.mod_name)
            if not mod_info:
                return
            file_path = os.path.join(mod_info.absolutePath(), entry.relative_path)
        folder_path = os.path.dirname(file_path)

        if os.path.exists(folder_path):
            import subprocess
            import sys

            if sys.platform == "win32":
                if os.path.exists(file_path):
                    subprocess.run(["explorer", "/select,", file_path])
                else:
                    os.startfile(folder_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

            self.status_changed.emit(f"Opened: {folder_path}")

    def _copy_results(self) -> None:
        lines = ["=== NIF ↔ DDS Search Results ===", ""]

        def collect_items(item: QTreeWidgetItem, indent: int = 0):
            prefix = "  " * indent
            text = item.text(0)
            score = item.text(1)
            mod = item.text(2)

            line = f"{prefix}{text}"
            if score:
                line += f" [score: {score}]"
            if mod:
                line += f" ({mod})"
            lines.append(line)

            for i in range(item.childCount()):
                collect_items(item.child(i), indent + 1)

        for i in range(self._results_tree.topLevelItemCount()):
            collect_items(self._results_tree.topLevelItem(i))

        QApplication.clipboard().setText("\n".join(lines))
        self.status_changed.emit("Results copied to clipboard")

    def _goto_selected_mod(self) -> None:
        items = self._results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        entry = None
        if data.get("type") == "nif":
            entry = data["entry"]
        elif data.get("type") == "texture":
            entry = data.get("nif_entry")

        if entry and not entry.is_game:
            self._goto_mod_in_view(entry.mod_name)

    def focus_search(self) -> None:
        self._search_input.setFocus()
        self._search_input.selectAll()

    def handle_key_press(self, key: int) -> bool:
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._search_input.hasFocus():
                self._do_search()
                return True
        elif key == Qt.Key.Key_Down and self._search_input.hasFocus():
            self._results_tree.setFocus()
            if self._results_tree.topLevelItemCount() > 0:
                self._results_tree.setCurrentItem(self._results_tree.topLevelItem(0))
            return True
        return False


__all__ = ["NifTextureSearchTab"]
