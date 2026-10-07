import os
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
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
from .archive_core import AssetSource
from .nif_search import NifSearchWorker, entry_source
from .nif_tree_filter import AssetTreeFilter
from .preview_bridge import can_preview_virtual_path, preview_asset_source, preview_nif_entry


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
        self._pending_external_texture_query = ""
        self._search_generation = 0
        self._search_workers = []
        self._index_workers = []
        self._snapshot = None
        self._action_data = None

        self._last_query = ""
        self._profile_index_dirty = False

        self.settings = QSettings("ModOrganizer2", "FullModSearchPlugin")

        self._setup_ui()
        self._connect_signals()
        self._subscribe_profile_changes()

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
        self._search_btn.setEnabled(False)
        input_row.addWidget(self._search_btn)

        search_layout.addLayout(input_row)

        layout.addWidget(search_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        results_group = QGroupBox("Results")
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)
        results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._results_filter_input, result_expand, result_collapse = self._filter_controls(
            results_layout, "Filter results (all words or quoted phrases)..."
        )

        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels(["Item", "Score", "Winning Mod"])
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.setRootIsDecorated(True)
        self._results_tree.setIndentation(16)
        self._results_tree.setUniformRowHeights(True)

        header = self._results_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self._results_tree.setColumnWidth(1, 50)
        self._results_tree.setColumnWidth(2, 260)

        results_layout.addWidget(self._results_tree)

        self._results_label = QLabel("No results")
        results_layout.addWidget(self._results_label)

        splitter.addWidget(results_group)

        details_group = QGroupBox("Details")
        details_group.setFlat(True)
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(4, 2, 4, 2)
        details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._details_filter_input, detail_expand, detail_collapse = self._filter_controls(
            details_layout, "Filter referenced textures and providers..."
        )

        self._details_tree = QTreeWidget()
        self._details_tree.setHeaderLabels(["Property", "Value"])
        self._details_tree.setAlternatingRowColors(True)
        self._details_tree.setRootIsDecorated(True)
        self._details_tree.setUniformRowHeights(True)

        header2 = self._details_tree.header()
        header2.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header2.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._details_tree.setColumnWidth(0, 175)

        details_layout.addWidget(self._details_tree)
        self._details_label = QLabel("")
        details_layout.addWidget(self._details_label)
        self._results_filter = AssetTreeFilter(
            self._results_tree, self._results_filter_input, self._results_label, "nif"
        )
        self._details_filter = AssetTreeFilter(
            self._details_tree, self._details_filter_input, self._details_label, "texture"
        )
        result_expand.clicked.connect(self._results_filter.expand_all)
        result_collapse.clicked.connect(self._results_filter.collapse_all)
        detail_expand.clicked.connect(self._details_filter.expand_all)
        detail_collapse.clicked.connect(self._details_filter.collapse_all)

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

        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setEnabled(False)
        bottom_row.addWidget(self._preview_btn)

        self._open_folder_btn = QPushButton("📂 Open Folder")
        self._open_folder_btn.setEnabled(False)
        bottom_row.addWidget(self._open_folder_btn)

        layout.addLayout(bottom_row)

    def _filter_controls(self, layout, placeholder):
        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        row.addWidget(edit, 1)
        expand = QPushButton("Expand All")
        collapse = QPushButton("Collapse All")
        row.addWidget(expand)
        row.addWidget(collapse)
        layout.addLayout(row)
        return edit, expand, collapse

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
        self._details_tree.itemClicked.connect(self._on_detail_clicked)
        self._details_tree.itemDoubleClicked.connect(self._on_detail_double_clicked)
        self._results_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._details_tree.itemSelectionChanged.connect(self._on_selection_changed)

        self._copy_btn.clicked.connect(self._copy_results)
        self._goto_btn.clicked.connect(self._goto_selected_mod)
        self._preview_btn.clicked.connect(self._preview_selected_result)
        self._open_folder_btn.clicked.connect(self._open_selected_folder)

        self._nif_to_dds_radio.toggled.connect(self._on_mode_changed)
        self._include_bsas_cb.toggled.connect(self._on_include_bsas_toggled)
        self._active_only_cb.toggled.connect(self._on_active_only_toggled)

    def _subscribe_profile_changes(self):
        self._profile_refresh_timer = QTimer(self)
        self._profile_refresh_timer.setSingleShot(True)
        self._profile_refresh_timer.setInterval(350)
        self._profile_refresh_timer.timeout.connect(self._refresh_profile_search)
        try:
            self._mod_list.onModStateChanged(self._on_states_changed)
            self._mod_list.onModMoved(self._on_priority_changed)
            plugins = self._organizer.pluginList()
            plugins.onPluginStateChanged(self._on_states_changed)
            plugins.onPluginMoved(self._on_priority_changed)
            plugins.onRefreshed(self._on_profile_dirty)
            self._organizer.onProfileChanged(self._on_profile_changed)
        except AttributeError:
            pass

    def _on_states_changed(self, changes: dict):
        if not self._include_bsas_cb.isChecked() and self._active_only_cb.isChecked():
            self._profile_index_dirty = True
        self._on_profile_dirty()

    def _on_priority_changed(self, name, old_priority, new_priority):
        self._on_profile_dirty()

    def _on_profile_changed(self, old_profile, new_profile):
        self._profile_index_dirty = True
        self._on_profile_dirty()

    def _on_profile_dirty(self):
        self._invalidate_search()
        self._clear_search_views()
        self._profile_refresh_timer.start()

    def _refresh_profile_search(self):
        if self._profile_index_dirty and not self._first_activation:
            self._profile_index_dirty = False
            if self._is_indexing:
                self._pending_scope_rebuild = True
                self._stop_indexing()
            else:
                self._start_indexing(force_rebuild=False)
            return
        if self._last_query and self._index.is_loaded and not self._is_indexing:
            self._do_search()

    def _invalidate_search(self):
        self._search_generation += 1
        for worker in self._search_workers:
            worker.cancel()
        self._snapshot = None
        self._action_data = None
        if not self._is_indexing:
            self._stop_btn.setEnabled(False)

    def _clear_search_views(self):
        self._results_filter.reset()
        self._details_filter.reset()
        self._results_tree.clear()
        self._details_tree.clear()
        self._results_label.setText("No results")
        self._details_label.clear()
        self._set_action_data(None)

    def _apply_scope_controls(self) -> None:
        exhaustive = self._include_bsas_cb.isChecked()
        self._active_only_cb.setEnabled(not exhaustive)
        self._active_only_cb.setToolTip(
            "Include BSAs indexes all installed mods and game data."
            if exhaustive
            else ""
        )

    def _on_include_bsas_toggled(self, checked: bool) -> None:
        self._invalidate_search()
        self._clear_search_views()
        self.settings.setValue(f"{self.SETTINGS_KEY}/IncludeBSAs", checked)
        self.settings.sync()
        self._apply_scope_controls()
        self.include_bsas_changed.emit(checked)
        self._index = NifTextureIndex(self._index.cache_dir)
        self._update_index_status()
        self._search_btn.setEnabled(False)
        if self._is_indexing:
            self._pending_scope_rebuild = True
            self._stop_indexing()
        elif not self._first_activation:
            QTimer.singleShot(0, lambda: self._start_indexing(force_rebuild=True))

    def _on_active_only_toggled(self, _checked: bool) -> None:
        if self._include_bsas_cb.isChecked():
            return
        self._invalidate_search()
        self._clear_search_views()
        self._index = NifTextureIndex(self._index.cache_dir)
        self._update_index_status()
        self._search_btn.setEnabled(False)
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
            QTimer.singleShot(100, lambda: self._start_indexing(force_rebuild=False))

    def find_nif_references(self, texture_path: str) -> bool:
        query = (texture_path or "").strip()
        if not query:
            return False

        self._pending_external_texture_query = query
        self._dds_to_nif_radio.setChecked(True)
        self._search_input.setText(query)
        self.focus_search()
        self.refresh_if_needed()

        if self._index.is_loaded and not self._is_indexing and not self._pending_scope_rebuild:
            self._pending_external_texture_query = ""
            QTimer.singleShot(0, self._do_search)
        elif not self._is_indexing and not self._first_activation:
            self._start_indexing(force_rebuild=False)

        self.status_changed.emit(f"Queued DDS -> NIF search: {query}")
        return True

    def _run_pending_external_search(self) -> None:
        if not self._pending_external_texture_query:
            return
        if not self._index.is_loaded or self._pending_scope_rebuild:
            return
        query = self._pending_external_texture_query
        self._pending_external_texture_query = ""
        self._dds_to_nif_radio.setChecked(True)
        self._search_input.setText(query)
        self.focus_search()
        self._do_search()

    def _start_indexing(self, force_rebuild: bool = False) -> None:
        if self._is_indexing:
            return

        self._invalidate_search()
        self._clear_search_views()
        if force_rebuild:
            self._index = NifTextureIndex(self._index.cache_dir)

        self._is_indexing = True
        self._rebuild_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._search_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setVisible(True)

        self._index_icon.setText("🔄")
        self._index_status.setText("Preparing index...")

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
        self._index_worker.phase.connect(self._on_index_phase)
        self._index_worker.index_ready.connect(self._on_index_ready)
        self._index_worker.completed.connect(self._on_index_finished)
        self._index_worker.error.connect(self._on_index_error)
        self._index_worker.warning.connect(self._on_index_warning)
        worker = self._index_worker
        self._index_workers.append(worker)
        worker.finished.connect(lambda: self._release_index_worker(worker))

        self._index_worker.start()

    def _release_index_worker(self, worker):
        if worker in self._index_workers:
            self._index_workers.remove(worker)
        if self._index_worker is worker:
            self._index_worker = None
        worker.deleteLater()

    def _rebuild_index(self) -> None:
        self._start_indexing(force_rebuild=True)

    def _stop_indexing(self) -> None:
        if self._index_worker and self._index_worker.isRunning():
            self._index_worker.cancel()
            self._stop_btn.setEnabled(False)
            self._progress_label.setText("Stopping...")
        elif self._search_workers:
            self._invalidate_search()
            self._clear_search_views()
            self._results_label.setText("Search stopped")
            self._stop_btn.setEnabled(False)
            self._search_btn.setEnabled(self._index.is_loaded)

    def _on_index_progress(self, current: int, total: int, filename: str) -> None:
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)
            self._progress_label.setText(f"{current}/{total}: {filename}")
        else:
            self._progress_bar.setMaximum(0)
            self._progress_label.setText(f"{current}: {filename}")

    def _on_index_phase(self, message: str) -> None:
        self._index_status.setText(message)
        self._progress_label.setText(message)

    def _on_index_ready(self, index: NifTextureIndex, loaded_from_cache: bool) -> None:
        if self._pending_scope_rebuild:
            return
        self._index = index
        if loaded_from_cache:
            self.status_changed.emit(f"Index loaded: {self._index.nif_count} NIFs")

    def _on_index_finished(self, total_nifs: int, total_textures: int) -> None:
        self._is_indexing = False
        self._rebuild_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._search_btn.setEnabled(self._index.is_loaded and not self._pending_scope_rebuild)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        self._update_index_status()
        self.status_changed.emit(
            f"Indexing complete: {self._index.nif_count} NIFs, "
            f"{self._index.texture_count} textures",
        )
        if self._pending_scope_rebuild:
            self._pending_scope_rebuild = False
            QTimer.singleShot(0, lambda: self._start_indexing(force_rebuild=True))
        elif self._pending_external_texture_query:
            QTimer.singleShot(0, self._run_pending_external_search)
        elif self._last_query and self._index.is_loaded:
            QTimer.singleShot(0, self._do_search)

    def _on_index_warning(self, message: str) -> None:
        self.status_changed.emit(f"Archive warning: {message}")

    def _on_index_error(self, message: str) -> None:
        self._is_indexing = False
        self._rebuild_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._search_btn.setEnabled(self._index.is_loaded)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        self._index_icon.setText("❌")
        self._index_status.setText(f"Error: {message}")
        self._pending_external_texture_query = ""
        self.status_changed.emit(f"Index error: {message}")
        if self._pending_scope_rebuild:
            self._pending_scope_rebuild = False
            QTimer.singleShot(0, lambda: self._start_indexing(force_rebuild=True))

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
        self._invalidate_search()
        self._clear_search_views()
        self._search_btn.setEnabled(self._index.is_loaded and not self._is_indexing)
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
        if not query or self._is_indexing:
            return
        if not self._index.is_loaded:
            QMessageBox.information(self, "Index Required", "Please wait for indexing or rebuild the index.")
            return
        self._invalidate_search()
        self._clear_search_views()
        self._results_filter.reset(clear=True)
        self._details_filter.reset(clear=True)
        self._last_query = query
        generation = self._search_generation
        self._search_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._results_label.setText("Resolving current-profile winners...")
        worker = NifSearchWorker(
            self._organizer, self._index, query, self._nif_to_dds_radio.isChecked(), generation
        )
        self._search_workers.append(worker)
        worker.ready.connect(self._on_search_ready)
        worker.failed.connect(self._on_search_failed)
        worker.finished.connect(lambda: self._release_search_worker(worker))
        worker.start()

    def _release_search_worker(self, worker):
        if worker in self._search_workers:
            self._search_workers.remove(worker)
        worker.deleteLater()

    def _on_search_failed(self, generation, message):
        if generation != self._search_generation:
            return
        self._search_btn.setEnabled(self._index.is_loaded and not self._is_indexing)
        self._stop_btn.setEnabled(False)
        self._results_label.setText(f"Search failed: {message}")
        self.status_changed.emit(f"Search error: {message}")

    def _on_search_ready(self, generation, payload):
        if generation != self._search_generation:
            return
        self._snapshot = payload["snapshot"]
        results = payload["results"]
        groups = {}
        nif_to_dds = payload["nif_to_dds"]
        if not nif_to_dds:
            for label, minimum, maximum in (("Exact matches", 70, 101),
                                             ("Partial matches", 40, 70),
                                             ("Possible matches", 0, 40)):
                count = sum(minimum <= score < maximum for entry, score in results)
                if count:
                    group = QTreeWidgetItem([f"{label} ({count})", "", ""])
                    group.setData(0, Qt.ItemDataRole.UserRole, {"type": "group"})
                    self._results_tree.addTopLevelItem(group)
                    group.setExpanded(True)
                    groups[label] = group
            high = [item for item in results if item[1] >= 70]
            medium = [item for item in results if 40 <= item[1] < 70]
            low = [item for item in results if item[1] < 40]
            self._show_dds_search_summary(payload["query"], results, high, medium, low, payload["total"])
        else:
            self._add_detail("Query", payload["query"])
            self._add_detail("Matching NIFs", str(payload["total"]))
            self._add_detail("Details", "Select a NIF or referenced texture")
        warnings = self._snapshot.warnings
        if warnings:
            self._add_detail("Resolution Warnings", f"{len(warnings)} (see tooltip)").setToolTip(
                1, "\n".join(warnings)
            )
        suffix = ""
        if payload["total"] > len(results):
            suffix = f" - showing first {len(results)} of {payload['total']} matches"
        self._results_filter.suffix = suffix
        self._details_filter.apply()

        def append_batch(offset=0):
            if generation != self._search_generation:
                return
            self._results_tree.setUpdatesEnabled(False)
            try:
                for entry, score in results[offset:offset + 40]:
                    item = self._make_nif_item(entry, score, nif_to_dds)
                    if nif_to_dds:
                        self._results_tree.addTopLevelItem(item)
                    else:
                        name = "Exact matches" if score >= 70 else "Partial matches" if score >= 40 else "Possible matches"
                        groups[name].addChild(item)
            finally:
                self._results_tree.setUpdatesEnabled(True)
            if offset + 40 < len(results):
                QTimer.singleShot(0, lambda: append_batch(offset + 40))
            else:
                if nif_to_dds and results:
                    self._results_tree.topLevelItem(0).setExpanded(True)
                self._results_filter.apply()
                self._search_btn.setEnabled(True)
                self._stop_btn.setEnabled(False)
                self.status_changed.emit(
                    f"{payload['total']} unique winning NIFs; {len(warnings)} resolution warnings"
                )
        append_batch()

    def _make_nif_item(self, entry, score, include_textures):
        label = self._provider_label(entry_source(entry))
        item = QTreeWidgetItem([entry.filename, str(score), label])
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "nif", "entry": entry,
            "search": f"{entry.filename} {entry.relative_path} {label}",
        })
        item.setToolTip(0, self._entry_location(entry))
        item.setToolTip(2, label)
        if include_textures:
            for texture_path in entry.textures:
                item.addChild(self._make_texture_item(texture_path, entry, results=True))
        return item

    def _show_dds_search_summary(
        self,
        query: str,
        results: list,
        high: list,
        medium: list,
        low: list,
        total=None,
    ) -> None:
        self._add_detail("--- DDS -> NIF Search ---", "")
        self._add_detail("Query", query)
        self._add_detail("Matching NIFs", str(total if total is not None else len(results)))
        if total is not None and total > len(results):
            self._add_detail("Displayed NIFs", str(len(results)))
        self._add_detail("Exact", str(len(high)))
        self._add_detail("Partial", str(len(medium)))
        self._add_detail("Possible", str(len(low)))
        if results:
            self._add_detail("Details", "Select a NIF to inspect referenced texture paths")
        else:
            self._add_detail("Details", "No indexed NIF references matched this query")

    def _add_detail(self, key: str, value: str):
        item = QTreeWidgetItem([key, value])
        item.setToolTip(1, value)
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "property"})
        self._details_tree.addTopLevelItem(item)
        return item

    def _on_result_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        self._details_filter.reset()
        self._details_tree.clear()
        item_type = data.get("type")

        if item_type == "nif":
            self._show_nif_details(data["entry"])
        elif item_type == "texture":
            self._show_texture_details(data)
        self._details_filter.apply()
        self._set_action_data(data)

    def _show_nif_details(self, entry: NifTextureEntry) -> None:
        self._add_detail("File", entry.filename)
        self._add_detail("Path", entry.relative_path)
        self._add_detail("Mod", entry.mod_name)
        self._add_detail("Source Type", "BSA" if entry.source_kind == "bsa" else "Loose file").setToolTip(
            1, self._entry_location(entry)
        )
        self._add_detail("Texture Count", str(len(entry.textures)))
        if entry.parse_error:
            self._add_detail("Read Error", entry.parse_error)
        group = QTreeWidgetItem(["Referenced Textures", str(len(entry.textures))])
        group.setData(0, Qt.ItemDataRole.UserRole, {"type": "group"})
        self._details_tree.addTopLevelItem(group)
        for texture_path in entry.textures:
            group.addChild(self._make_texture_item(texture_path, entry))
        group.setExpanded(True)

    def _make_texture_item(self, texture_path, entry, results=False):
        providers = self._snapshot.providers(texture_path) if self._snapshot else []
        found = any(provider.winning for provider in providers)
        status = "Found" if found else "Missing"
        item = QTreeWidgetItem(
            [texture_path, status, ""] if results else [status, texture_path]
        )
        item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "texture", "path": texture_path, "nif_entry": entry,
            "search": f"{texture_path} {status}",
        })
        item.setToolTip(0, texture_path)
        item.setToolTip(1, texture_path)
        if not results:
            for provider in providers:
                source = provider.source
                child = QTreeWidgetItem(["Provider", provider.label])
                child.setToolTip(1, source.location_text)
                child.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "provider", "source": source, "path": texture_path,
                    "nif_entry": entry, "search": f"{texture_path} {provider.label}",
                })
                item.addChild(child)
        return item

    def _show_texture_details(self, data: dict) -> None:
        self._add_detail("Path", data.get("path", ""))
        entry = data.get("nif_entry")
        if entry:
            self._add_detail("NIF", entry.relative_path)
            self._add_detail("Mod", entry.mod_name)
            self._add_detail("Source Type", "BSA" if entry.source_kind == "bsa" else "Loose file")
        group = QTreeWidgetItem(["Referenced Textures", "1"])
        group.setData(0, Qt.ItemDataRole.UserRole, {"type": "group"})
        self._details_tree.addTopLevelItem(group)
        texture = self._make_texture_item(data.get("path", ""), entry)
        group.addChild(texture)
        group.setExpanded(True)
        texture.setExpanded(True)

    @staticmethod
    def _provider_label(source: AssetSource) -> str:
        if source.source_kind == "bsa":
            archive = source.archive_name or Path(source.container_path).name
            return f"{source.owner} [{archive}]"
        return f"{source.owner} [Loose]"

    def _on_detail_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        self._set_action_data(data if data.get("type") in ("texture", "provider") else None)

    def _on_detail_double_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") in ("texture", "provider"):
            self._preview_result_data(data)
        else:
            self._copy_detail_item(item, column)

    def _on_selection_changed(self):
        if self._action_data and not any(
            item.data(0, Qt.ItemDataRole.UserRole) == self._action_data
            for item in self._results_tree.selectedItems() + self._details_tree.selectedItems()
        ):
            self._set_action_data(None)

    def _set_action_data(self, data):
        self._action_data = data
        source = self._action_source(data)
        self._goto_btn.setEnabled(bool(source and not source.is_game))
        self._open_folder_btn.setEnabled(bool(source))
        self._preview_btn.setEnabled(bool(source and can_preview_virtual_path(source.virtual_path)))

    def _action_source(self, data):
        if not data:
            return None
        if data.get("type") == "provider":
            return data["source"]
        if data.get("type") == "nif":
            return entry_source(data["entry"])
        if data.get("type") == "texture" and self._snapshot:
            return next((provider.source for provider in self._snapshot.providers(data["path"])
                         if provider.winning), None)
        return None

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

        self._preview_result_data(data)

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

    def _preview_selected_result(self) -> None:
        if self._action_data:
            self._preview_result_data(self._action_data)

    def _preview_result_data(self, data: dict) -> None:
        if data.get("type") not in ("nif", "texture", "provider"):
            return
        if data.get("type") == "nif":
            entry = data.get("entry")
            if preview_nif_entry(self, entry, self._organizer) and entry:
                self.status_changed.emit(f"Preview: {entry.relative_path}")
            return
        source = self._action_source(data)
        if source is None:
            QMessageBox.information(self, "Preview", "No effective DDS provider exists in the current profile.")
        elif preview_asset_source(self, source, self._organizer, exact_source=True):
            self.status_changed.emit(f"Preview: {source.virtual_path}")

    def _open_selected_folder(self) -> None:
        source = self._action_source(self._action_data)
        if source is None:
            return
        file_path = source.navigation_path or source.container_path
        folder_path = os.path.dirname(file_path)
        if os.path.exists(folder_path):
            import subprocess
            import sys
            if sys.platform == "win32":
                if os.path.exists(file_path):
                    subprocess.Popen(["explorer", "/select,", file_path])
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
            if item.isHidden():
                return
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
        source = self._action_source(self._action_data)
        if source and not source.is_game:
            self._goto_mod_in_view(source.owner)

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
