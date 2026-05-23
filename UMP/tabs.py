from pathlib import Path
from typing import Optional, Iterator

import mobase
from PyQt6.QtCore import Qt, QEvent, QSettings, QThread, pyqtSignal, QTimer, QByteArray
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QAbstractItemView, QTreeView, QApplication,
    QTabWidget, QWidget, QLabel, QGroupBox, QPushButton, QCheckBox,
    QSplitter, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QComboBox, QMessageBox, QRadioButton, QHeaderView,
    QDockWidget, QMainWindow, QScrollArea
)
from PyQt6.QtGui import QShortcut, QKeySequence, QFont
import fnmatch
import os

from .nif_core import LightweightNifParser, NifTextureEntry, NifTextureIndex, NifIndexWorker




class FileSearchWorker(QThread):
    """Background worker for file searching"""

    progress = pyqtSignal(int, int)
    result_found = pyqtSignal(str, str, str)
    finished_search = pyqtSignal(int)

    def __init__(self, organizer: "mobase.IOrganizer", search_pattern: str,
                 file_extensions: list, search_in_bsa: bool = False):
        super().__init__()
        self._organizer = organizer
        self._search_pattern = search_pattern
        self._file_extensions = file_extensions
        self._search_in_bsa = search_in_bsa
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        results_count = 0
        mod_list = self._organizer.modList()
        all_mods = mod_list.allMods()
        total_mods = len(all_mods)

        search_lower = self._search_pattern.lower()

        for i, mod_name in enumerate(all_mods):
            if self._cancelled:
                break

            self.progress.emit(i + 1, total_mods)

            state = mod_list.state(mod_name)
            if not (state & mobase.ModState.EXISTS):
                continue

            mod_info = self._organizer.getMod(mod_name)
            if not mod_info:
                continue

            mod_path = mod_info.absolutePath()
            if not mod_path or not os.path.exists(mod_path):
                continue

            try:
                for root, dirs, files in os.walk(mod_path):
                    if self._cancelled:
                        break

                    for file_name in files:
                        if self._cancelled:
                            break

                        file_lower = file_name.lower()

                        if self._file_extensions:
                            ext = os.path.splitext(file_lower)[1]
                            if ext and ext not in self._file_extensions:
                                continue

                        if search_lower in file_lower or fnmatch.fnmatch(file_lower, f"*{search_lower}*"):
                            full_path = os.path.join(root, file_name)
                            relative_path = os.path.relpath(full_path, mod_path)

                            self.result_found.emit(mod_name, relative_path, full_path)
                            results_count += 1

            except Exception:
                continue

        self.finished_search.emit(results_count)


class NifTextureSearchTab(QWidget):
    """
    Вкладка поиска NIF ↔ DDS.
    Автоматически индексирует при первом открытии, кэширует между сессиями.
    """

    SETTINGS_KEY = "FullModSearch"

    status_changed = pyqtSignal(str)
    goto_mod = pyqtSignal(str)

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

        self._results_tree = QTreeWidget()
        self._results_tree.setHeaderLabels(["Item", "Score", "Details"])
        self._results_tree.setAlternatingRowColors(True)
        self._results_tree.setRootIsDecorated(True)
        self._results_tree.setIndentation(16)

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

        bottom_row.addStretch()

        self._goto_btn = QPushButton("➡️ Go to Mod")
        self._goto_btn.setEnabled(False)
        bottom_row.addWidget(self._goto_btn)

        self._open_folder_btn = QPushButton("📂 Open Folder")
        self._open_folder_btn.setEnabled(False)
        bottom_row.addWidget(self._open_folder_btn)

        layout.addLayout(bottom_row)

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

    def refresh_if_needed(self) -> None:
        if self._first_activation:
            self._first_activation = False

            if self._index.load_from_cache():
                self._update_index_status()
                self.status_changed.emit(f"Index loaded: {self._index.nif_count} NIFs")
            else:
                QTimer.singleShot(100, self._start_indexing)

    def _start_indexing(self, force_rebuild: bool = False) -> None:
        if self._is_indexing:
            return

        if force_rebuild:
            self._index.clear()

        self._is_indexing = True
        self._rebuild_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._search_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setVisible(True)

        self._index_icon.setText("🔄")
        self._index_status.setText("Indexing NIF files...")

        only_active = self._active_only_cb.isChecked()

        self._index_worker = NifIndexWorker(
            self._organizer,
            self._index,
            only_active=only_active,
            incremental=not force_rebuild,
        )

        self._index_worker.progress.connect(self._on_index_progress)
        self._index_worker.entry_ready.connect(self._on_entry_ready)
        self._index_worker.finished.connect(self._on_index_finished)
        self._index_worker.error.connect(self._on_index_error)

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

    def _on_entry_ready(self, mod_name: str, relative_path: str,
                        textures: list, mtime: float) -> None:
        self._index.add_nif(mod_name, relative_path, textures, mtime)

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
            nif_item = QTreeWidgetItem([
                f"📄 {entry.filename}",
                str(score),
                entry.mod_name,
            ])
            nif_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "nif",
                "entry": entry,
            })
            nif_item.setToolTip(0, f"{entry.mod_name}/{entry.relative_path}")

            font = QFont()
            font.setBold(True)
            nif_item.setFont(0, font)

            state = self._mod_list.state(entry.mod_name)

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
                item = QTreeWidgetItem([
                    entry.filename,
                    str(score),
                    entry.mod_name,
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "nif",
                    "entry": entry,
                })
                item.setToolTip(0, f"{entry.mod_name}/{entry.relative_path}")

                state = self._mod_list.state(entry.mod_name)

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
            self._goto_btn.setEnabled(True)
            self._open_folder_btn.setEnabled(True)
        elif item_type == "texture":
            self._show_texture_details(data)
            self._goto_btn.setEnabled(True)
            self._open_folder_btn.setEnabled(True)
        else:
            self._goto_btn.setEnabled(False)
            self._open_folder_btn.setEnabled(False)

    def _show_nif_details(self, entry: NifTextureEntry) -> None:
        self._add_detail("--- NIF Info ---", "")
        self._add_detail("File", entry.filename)
        self._add_detail("Path", entry.relative_path)
        self._add_detail("Mod", entry.mod_name)
        self._add_detail("Textures", str(len(entry.textures)))

        self._add_detail("--- Textures ---", "")
        for tex in entry.textures[:20]:
            normalized = tex.lower().replace("\\", "/")
            if not normalized.startswith("textures/"):
                normalized = f"textures/{normalized}"

            resolved = self._organizer.resolvePath(normalized)
            status = "✅" if resolved and Path(resolved).exists() else "❌"
            self._add_detail(status, tex)

        if len(entry.textures) > 20:
            self._add_detail("...", f"+{len(entry.textures) - 20} more")

    def _show_texture_details(self, data: dict) -> None:
        tex_path = data.get("path", "")
        nif_entry = data.get("nif_entry")

        self._add_detail("--- Texture ---", "")
        self._add_detail("Path", tex_path)

        self._check_texture_exists(tex_path)

        if nif_entry:
            self._add_detail("--- Parent NIF ---", "")
            self._add_detail("File", nif_entry.filename)
            self._add_detail("Mod", nif_entry.mod_name)

        other_nifs = self._index.find_nifs_by_texture(tex_path, limit=10)
        if len(other_nifs) > 1:
            self._add_detail("--- Also used by ---", "")
            for entry, score in other_nifs[:10]:
                if not nif_entry or entry.key != nif_entry.key:
                    self._add_detail("📄", f"{entry.mod_name}/{entry.filename}")

    def _on_result_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") == "group":
            return

        entry = None
        if data.get("type") == "nif":
            entry = data["entry"]
        elif data.get("type") == "texture":
            entry = data.get("nif_entry")

        if entry:
            self._goto_mod_in_view(entry.mod_name)

    def _copy_detail_item(self, item: QTreeWidgetItem, column: int) -> None:
        text = item.text(1) if column == 1 else item.text(0)
        if text:
            for prefix in ["✅ ", "❌ ", "📄 ", "🖼️ "]:
                text = text.removeprefix(prefix)

            QApplication.clipboard().setText(text)

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

        if entry:
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

        mod_info = self._organizer.getMod(entry.mod_name)
        if not mod_info:
            return

        mod_path = mod_info.absolutePath()
        file_path = os.path.join(mod_path, entry.relative_path)
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


class ModNameSearchTab(QWidget):
    """Tab for searching mods by name"""

    SETTINGS_KEY = "FullModSearch"
    MAX_RECENT_ITEMS = 10

    mod_selected = pyqtSignal(str)

    def __init__(self, parent, mods_view: "QTreeView", mod_list: "mobase.IModList"):
        super().__init__(parent)
        self.mods_view = mods_view
        self.mod_list = mod_list
        self.settings = QSettings("ModOrganizer2", "FullModSearchPlugin")
        self._loaded = False

        self._setup_ui()
        self._load_recent_mods()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        search_layout = QHBoxLayout()

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Enter mod name to search...")
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        self.case_sensitive_cb = QCheckBox("Case Sensitive", self)
        search_layout.addWidget(self.case_sensitive_cb)

        layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.mod_list_widget = QListWidget(self)
        self.mod_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mod_list_widget.setAlternatingRowColors(True)
        results_layout.addWidget(self.mod_list_widget)

        self.results_label = QLabel("0 mods found", self)
        results_layout.addWidget(self.results_label)

        splitter.addWidget(results_group)

        recent_group = QGroupBox("Recent Selections (Last 10)", self)
        recent_group.setFlat(True)
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(4, 2, 4, 2)

        self.recent_list_widget = QListWidget(self)
        self.recent_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recent_list_widget.setAlternatingRowColors(True)
        self.recent_list_widget.setMaximumHeight(150)
        recent_layout.addWidget(self.recent_list_widget)

        clear_btn = QPushButton("Clear Recent History", self)
        clear_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_btn)

        splitter.addWidget(recent_group)

        layout.addWidget(splitter)

    def _connect_signals(self):
        self.search_input.textChanged.connect(self.filter_mods)
        self.case_sensitive_cb.stateChanged.connect(lambda: self.filter_mods(self.search_input.text()))
        self.mod_list_widget.itemClicked.connect(self._on_mod_selected)
        self.mod_list_widget.itemDoubleClicked.connect(self._on_mod_double_clicked)
        self.recent_list_widget.itemClicked.connect(self._on_recent_selected)
        self.recent_list_widget.itemDoubleClicked.connect(self._on_mod_double_clicked)

    def _load_recent_mods(self):
        self.recent_mods = self.settings.value(f"{self.SETTINGS_KEY}/RecentMods", [], type=list)
        self._update_recent_list()

    def _save_recent_mods(self):
        self.settings.setValue(f"{self.SETTINGS_KEY}/RecentMods", self.recent_mods)
        self.settings.sync()

    def _update_recent_list(self):
        self.recent_list_widget.clear()
        for mod_data in self.recent_mods:
            if isinstance(mod_data, dict):
                display_name = mod_data.get("display", "")
                internal_name = mod_data.get("internal", "")
            else:
                display_name = internal_name = mod_data

            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, internal_name)
            self.recent_list_widget.addItem(item)

    def _add_to_recent(self, display_name: str, internal_name: str):
        mod_data = {"display": display_name, "internal": internal_name}

        self.recent_mods = [
            m for m in self.recent_mods
            if not (isinstance(m, dict) and m.get("internal") == internal_name)
        ]

        self.recent_mods.insert(0, mod_data)
        self.recent_mods = self.recent_mods[:self.MAX_RECENT_ITEMS]

        self._save_recent_mods()
        self._update_recent_list()

    def _clear_recent(self):
        self.recent_mods = []
        self._save_recent_mods()
        self._update_recent_list()
        self.mod_selected.emit("Recent history cleared")

    def load_mods(self):
        self.mod_list_widget.clear()
        all_mods = self.mod_list.allMods()

        for internal_name in all_mods:
            if self.mod_list.state(internal_name) & mobase.ModState.EXISTS:
                display_name = self.mod_list.displayName(internal_name)

                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, internal_name)

                is_separator = self._is_separator(internal_name, display_name)

                if is_separator:
                    clean_name = self._clean_separator_name(display_name)
                    item.setText(clean_name.upper())

                    font = QFont()
                    font.setBold(True)
                    font.setPointSize(font.pointSize() + 1)
                    item.setFont(font)
                    item.setData(Qt.ItemDataRole.UserRole + 1, True)
                else:
                    item.setText(display_name)
                    item.setData(Qt.ItemDataRole.UserRole + 1, False)

                self.mod_list_widget.addItem(item)

        self._update_results_count()
        self._loaded = True

    def refresh_if_needed(self):
        self.load_mods()

    def _is_separator(self, internal_name: str, display_name: str) -> bool:
        name_lower = internal_name.lower()
        display_lower = display_name.lower()

        return (
            name_lower.endswith("_separator")
            or "_separator" in name_lower
            or display_name.startswith("---")
            or display_name.startswith("===")
            or display_name.startswith("***")
            or "separator" in display_lower
        )

    def _clean_separator_name(self, name: str) -> str:
        clean = name

        for suffix in ["_separator", "_Separator", "_SEPARATOR"]:
            if clean.endswith(suffix):
                clean = clean[: -len(suffix)]
                break

        for prefix in ["---", "===", "***", "///", "###"]:
            clean = clean.strip(prefix[0])

        clean = clean.replace("_", " ")
        return clean.strip()

    def filter_mods(self, text: str):
        case_sensitive = self.case_sensitive_cb.isChecked()
        search_text = text if case_sensitive else text.lower()

        visible_count = 0

        for i in range(self.mod_list_widget.count()):
            item = self.mod_list_widget.item(i)
            item_text = item.text() if case_sensitive else item.text().lower()

            matches = search_text in item_text
            item.setHidden(not matches)

            if matches:
                visible_count += 1

        self._update_results_count(visible_count if text else None)

    def _update_results_count(self, filtered_count: int = None):
        total = self.mod_list_widget.count()

        if filtered_count is not None:
            self.results_label.setText(f"{filtered_count} of {total} mods shown")
        else:
            self.results_label.setText(f"{total} mods found")

    def _on_mod_selected(self, item: QListWidgetItem):
        self._select_mod_in_view(item)

    def _on_recent_selected(self, item: QListWidgetItem):
        self._select_mod_in_view(item, add_to_recent=False)

    def _on_mod_double_clicked(self, item: QListWidgetItem):
        self._select_mod_in_view(item)

    def _select_mod_in_view(self, item: QListWidgetItem, add_to_recent: bool = True):
        if not item:
            return

        internal_name = item.data(Qt.ItemDataRole.UserRole)
        display_name = item.text()
        is_separator = item.data(Qt.ItemDataRole.UserRole + 1)

        if not self.mods_view or not self.mods_view.model():
            self.mod_selected.emit("Error: Mods view not available")
            return

        model = self.mods_view.model()
        matches = None

        search_names = []

        original_display = self.mod_list.displayName(internal_name)
        search_names.append(original_display)

        search_names.append(internal_name)

        if is_separator:
            search_names.append(display_name)

            if not internal_name.lower().endswith("_separator"):
                search_names.append(f"{internal_name}_separator")

            for suffix in ["_separator", "_Separator", "_SEPARATOR"]:
                if internal_name.endswith(suffix):
                    search_names.append(internal_name[: -len(suffix)])
                    break

        seen = set()
        unique_names = []
        for name in search_names:
            if name and name not in seen:
                seen.add(name)
                unique_names.append(name)

        for search_name in unique_names:
            matches = model.match(
                model.index(0, 0),
                Qt.ItemDataRole.DisplayRole,
                search_name,
                1,
                Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
            )

            if matches:
                break

            matches = model.match(
                model.index(0, 0),
                Qt.ItemDataRole.DisplayRole,
                search_name,
                1,
                Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive,
            )

            if matches:
                break

        if matches:
            index = matches[0]
            parent = index.parent()

            if parent.isValid():
                self.mods_view.expand(parent)

            self.mods_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.mods_view.setCurrentIndex(index)
            self.mods_view.setFocus()

            if add_to_recent:
                self._add_to_recent(display_name, internal_name)

            self.mod_selected.emit(f"Selected: {original_display}")
        else:
            self.mod_selected.emit(
                f"Could not find: {internal_name} (tried: {', '.join(unique_names[:3])})",
            )

    def handle_key_press(self, key: int) -> bool:
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.search_input.hasFocus():
                for i in range(self.mod_list_widget.count()):
                    item = self.mod_list_widget.item(i)
                    if not item.isHidden():
                        self.mod_list_widget.setCurrentItem(item)
                        self._on_mod_selected(item)
                        break
            else:
                selected = self.mod_list_widget.selectedItems()
                if selected:
                    self._on_mod_selected(selected[0])
            return True
        elif key == Qt.Key.Key_Down and self.search_input.hasFocus():
            self.mod_list_widget.setFocus()
            if self.mod_list_widget.count() > 0:
                for i in range(self.mod_list_widget.count()):
                    item = self.mod_list_widget.item(i)
                    if not item.isHidden():
                        self.mod_list_widget.setCurrentItem(item)
                        break
            return True
        return False

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()


class PluginSearchTab(QWidget):
    """Tab for searching plugins"""

    SETTINGS_KEY = "FullModSearch"
    MAX_RECENT_ITEMS = 10

    plugin_selected = pyqtSignal(str)

    def __init__(self, parent, plugins_view: "QTreeView", plugin_list: "mobase.IPluginList"):
        super().__init__(parent)
        self.plugins_view = plugins_view
        self.plugin_list = plugin_list
        self.settings = QSettings("ModOrganizer2", "FullModSearchPlugin")
        self._loaded = False

        self._setup_ui()
        self._load_recent_plugins()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        search_layout = QHBoxLayout()

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Enter plugin name to search...")
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        self.case_sensitive_cb = QCheckBox("Case Sensitive", self)
        search_layout.addWidget(self.case_sensitive_cb)

        layout.addLayout(search_layout)

        filter_layout = QHBoxLayout()

        self.show_esp_cb = QCheckBox("ESP", self)
        self.show_esp_cb.setChecked(True)
        filter_layout.addWidget(self.show_esp_cb)

        self.show_esm_cb = QCheckBox("ESM", self)
        self.show_esm_cb.setChecked(True)
        filter_layout.addWidget(self.show_esm_cb)

        self.show_esl_cb = QCheckBox("ESL", self)
        self.show_esl_cb.setChecked(True)
        filter_layout.addWidget(self.show_esl_cb)

        self.show_active_only_cb = QCheckBox("Active Only", self)
        filter_layout.addWidget(self.show_active_only_cb)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.plugin_list_widget = QListWidget(self)
        self.plugin_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plugin_list_widget.setAlternatingRowColors(True)
        results_layout.addWidget(self.plugin_list_widget)

        self.results_label = QLabel("0 plugins found", self)
        results_layout.addWidget(self.results_label)

        splitter.addWidget(results_group)

        recent_group = QGroupBox("Recent Selections", self)
        recent_group.setFlat(True)
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(4, 2, 4, 2)

        self.recent_list_widget = QListWidget(self)
        self.recent_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recent_list_widget.setAlternatingRowColors(True)
        self.recent_list_widget.setMaximumHeight(120)
        recent_layout.addWidget(self.recent_list_widget)

        clear_btn = QPushButton("Clear History", self)
        clear_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_btn)

        splitter.addWidget(recent_group)

        layout.addWidget(splitter)

    def _connect_signals(self):
        self.search_input.textChanged.connect(self.filter_plugins)
        self.case_sensitive_cb.stateChanged.connect(self._refresh_filter)
        self.show_esp_cb.stateChanged.connect(self._refresh_filter)
        self.show_esm_cb.stateChanged.connect(self._refresh_filter)
        self.show_esl_cb.stateChanged.connect(self._refresh_filter)
        self.show_active_only_cb.stateChanged.connect(self._refresh_filter)

        self.plugin_list_widget.itemClicked.connect(self._on_plugin_selected)
        self.plugin_list_widget.itemDoubleClicked.connect(self._on_plugin_double_clicked)
        self.recent_list_widget.itemClicked.connect(self._on_recent_selected)
        self.recent_list_widget.itemDoubleClicked.connect(self._on_plugin_double_clicked)

    def _refresh_filter(self):
        self.filter_plugins(self.search_input.text())

    def _load_recent_plugins(self):
        self.recent_plugins = self.settings.value(f"{self.SETTINGS_KEY}/RecentPlugins", [], type=list)
        self._update_recent_list()

    def _save_recent_plugins(self):
        self.settings.setValue(f"{self.SETTINGS_KEY}/RecentPlugins", self.recent_plugins)
        self.settings.sync()

    def _update_recent_list(self):
        self.recent_list_widget.clear()
        for plugin_name in self.recent_plugins:
            item = QListWidgetItem(plugin_name)
            item.setData(Qt.ItemDataRole.UserRole, plugin_name)
            self.recent_list_widget.addItem(item)

    def _add_to_recent(self, plugin_name: str):
        if plugin_name in self.recent_plugins:
            self.recent_plugins.remove(plugin_name)

        self.recent_plugins.insert(0, plugin_name)
        self.recent_plugins = self.recent_plugins[:self.MAX_RECENT_ITEMS]

        self._save_recent_plugins()
        self._update_recent_list()

    def _clear_recent(self):
        self.recent_plugins = []
        self._save_recent_plugins()
        self._update_recent_list()
        self.plugin_selected.emit("Recent history cleared")

    def load_plugins(self):
        self.plugin_list_widget.clear()
        plugin_names = self.plugin_list.pluginNames()

        for plugin_name in plugin_names:
            state = self.plugin_list.state(plugin_name)

            if state == mobase.PluginState.MISSING:
                continue

            item = QListWidgetItem(plugin_name)
            item.setData(Qt.ItemDataRole.UserRole, plugin_name)

            extension = plugin_name.lower().split(".")[-1] if "." in plugin_name else ""
            item.setData(Qt.ItemDataRole.UserRole + 1, extension)
            item.setData(Qt.ItemDataRole.UserRole + 2, state == mobase.PluginState.ACTIVE)

            font = QFont()
            if state == mobase.PluginState.ACTIVE:
                font.setBold(True)
            elif extension == "esm":
                font.setBold(True)
            item.setFont(font)

            self.plugin_list_widget.addItem(item)

        self._update_results_count()
        self._loaded = True

    def refresh_if_needed(self):
        self.load_plugins()

    def filter_plugins(self, text: str):
        case_sensitive = self.case_sensitive_cb.isChecked()
        show_esp = self.show_esp_cb.isChecked()
        show_esm = self.show_esm_cb.isChecked()
        show_esl = self.show_esl_cb.isChecked()
        active_only = self.show_active_only_cb.isChecked()

        search_text = text if case_sensitive else text.lower()
        visible_count = 0

        for i in range(self.plugin_list_widget.count()):
            item = self.plugin_list_widget.item(i)
            item_text = item.text() if case_sensitive else item.text().lower()
            extension = item.data(Qt.ItemDataRole.UserRole + 1)
            is_active = item.data(Qt.ItemDataRole.UserRole + 2)

            text_match = search_text in item_text

            type_match = (
                (extension == "esp" and show_esp)
                or (extension == "esm" and show_esm)
                or (extension == "esl" and show_esl)
                or (extension not in ["esp", "esm", "esl"])
            )

            active_match = not active_only or is_active

            visible = text_match and type_match and active_match
            item.setHidden(not visible)

            if visible:
                visible_count += 1

        self._update_results_count(visible_count if text or active_only else None)

    def _update_results_count(self, filtered_count: int = None):
        total = self.plugin_list_widget.count()

        if filtered_count is not None:
            self.results_label.setText(f"{filtered_count} of {total} plugins shown")
        else:
            self.results_label.setText(f"{total} plugins found")

    def _on_plugin_selected(self, item: QListWidgetItem):
        self._select_plugin_in_view(item)

    def _on_recent_selected(self, item: QListWidgetItem):
        self._select_plugin_in_view(item, add_to_recent=False)

    def _on_plugin_double_clicked(self, item: QListWidgetItem):
        self._select_plugin_in_view(item)

    def _select_plugin_in_view(self, item: QListWidgetItem, add_to_recent: bool = True):
        if not item:
            return

        plugin_name = item.data(Qt.ItemDataRole.UserRole)

        if not self.plugins_view or not self.plugins_view.model():
            self.plugin_selected.emit("Error: Plugins view not available")
            return

        model = self.plugins_view.model()
        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            plugin_name,
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )

        if matches:
            index = matches[0]
            self.plugins_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.plugins_view.setCurrentIndex(index)
            self.plugins_view.setFocus()

            if add_to_recent:
                self._add_to_recent(plugin_name)

            self.plugin_selected.emit(f"Selected: {plugin_name}")
        else:
            self.plugin_selected.emit(f"Could not find plugin: {plugin_name}")

    def handle_key_press(self, key: int) -> bool:
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.search_input.hasFocus():
                for i in range(self.plugin_list_widget.count()):
                    item = self.plugin_list_widget.item(i)
                    if not item.isHidden():
                        self.plugin_list_widget.setCurrentItem(item)
                        self._on_plugin_selected(item)
                        break
            else:
                selected = self.plugin_list_widget.selectedItems()
                if selected:
                    self._on_plugin_selected(selected[0])
            return True
        elif key == Qt.Key.Key_Down and self.search_input.hasFocus():
            self.plugin_list_widget.setFocus()
            if self.plugin_list_widget.count() > 0:
                for i in range(self.plugin_list_widget.count()):
                    item = self.plugin_list_widget.item(i)
                    if not item.isHidden():
                        self.plugin_list_widget.setCurrentItem(item)
                        break
            return True
        return False

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()


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

        self.active_mods_only_cb = QCheckBox("Active Mods Only", self)
        btn_layout.addWidget(self.active_mods_only_cb)

        search_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        search_layout.addWidget(self.progress_bar)

        layout.addWidget(search_group)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.results_tree = QTreeWidget(self)
        self.results_tree.setHeaderLabels(["Mod / File Path", "Full Path"])
        self.results_tree.setColumnWidth(0, 400)
        self.results_tree.setAlternatingRowColors(True)
        self.results_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        results_layout.addWidget(self.results_tree)

        info_layout = QHBoxLayout()
        self.results_label = QLabel("No results", self)
        info_layout.addWidget(self.results_label)

        info_layout.addStretch()

        self.goto_mod_btn = QPushButton("Go to Mod", self)
        self.goto_mod_btn.setEnabled(False)
        info_layout.addWidget(self.goto_mod_btn)

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
        self.recent_list.setMaximumHeight(100)
        self.recent_list.setAlternatingRowColors(True)
        recent_layout.addWidget(self.recent_list)

        clear_recent_btn = QPushButton("Clear History", self)
        clear_recent_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_recent_btn)

        splitter.addWidget(recent_group)

        layout.addWidget(splitter)

    def _connect_signals(self):
        self.search_btn.clicked.connect(self._start_search)
        self.cancel_btn.clicked.connect(self._cancel_search)
        self.clear_btn.clicked.connect(self._clear_results)

        self.search_input.returnPressed.connect(self._start_search)

        self.results_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self.goto_mod_btn.clicked.connect(self._goto_selected_mod)
        self.open_folder_btn.clicked.connect(self._open_selected_folder)

        self.recent_list.itemDoubleClicked.connect(self._on_recent_clicked)

    def _load_recent_searches(self):
        self.recent_searches = self.settings.value(
            f"{self.SETTINGS_KEY}/RecentFileSearches", [], type=list,
        )
        self._update_recent_list()

    def _save_recent_searches(self):
        self.settings.setValue(
            f"{self.SETTINGS_KEY}/RecentFileSearches", self.recent_searches,
        )
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
        self.file_selected.emit("Recent searches cleared")

    def _get_selected_extensions(self) -> list:
        preset = self.extension_combo.currentText()
        extensions = self.EXTENSION_PRESETS.get(preset, []).copy()

        custom = self.custom_ext_input.text().strip()
        if custom:
            for ext in custom.split(","):
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
        )

        self._search_worker.progress.connect(self._on_search_progress)
        self._search_worker.result_found.connect(self._on_result_found)
        self._search_worker.finished_search.connect(self._on_search_finished)

        self._search_worker.start()

    def _cancel_search(self):
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self.file_selected.emit("Search cancelled")

    def _clear_results(self):
        self.results_tree.clear()
        self._search_results = {}
        self.results_label.setText("No results")
        self.goto_mod_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)

    def _on_search_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.file_selected.emit(f"Searching... ({current}/{total} mods)")

    def _on_result_found(self, mod_name: str, relative_path: str, full_path: str):
        if self.active_mods_only_cb.isChecked():
            state = self._mod_list.state(mod_name)
            if not (state & mobase.ModState.ACTIVE):
                return

        if mod_name not in self._search_results:
            self._search_results[mod_name] = []

        self._search_results[mod_name].append((relative_path, full_path))
        self._update_results_tree()

    def _update_results_tree(self):
        self.results_tree.clear()

        total_files = 0

        for mod_name, files in sorted(self._search_results.items()):
            mod_item = QTreeWidgetItem([mod_name, ""])

            font = QFont()
            font.setBold(True)
            mod_item.setFont(0, font)
            mod_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "mod", "name": mod_name})

            for relative_path, full_path in files:
                file_item = QTreeWidgetItem([relative_path, full_path])
                file_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "file",
                    "mod_name": mod_name,
                    "relative_path": relative_path,
                    "full_path": full_path,
                })

                mod_item.addChild(file_item)
                total_files += 1

            self.results_tree.addTopLevelItem(mod_item)

        mod_count = len(self._search_results)
        self.results_label.setText(f"{total_files} files in {mod_count} mods")

    def _is_separator(self, mod_name: str) -> bool:
        name_lower = mod_name.lower()
        display_name = self._mod_list.displayName(mod_name)

        return (
            "_separator" in name_lower
            or name_lower.endswith("_separator")
            or display_name.startswith("---")
            or "separator" in name_lower
        )

    def _on_search_finished(self, total_results: int):
        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

        mod_count = len(self._search_results)
        self.file_selected.emit(f"Search complete: {total_results} files in {mod_count} mods")

        if mod_count <= 20:
            self.results_tree.expandAll()

    def _on_selection_changed(self):
        items = self.results_tree.selectedItems()
        has_selection = len(items) > 0

        self.goto_mod_btn.setEnabled(has_selection)
        self.open_folder_btn.setEnabled(has_selection)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "mod":
            self._goto_mod(data["name"])
        else:
            self._goto_mod(data["mod_name"])

    def _goto_selected_mod(self):
        items = self.results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        mod_name = data.get("name") or data.get("mod_name")
        if mod_name:
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

    def _open_selected_folder(self):
        items = self.results_tree.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "file":
            folder_path = os.path.dirname(data["full_path"])
        else:
            mod_info = self._organizer.getMod(data["name"])
            if mod_info:
                folder_path = mod_info.absolutePath()
            else:
                return

        if os.path.exists(folder_path):
            import subprocess
            import sys

            if sys.platform == "win32":
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
        pass

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


from .workers import FileSearchWorker as _FileSearchWorker
from .tabs_mods_plugins import ModNameSearchTab as _ModNameSearchTab, PluginSearchTab as _PluginSearchTab, ModNotesSearchTab as _ModNotesSearchTab
from .content_filter_tab import ContentFilterTab as _ContentFilterTab
from .tabs_files import FileSearchTab as _FileSearchTab
from .tabs_nif import NifTextureSearchTab as _NifTextureSearchTab

FileSearchWorker = _FileSearchWorker
ModNameSearchTab = _ModNameSearchTab
PluginSearchTab = _PluginSearchTab
ModNotesSearchTab = _ModNotesSearchTab
ContentFilterTab = _ContentFilterTab
FileSearchTab = _FileSearchTab
NifTextureSearchTab = _NifTextureSearchTab

__all__ = [
    "FileSearchWorker",
    "NifTextureSearchTab",
    "ModNameSearchTab",
    "PluginSearchTab",
    "ModNotesSearchTab",
    "ContentFilterTab",
    "FileSearchTab",
]
