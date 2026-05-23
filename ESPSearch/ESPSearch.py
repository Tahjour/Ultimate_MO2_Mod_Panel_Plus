import csv
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import mobase
from PyQt6.QtCore import QByteArray, QEvent, QPoint, QRect, QSettings, QSize, QStringListModel, Qt, QThread, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .engine.data_types import PluginFile, Record
from .engine.localization import decode_text
from .engine.plugin_file import create_lazy_index, parse_plugin
from .engine.search_engine import iter_records
from .engine.record_formatter import DetailNode, StructuredSubrecordParser

logger = logging.getLogger(__name__)


def make_plugin_icon(size: int = 24) -> QIcon:
    color = QColor("#d67500")
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, 1.5))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    font = QFont("Arial", max(size // 3, 6), QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "ES")
    painter.end()
    return QIcon(px)


@dataclass
class PluginEntry:
    name: str
    path: str
    size: int
    mtime: float
    active: bool
    origin: str = ""


@dataclass
class SearchResultRow:
    signature: str
    form_id: int
    record_name: str
    plugin_name: str
    plugin_path: str
    matched_text: str = ""


@dataclass
class CachedPluginBundle:
    path: str
    mtime: float
    size: int
    plugin: PluginFile
    author: str = ""
    record_blob_cache: Dict[Tuple[str, int], str] = field(default_factory=dict)
    signatures: Set[str] = field(default_factory=set)


class SearchWorker(QThread):
    progress_changed = Signal(int, str)
    results_ready = Signal(list)
    error_raised = Signal(str)

    def __init__(
        self,
        owner: "EspSearchPanel",
        plugin_entries: List[PluginEntry],
        query_text: str,
        use_regex: bool,
        record_types: List[str],
        selected_only: bool,
        selected_plugin: Optional[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._owner = owner
        self._plugin_entries = plugin_entries
        self._query_text = query_text
        self._use_regex = use_regex
        self._record_types = {x.strip().upper() for x in record_types if x.strip()}
        self._selected_only = selected_only
        self._selected_plugin = selected_plugin
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            started = time.time()
            if self._selected_only and self._selected_plugin:
                selected = [x for x in self._plugin_entries if x.name == self._selected_plugin]
                targets = selected[:1]
            else:
                targets = list(self._plugin_entries)
            total = max(len(targets), 1)
            matcher = self._build_matcher(self._query_text, self._use_regex)
            results: List[SearchResultRow] = []
            for idx, entry in enumerate(targets):
                if self._cancel_requested:
                    break
                progress = int((idx / total) * 100)
                self.progress_changed.emit(progress, f"Scanning {entry.name}")
                bundle = self._owner.get_or_parse_bundle(entry.path, entry.name)
                if bundle is None:
                    continue
                plugin_results = self._scan_plugin(bundle, entry.name, matcher)
                results.extend(plugin_results)
            if not self._cancel_requested:
                elapsed = time.time() - started
                self.progress_changed.emit(100, f"Done in {elapsed:.2f}s")
            self.results_ready.emit(results)
        except Exception as exc:
            self.error_raised.emit(str(exc))

    def _build_matcher(self, text: str, use_regex: bool):
        if use_regex:
            pattern = re.compile(text, re.IGNORECASE)
            return lambda s: bool(pattern.search(s))
        needle = text.lower()
        return lambda s: needle in s.lower()

    def _scan_plugin(self, bundle: CachedPluginBundle, plugin_name: str, matcher):
        rows: List[SearchResultRow] = []
        is_empty_query = not self._query_text.strip()
        for record in iter_records(bundle.plugin.children):
            if self._cancel_requested:
                break
            if self._record_types and record.signature.upper() not in self._record_types:
                continue
            if not is_empty_query:
                blob = self._owner.get_record_blob(bundle, record)
                if not matcher(blob):
                    continue
            rows.append(
                SearchResultRow(
                    signature=record.signature,
                    form_id=record.form_id,
                    record_name=self._owner.resolve_record_name(bundle.plugin, record),
                    plugin_name=plugin_name,
                    plugin_path=bundle.path,
                    matched_text=self._query_text,
                )
            )
        return rows


class CompareDialog(QDialog):
    def __init__(self, title: str, rows: List[Tuple[str, str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 320)
        layout = QVBoxLayout(self)
        table = QTableWidget(self)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Plugin", "Editor ID", "Name"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                table.setItem(row_idx, col_idx, QTableWidgetItem(value))
        layout.addWidget(table)
        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class EspSearchPanel(QWidget):
    def __init__(self, organizer: mobase.IOrganizer, parent=None) -> None:
        super().__init__(parent)
        self._organizer = organizer
        self._settings = QSettings("ModOrganizer2", "FlyoutEspSearch")
        self._plugins: List[PluginEntry] = []
        self._plugins_by_name: Dict[str, PluginEntry] = {}
        self._bundle_cache: Dict[str, CachedPluginBundle] = {}
        self._lazy_index_cache: Dict[str, object] = {}
        self._search_cache: Dict[str, List[SearchResultRow]] = {}
        self._record_lookup: Dict[Tuple[str, str, int], Record] = {}
        self._current_results: List[SearchResultRow] = []
        self._worker: Optional[SearchWorker] = None
        self._plugin_path_cache: Dict[str, str] = {}
        self._history: List[str] = []
        self._history_model = QStringListModel(self)
        self._history_completer = QCompleter(self._history_model, self)
        self._history_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._history_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._plugin_name_model = QStringListModel(self)
        self._plugin_name_completer = QCompleter(self._plugin_name_model, self)
        self._plugin_name_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._plugin_name_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._view_state_save_timer = QTimer(self)
        self._view_state_save_timer.setSingleShot(True)
        self._view_state_save_timer.setInterval(250)
        self._view_state_save_timer.timeout.connect(self._save_view_state)
        self._build_ui()
        self._load_history()
        self._restore_view_state()
        self.refresh_plugins()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(8)
        top_grid.setVerticalSpacing(6)

        self.plugin_search_input = QLineEdit(self)
        self.plugin_search_input.setPlaceholderText("Quick plugin filter...")
        self.plugin_combo = QComboBox(self)
        self.plugin_combo.setMinimumWidth(260)
        self.plugin_combo.currentTextChanged.connect(self._on_plugin_changed)
        self.plugin_combo.currentTextChanged.connect(self._schedule_view_state_save)
        self.plugin_search_input.textChanged.connect(self._filter_plugin_combo)
        self.plugin_search_input.setCompleter(self._plugin_name_completer)

        self.query_input = QLineEdit(self)
        self.query_input.setPlaceholderText("Search text or regex pattern")
        self.query_input.returnPressed.connect(self.start_search)
        self.query_input.textChanged.connect(self._schedule_view_state_save)
        self.query_input.setCompleter(self._history_completer)

        self.regex_check = QCheckBox("Regex", self)
        self.regex_check.setChecked(False)
        self.regex_check.toggled.connect(self._schedule_view_state_save)

        self.scope_selected_check = QCheckBox("Selected plugin only", self)
        self.scope_selected_check.setChecked(True)
        self.scope_selected_check.toggled.connect(self._on_scope_changed)
        self.scope_selected_check.toggled.connect(self._schedule_view_state_save)

        self.types_input = QComboBox(self)
        self.types_input.setEditable(True)
        self.types_input.addItem("ALL types")
        self.types_input.currentTextChanged.connect(self._schedule_view_state_save)
        if self.types_input.lineEdit():
            self.types_input.lineEdit().setPlaceholderText("NPC_, WEAP, SPEL...")

        self.results_filter_input = QLineEdit(self)
        self.results_filter_input.setPlaceholderText("Filter results...")
        self.results_filter_input.textChanged.connect(self._apply_result_filter)
        self.results_filter_input.textChanged.connect(self._schedule_view_state_save)

        self.search_btn = QPushButton("Search", self)
        self.search_btn.clicked.connect(self.start_search)
        self.search_btn.clicked.connect(self._schedule_view_state_save)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.cancel_search)
        self.cancel_btn.setEnabled(False)

        self.refresh_btn = QPushButton("Refresh Plugins", self)
        self.refresh_btn.clicked.connect(self.refresh_plugins)

        top_grid.addWidget(QLabel("Plugin Filter"), 0, 0)
        top_grid.addWidget(self.plugin_search_input, 0, 1)
        top_grid.addWidget(QLabel("Plugin"), 1, 0)
        top_grid.addWidget(self.plugin_combo, 1, 1)
        top_grid.addWidget(QLabel("Query"), 2, 0)
        top_grid.addWidget(self.query_input, 2, 1)
        top_grid.addWidget(self.regex_check, 2, 2)
        top_grid.addWidget(self.scope_selected_check, 2, 3)
        top_grid.addWidget(QLabel("Record Types"), 3, 0)
        top_grid.addWidget(self.types_input, 3, 1)
        top_grid.addWidget(QLabel("Filter"), 3, 2)
        top_grid.addWidget(self.results_filter_input, 3, 3)
        top_grid.addWidget(self.search_btn, 4, 1)
        top_grid.addWidget(self.cancel_btn, 4, 3)
        top_grid.addWidget(self.refresh_btn, 4, 2)
        root.addLayout(top_grid)

        meta_layout = QHBoxLayout()
        self.meta_size = QLabel("Size: -", self)
        self.meta_mtime = QLabel("Modified: -", self)
        self.meta_author = QLabel("Author: -", self)
        meta_layout.addWidget(self.meta_size)
        meta_layout.addWidget(self.meta_mtime)
        meta_layout.addWidget(self.meta_author)
        meta_layout.addStretch()
        root.addLayout(meta_layout)

        self.progress_label = QLabel("Idle", self)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress_label)
        root.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter = splitter
        self.results_table = QTableWidget(self)
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Record Type", "ID", "Name", "Containing Plugin"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.itemSelectionChanged.connect(self._on_result_selected)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._open_results_menu)
        splitter.addWidget(self.results_table)

        self.details_tree = QTreeWidget(self)
        self.details_tree.setColumnCount(3)
        self.details_tree.setHeaderLabels(["Field", "Type", "Value"])
        self.details_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.details_tree.customContextMenuRequested.connect(self._open_tree_menu)
        self.details_tree.itemDoubleClicked.connect(self._on_detail_double_clicked)
        self._match_background = self.palette().color(QPalette.ColorRole.Highlight)
        self._ref_foreground = self.palette().color(QPalette.ColorRole.Link)
        splitter.addWidget(self.details_tree)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.splitterMoved.connect(self._schedule_view_state_save)
        self.results_table.horizontalHeader().sectionResized.connect(self._schedule_view_state_save)
        self.details_tree.header().sectionResized.connect(self._schedule_view_state_save)
        root.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.export_csv_btn = QPushButton("Export CSV", self)
        self.export_json_btn = QPushButton("Export JSON", self)
        self.compare_btn = QPushButton("Compare Similar", self)
        self.copy_structure_btn = QPushButton("Copy Structure", self)
        self.close_btn = QPushButton("Close", self)
        self.export_csv_btn.clicked.connect(self.export_csv)
        self.export_json_btn.clicked.connect(self.export_json)
        self.compare_btn.clicked.connect(self.compare_selected_record)
        self.copy_structure_btn.clicked.connect(self.copy_selected_structure)
        self.close_btn.clicked.connect(self._close_parent_dialog)
        bottom.addWidget(self.export_csv_btn)
        bottom.addWidget(self.export_json_btn)
        bottom.addWidget(self.compare_btn)
        bottom.addWidget(self.copy_structure_btn)
        bottom.addStretch()
        bottom.addWidget(self.close_btn)
        root.addLayout(bottom)
        self._restore_view_state()

    def _close_parent_dialog(self) -> None:
        dlg = self.window()
        if isinstance(dlg, QDialog):
            dlg.hide()

    def persist_ui_state(self) -> None:
        self._save_view_state()

    def hideEvent(self, event) -> None:
        self._save_view_state()
        super().hideEvent(event)

    def _schedule_view_state_save(self, *_args) -> None:
        self._view_state_save_timer.start()

    def _to_byte_array(self, raw: object) -> Optional[QByteArray]:
        if isinstance(raw, QByteArray):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            return QByteArray(bytes(raw))
        return None

    def _restore_view_state(self) -> None:
        self.blockSignals(True)
        try:
            splitter_state = self._to_byte_array(self._settings.value("ui/main_splitter_state"))
            if splitter_state is not None:
                self.main_splitter.restoreState(splitter_state)
            results_header_state = self._to_byte_array(self._settings.value("ui/results_header_state"))
            if results_header_state is not None:
                self.results_table.horizontalHeader().restoreState(results_header_state)
            details_header_state = self._to_byte_array(self._settings.value("ui/details_tree_header_state"))
            if details_header_state is not None:
                self.details_tree.header().restoreState(details_header_state)

            # Restore input fields
            self.query_input.setText(self._settings.value("input/query", ""))
            self.regex_check.setChecked(self._settings.value("input/regex", False, type=bool))
            self.scope_selected_check.setChecked(self._settings.value("input/scope_selected", True, type=bool))
            self.results_filter_input.setText(self._settings.value("input/filter", ""))
            saved_type = self._settings.value("input/record_type", "ALL types")
            if saved_type:
                self.types_input.setCurrentText(saved_type)
        finally:
            self.blockSignals(False)

    def _save_view_state(self) -> None:
        self._settings.setValue("ui/main_splitter_state", self.main_splitter.saveState())
        self._settings.setValue("ui/results_header_state", self.results_table.horizontalHeader().saveState())
        self._settings.setValue("ui/details_tree_header_state", self.details_tree.header().saveState())
        
        # Save input fields
        self._settings.setValue("input/query", self.query_input.text())
        self._settings.setValue("input/regex", self.regex_check.isChecked())
        self._settings.setValue("input/scope_selected", self.scope_selected_check.isChecked())
        self._settings.setValue("input/filter", self.results_filter_input.text())
        self._settings.setValue("input/record_type", self.types_input.currentText())
        self._settings.setValue("input/last_plugin", self.plugin_combo.currentText())

    def refresh_plugins(self) -> None:
        last_plugin = self._settings.value("input/last_plugin", "")
        self._plugins = self._collect_active_plugins()
        self._plugins_by_name = {p.name: p for p in self._plugins}
        self._plugin_name_model.setStringList([p.name for p in self._plugins])
        self._refill_plugin_combo(self._plugins)
        
        if last_plugin and last_plugin in self._plugins_by_name:
            self.plugin_combo.setCurrentText(last_plugin)
            
        self._update_record_types_combo()
        self.progress_label.setText(f"Loaded {len(self._plugins)} active plugins")

    def _collect_active_plugins(self) -> List[PluginEntry]:
        plugin_list = self._organizer.pluginList()
        entries: List[PluginEntry] = []
        for name in plugin_list.pluginNames():
            lower = name.lower()
            if not (lower.endswith(".esp") or lower.endswith(".esm") or lower.endswith(".esl")):
                continue
            state = plugin_list.state(name)
            if state != mobase.PluginState.ACTIVE:
                continue
            path = self._resolve_plugin_path(name)
            if not path or not os.path.exists(path):
                continue
            try:
                stat = os.stat(path)
                origin = plugin_list.origin(name) or ""
                entries.append(
                    PluginEntry(
                        name=name,
                        path=path,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        active=True,
                        origin=origin,
                    )
                )
            except OSError:
                continue
        entries.sort(key=lambda x: x.name.lower())
        return entries

    def _resolve_plugin_path(self, plugin_name: str) -> Optional[str]:
        cached = self._plugin_path_cache.get(plugin_name)
        if cached and os.path.exists(cached):
            return cached
        plugin_list = self._organizer.pluginList()
        origin = plugin_list.origin(plugin_name) or ""
        candidates: List[str] = []
        mods_path = self._organizer.modsPath()
        if origin:
            candidates.append(os.path.join(mods_path, origin, plugin_name))
            candidates.append(os.path.join(mods_path, origin, "Data", plugin_name))
        overwrite_path = getattr(self._organizer, "overwritePath", None)
        if callable(overwrite_path):
            ov_path = overwrite_path()
            candidates.append(os.path.join(ov_path, plugin_name))
            candidates.append(os.path.join(ov_path, "Data", plugin_name))
        try:
            data_path = self._organizer.managedGame().dataDirectory().path()
            candidates.append(os.path.join(data_path, plugin_name))
        except Exception:
            pass
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                self._plugin_path_cache[plugin_name] = candidate
                return candidate
        if origin:
            mod_root = os.path.join(mods_path, origin)
            if os.path.isdir(mod_root):
                target = plugin_name.lower()
                for root, _, files in os.walk(mod_root):
                    for file_name in files:
                        if file_name.lower() == target:
                            found = os.path.join(root, file_name)
                            self._plugin_path_cache[plugin_name] = found
                            return found
        return None

    def _refill_plugin_combo(self, entries: List[PluginEntry]) -> None:
        current = self.plugin_combo.currentText()
        self.plugin_combo.blockSignals(True)
        self.plugin_combo.clear()
        for entry in entries:
            self.plugin_combo.addItem(entry.name)
        self.plugin_combo.blockSignals(False)
        if current and self.plugin_combo.findText(current) >= 0:
            self.plugin_combo.setCurrentText(current)
        elif self.plugin_combo.count():
            self.plugin_combo.setCurrentIndex(0)
        self._on_plugin_changed(self.plugin_combo.currentText())

    def _filter_plugin_combo(self, text: str) -> None:
        needle = text.strip().lower()
        if not needle:
            self._refill_plugin_combo(self._plugins)
            return
        filtered = [p for p in self._plugins if needle in p.name.lower()]
        self._refill_plugin_combo(filtered)

    def _on_plugin_changed(self, plugin_name: str) -> None:
        entry = self._plugins_by_name.get(plugin_name)
        if not entry:
            self.meta_size.setText("Size: -")
            self.meta_mtime.setText("Modified: -")
            self.meta_author.setText("Author: -")
            return
        self.meta_size.setText(f"Size: {self._format_size(entry.size)}")
        self.meta_mtime.setText(f"Modified: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry.mtime))}")
        bundle = self.get_or_parse_bundle(entry.path, entry.name, parse_for_meta=True)
        author = bundle.author if bundle else ""
        self.meta_author.setText(f"Author: {author or 'Unknown'}")
        self._update_record_types_combo()

    def _on_scope_changed(self, _checked: bool) -> None:
        self._update_record_types_combo()

    def _update_record_types_combo(self) -> None:
        current_type = self.types_input.currentText()
        self.types_input.blockSignals(True)
        self.types_input.clear()
        self.types_input.addItem("ALL types")
        
        signatures = set()
        if self.scope_selected_check.isChecked():
            plugin_name = self.plugin_combo.currentText()
            entry = self._plugins_by_name.get(plugin_name)
            if entry:
                bundle = self.get_or_parse_bundle(entry.path, entry.name)
                if bundle:
                    signatures = bundle.signatures
        else:
            # Union of all active plugins signatures
            for entry in self._plugins:
                bundle = self.get_or_parse_bundle(entry.path, entry.name)
                if bundle:
                    signatures.update(bundle.signatures)
        
        sorted_sigs = sorted(list(signatures))
        for sig in sorted_sigs:
            self.types_input.addItem(sig)
            
        self.types_input.blockSignals(False)
        if current_type and self.types_input.findText(current_type) >= 0:
            self.types_input.setCurrentText(current_type)
        else:
            self.types_input.setCurrentIndex(0)

    def _format_size(self, size_bytes: int) -> str:
        value = float(size_bytes)
        units = ["B", "KB", "MB", "GB"]
        idx = 0
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024
            idx += 1
        return f"{value:.2f} {units[idx]}"

    def start_search(self) -> None:
        query = self.query_input.text().strip()
        if self.regex_check.isChecked() and query:
            try:
                re.compile(query)
            except re.error as exc:
                self.progress_label.setText(f"Regex error: {exc}")
                return
        selected_plugin = self.plugin_combo.currentText().strip()
        if not selected_plugin:
            self.progress_label.setText("No plugin selected")
            return
        selected_only = self.scope_selected_check.isChecked()
        
        type_text = self.types_input.currentText().strip()
        if type_text == "ALL types" or not type_text:
            types = []
        else:
            # If user typed multiple comma-separated types (since it's editable)
            types = [x.strip() for x in type_text.split(",") if x.strip()]
            
        cache_key = self._build_search_key(query, self.regex_check.isChecked(), types, selected_only, selected_plugin)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            self._set_results(cached)
            self.progress_label.setText("Loaded from search cache")
            self.progress.setValue(100)
            self._save_history(query)
            return
        self.cancel_search()
        self.search_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress_label.setText("Starting search...")
        self._worker = SearchWorker(
            owner=self,
            plugin_entries=self._plugins,
            query_text=query,
            use_regex=self.regex_check.isChecked(),
            record_types=types,
            selected_only=selected_only,
            selected_plugin=selected_plugin,
            parent=self,
        )
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.results_ready.connect(lambda rows, key=cache_key: self._on_worker_results(rows, key))
        self._worker.error_raised.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._save_history(query)

    def cancel_search(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
            self.progress_label.setText("Search canceled")
        self._worker = None
        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _build_search_key(self, query: str, regex: bool, types: List[str], selected_only: bool, selected_plugin: str) -> str:
        plugin_fingerprint = "|".join(f"{x.name}:{int(x.mtime)}:{x.size}" for x in self._plugins)
        return json.dumps(
            {
                "query": query,
                "regex": regex,
                "types": sorted([x.upper() for x in types]),
                "selected_only": selected_only,
                "selected_plugin": selected_plugin,
                "plugins": plugin_fingerprint,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _on_progress_changed(self, value: int, text: str) -> None:
        self.progress.setValue(max(0, min(100, value)))
        self.progress_label.setText(text)

    def _on_worker_results(self, rows: List[SearchResultRow], cache_key: str) -> None:
        self._search_cache[cache_key] = list(rows)
        self._set_results(rows)

    def _on_worker_error(self, message: str) -> None:
        self.progress_label.setText(f"Error: {message}")

    def _on_worker_finished(self) -> None:
        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None

    def _set_results(self, rows: List[SearchResultRow]) -> None:
        self._current_results = list(rows)
        self._apply_result_filter()
        self.progress_label.setText(f"Found {len(rows)} matches")

    def _apply_result_filter(self) -> None:
        needle = self.results_filter_input.text().strip().lower()
        if needle:
            rows = []
            for x in self._current_results:
                # Check signature, form_id (as hex string), record_name, and plugin_name
                searchable_text = f"{x.signature} 0x{x.form_id:08X} {x.record_name} {x.plugin_name}".lower()
                if needle in searchable_text:
                    rows.append(x)
        else:
            rows = list(self._current_results)
        self.results_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [row.signature, f"0x{row.form_id:08X}", row.record_name, row.plugin_name]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row_idx)
                self.results_table.setItem(row_idx, col_idx, item)
            if row.matched_text:
                for col_idx in range(4):
                    it = self.results_table.item(row_idx, col_idx)
                    if it:
                        it.setBackground(self._match_background)
        self.results_table.resizeRowsToContents()
        self.details_tree.clear()
        self.results_table.setProperty("filtered_rows", rows)

    def _get_filtered_rows(self) -> List[SearchResultRow]:
        rows = self.results_table.property("filtered_rows")
        if isinstance(rows, list):
            return rows
        return []

    def _on_result_selected(self) -> None:
        selected = self.results_table.selectedItems()
        if not selected:
            return
        row_idx = selected[0].row()
        rows = self._get_filtered_rows()
        if row_idx < 0 or row_idx >= len(rows):
            return
        result_row = rows[row_idx]
        bundle = self.get_or_parse_bundle(result_row.plugin_path, result_row.plugin_name)
        if bundle is None:
            return
        key = (result_row.plugin_path, result_row.signature, result_row.form_id)
        record = self._record_lookup.get(key)
        if record is None:
            record = bundle.plugin.record_map.get((result_row.signature, result_row.form_id))
        if record is None:
            return
        self._fill_details_tree(bundle.plugin, record, result_row.matched_text)

    def _fill_details_tree(self, plugin: PluginFile, record: Record, query_text: str) -> None:
        self.details_tree.clear()
        parser = StructuredSubrecordParser(record, plugin)
        nodes = parser.iter_nodes()
        for node in nodes:
            self._add_detail_node(None, node, query_text)
        self.details_tree.expandToDepth(1)

    def _add_detail_node(self, parent_item: Optional[QTreeWidgetItem], node: DetailNode, query_text: str) -> None:
        item = QTreeWidgetItem([node.name or "", self._infer_type(node.value), node.value or ""])
        if query_text and self._text_has_match(node.name + " " + node.value, query_text, self.regex_check.isChecked()):
            for col in range(3):
                item.setBackground(col, self._match_background)
        if node.refs:
            item.setForeground(0, self._ref_foreground)
            item.setData(0, Qt.ItemDataRole.UserRole, node.refs)
        if parent_item is None:
            self.details_tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        for child in node.children:
            self._add_detail_node(item, child, query_text)

    def _text_has_match(self, text: str, query: str, use_regex: bool) -> bool:
        if not query:
            return False
        if use_regex:
            try:
                return bool(re.search(query, text, flags=re.IGNORECASE))
            except re.error:
                return False
        return query.lower() in text.lower()

    def _infer_type(self, value: str) -> str:
        txt = (value or "").strip()
        if not txt:
            return "empty"
        if txt.startswith("0x"):
            return "hex"
        if re.fullmatch(r"-?\d+", txt):
            return "int"
        if re.fullmatch(r"-?\d+\.\d+", txt):
            return "float"
        return "text"

    def _open_results_menu(self, point) -> None:
        item = self.results_table.itemAt(point)
        if item is None:
            return
        menu = QMenu(self)
        copy_cell = menu.addAction("Copy Cell")
        copy_row = menu.addAction("Copy Row")
        action = menu.exec(self.results_table.viewport().mapToGlobal(point))
        if action == copy_cell:
            self._copy_text(item.text())
        elif action == copy_row:
            row = item.row()
            values = []
            for col in range(self.results_table.columnCount()):
                it = self.results_table.item(row, col)
                values.append(it.text() if it else "")
            self._copy_text("\t".join(values))

    def _open_tree_menu(self, point) -> None:
        item = self.details_tree.itemAt(point)
        if item is None:
            return
        menu = QMenu(self)
        copy_field = menu.addAction("Copy Field Name")
        copy_type = menu.addAction("Copy Type")
        copy_value = menu.addAction("Copy Value")
        copy_branch = menu.addAction("Copy Branch as JSON")
        action = menu.exec(self.details_tree.viewport().mapToGlobal(point))
        if action == copy_field:
            self._copy_text(item.text(0))
        elif action == copy_type:
            self._copy_text(item.text(1))
        elif action == copy_value:
            self._copy_text(item.text(2))
        elif action == copy_branch:
            self._copy_text(json.dumps(self._branch_to_dict(item), ensure_ascii=False, indent=2))

    def _branch_to_dict(self, item: QTreeWidgetItem) -> dict:
        return {
            "field": item.text(0),
            "type": item.text(1),
            "value": item.text(2),
            "children": [self._branch_to_dict(item.child(i)) for i in range(item.childCount())],
        }

    def _copy_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text or "")
        self.progress_label.setText("Copied to clipboard")

    def copy_selected_structure(self) -> None:
        selected = self.details_tree.selectedItems()
        if not selected:
            self.progress_label.setText("No detail item selected")
            return
        payload = self._branch_to_dict(selected[0])
        self._copy_text(json.dumps(payload, ensure_ascii=False, indent=2))

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "esp_search_results.csv", "CSV Files (*.csv)")
        if not path:
            return
        rows = self._get_filtered_rows()
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["record_type", "id", "name", "plugin"])
            for row in rows:
                writer.writerow([row.signature, f"0x{row.form_id:08X}", row.record_name, row.plugin_name])
        self.progress_label.setText(f"CSV exported: {path}")

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "esp_search_results.json", "JSON Files (*.json)")
        if not path:
            return
        rows = self._get_filtered_rows()
        payload = [
            {
                "record_type": row.signature,
                "id": f"0x{row.form_id:08X}",
                "name": row.record_name,
                "plugin": row.plugin_name,
            }
            for row in rows
        ]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        self.progress_label.setText(f"JSON exported: {path}")

    def get_or_parse_bundle(self, path: str, plugin_name: str, parse_for_meta: bool = False) -> Optional[CachedPluginBundle]:
        try:
            stat = os.stat(path)
        except OSError:
            return None
        cached = self._bundle_cache.get(path)
        if cached and cached.mtime == stat.st_mtime and cached.size == stat.st_size:
            return cached
        try:
            plugin = parse_plugin(path)
            bundle = CachedPluginBundle(path=path, mtime=stat.st_mtime, size=stat.st_size, plugin=plugin)
            if parse_for_meta:
                bundle.author = self._extract_author(plugin)
            else:
                bundle.author = self._extract_author(plugin)
            self._ensure_record_map(plugin)
            self._bundle_cache[path] = bundle
            for rec in iter_records(plugin.children):
                self._record_lookup[(path, rec.signature, rec.form_id)] = rec
                bundle.signatures.add(rec.signature)
            return bundle
        except Exception as exc:
            logger.exception("Failed to parse plugin %s", plugin_name)
            self.progress_label.setText(f"Parse failed for {plugin_name}: {exc}")
            return None

    def _ensure_record_map(self, plugin: PluginFile) -> None:
        if getattr(plugin, "record_map", None):
            return
        mapping: Dict[Tuple[str, int], Record] = {}
        for rec in iter_records(plugin.children):
            mapping[(rec.signature, rec.form_id)] = rec
        plugin.record_map = mapping

    def _extract_author(self, plugin: PluginFile) -> str:
        for rec in iter_records(plugin.children):
            if rec.signature != "TES4":
                continue
            for fld in rec.fields:
                if fld.signature == "CNAM":
                    text = decode_text(fld.raw)
                    if text:
                        return text
        return ""

    def resolve_record_name(self, plugin: PluginFile, record: Record) -> str:
        if record.full_name:
            return record.full_name
        if record.editor_id:
            return record.editor_id
        if plugin.formid_resolver:
            return plugin.formid_resolver.describe(record.form_id)
        return ""

    def get_record_blob(self, bundle: CachedPluginBundle, record: Record) -> str:
        key = (record.signature, record.form_id)
        cached = bundle.record_blob_cache.get(key)
        if cached is not None:
            return cached
        fragments = [record.signature, f"{record.form_id:08X}", record.editor_id or "", record.full_name or ""]
        try:
            parser = StructuredSubrecordParser(record, bundle.plugin)
            stack = list(parser.iter_nodes())
            while stack:
                node = stack.pop()
                if node.name:
                    fragments.append(node.name)
                if node.value:
                    fragments.append(node.value)
                if node.children:
                    stack.extend(node.children)
        except Exception:
            pass
        blob = "\n".join(fragments)
        bundle.record_blob_cache[key] = blob
        return blob

    def compare_selected_record(self) -> None:
        selected = self.results_table.selectedItems()
        if not selected:
            self.progress_label.setText("Select result row to compare")
            return
        rows = self._get_filtered_rows()
        row_idx = selected[0].row()
        if row_idx < 0 or row_idx >= len(rows):
            return
        target = rows[row_idx]
        key = (target.signature, target.form_id)
        compare_rows: List[Tuple[str, str, str]] = []
        for entry in self._plugins:
            if entry.path not in self._bundle_cache:
                if not self._plugin_may_contain(entry.path, key):
                    continue
            bundle = self.get_or_parse_bundle(entry.path, entry.name)
            if bundle is None:
                continue
            record = bundle.plugin.record_map.get(key)
            if record is None:
                continue
            compare_rows.append((entry.name, record.editor_id or "", self.resolve_record_name(bundle.plugin, record)))
        if not compare_rows:
            QMessageBox.information(self, "Compare Similar", "No analogous records found in active plugins.")
            return
        dlg = CompareDialog(f"Compare {target.signature} 0x{target.form_id:08X}", compare_rows, self)
        dlg.exec()

    def _plugin_may_contain(self, path: str, key: Tuple[str, int]) -> bool:
        lazy_index = self._lazy_index_cache.get(path)
        if lazy_index is not None:
            return key in lazy_index.record_offsets
        try:
            lazy_index = create_lazy_index(path)
        except Exception:
            return False
        self._lazy_index_cache[path] = lazy_index
        return key in lazy_index.record_offsets

    def _on_detail_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        refs = item.data(0, Qt.ItemDataRole.UserRole)
        if not refs:
            return
        ref_rows = []
        for sig, form_id in refs:
            if not form_id:
                continue
            matched = []
            for bundle in self._bundle_cache.values():
                rec = bundle.plugin.record_map.get((sig, form_id)) if sig else bundle.plugin.record_map.get((item.text(0)[:4], form_id))
                if rec:
                    matched.append((os.path.basename(bundle.path), rec.editor_id or "", self.resolve_record_name(bundle.plugin, rec)))
            ref_rows.extend(matched)
        if not ref_rows:
            return
        dlg = CompareDialog("Linked References", ref_rows, self)
        dlg.exec()

    def _load_history(self) -> None:
        raw = self._settings.value("history", [])
        if isinstance(raw, str):
            self._history = [x for x in raw.split("\n") if x]
        elif isinstance(raw, list):
            self._history = [str(x) for x in raw if str(x).strip()]
        else:
            self._history = []
        self._history_model.setStringList(self._history)

    def _save_history(self, query: str) -> None:
        query = query.strip()
        if not query:
            return
        filtered = [x for x in self._history if x != query]
        self._history = [query] + filtered[:49]
        self._settings.setValue("history", self._history)
        self._history_model.setStringList(self._history)


class MyPluginDialog(QDialog):
    def __init__(self, organizer: mobase.IOrganizer, parent=None):
        super().__init__(parent)
        self._organizer = organizer
        self._settings = QSettings("ModOrganizer2", "FlyoutEspSearch")
        self.setWindowTitle("ESP Search")
        self.resize(1240, 760)
        self.setMinimumSize(980, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.panel = EspSearchPanel(self._organizer, self)
        layout.addWidget(self.panel)
        self._restore_geometry()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            QTimer.singleShot(150, self._check_should_hide)
        return super().event(event)

    def _check_should_hide(self):
        if not self.isVisible():
            return
        active = QApplication.activeWindow()
        if active is self:
            return
        if active is not None and active.parent() is self:
            return
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return
        self.hide()

    def has_saved_geometry(self) -> bool:
        return self._settings.value("ui/dialog_geometry") is not None

    def _restore_geometry(self) -> None:
        raw = self._settings.value("ui/dialog_geometry")
        if isinstance(raw, QByteArray):
            self.restoreGeometry(raw)
        elif isinstance(raw, (bytes, bytearray)):
            self.restoreGeometry(QByteArray(bytes(raw)))

    def _save_geometry(self) -> None:
        self._settings.setValue("ui/dialog_geometry", self.saveGeometry())

    def hideEvent(self, event) -> None:
        self.panel.persist_ui_state()
        self._save_geometry()
        super().hideEvent(event)


class MyPlugin(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._organizer = None
        self._toolbar_button = None
        self._retry_count = 0
        self._tools_menu = None
        self._flyout_dialog = None

    def init(self, organizer):
        self._organizer = organizer
        QTimer.singleShot(3000, self._setup_toolbar)
        return True

    def name(self):
        return "Flyout ESP Search"

    def author(self):
        return "Flyout Integration Team"

    def description(self):
        return "High-performance ESP search flyout with caching and export"

    def version(self):
        return mobase.VersionInfo(2, 0, 0)

    def requirements(self):
        return []

    def settings(self):
        return []

    def displayName(self):
        return "ESP Search Flyout"

    def tooltip(self):
        return "Search ESP/ESM/ESL records in active profile"

    def icon(self):
        return make_plugin_icon()

    def display(self):
        self._open_flyout()

    def _open_flyout(self):
        main_window = self._main_window()
        if not main_window:
            return
        dialog = self._flyout_dialog
        if dialog is not None and dialog.isVisible():
            dialog.hide()
            return
        if dialog is None:
            dialog = MyPluginDialog(self._organizer, main_window)
            dialog.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self._flyout_dialog = dialog
        if not dialog.has_saved_geometry():
            anchor = self._toolbar_button or main_window
            if isinstance(anchor, QToolButton):
                global_pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
            else:
                global_pos = main_window.mapToGlobal(QPoint(0, 0))
            dialog.move(global_pos)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _setup_toolbar(self):
        main_window = self._main_window()
        if not main_window:
            self._retry()
            return
        for toolbar in main_window.findChildren(QToolBar):
            actions_list = toolbar.actions()
            for action in actions_list:
                menu = self._find_menu(action, toolbar)
                if self._is_tools_menu(menu):
                    self._tools_menu = menu
                    button = QToolButton(toolbar)
                    button.setToolTip(self.tooltip())
                    button.setAutoRaise(True)
                    button.setIcon(make_plugin_icon())
                    button.setIconSize(QSize(30, 30))
                    button.clicked.connect(self._open_flyout)
                    if actions_list:
                        toolbar.insertWidget(actions_list[0], button)
                    else:
                        toolbar.addWidget(button)
                    self._toolbar_button = button
                    self._hide_self_from_menu()
                    return
        self._retry()

    def _retry(self):
        self._retry_count += 1
        if self._retry_count < 5:
            QTimer.singleShot(2000, self._setup_toolbar)

    def _find_menu(self, toolbar_action, toolbar):
        menu = toolbar_action.menu()
        if menu:
            return menu
        widget = toolbar.widgetForAction(toolbar_action)
        if isinstance(widget, QToolButton):
            default_action = widget.defaultAction()
            if default_action:
                menu = default_action.menu()
                if menu:
                    return menu
        return None

    def _normalize_text(self, text):
        return text.replace("&", "").replace("—", "-").replace("–", "-").strip().lower()

    def _menu_title_matches(self, menu):
        title = self._normalize_text(menu.title())
        return title in ("tool plugins", "плагины-программы")

    def _menu_has_plugin_action(self, menu):
        target = self._normalize_text(self.displayName())
        for action in menu.actions():
            if self._normalize_text(action.text()) == target:
                return True
        return False

    def _is_tools_menu(self, menu):
        if not menu:
            return False
        return self._menu_title_matches(menu) or self._menu_has_plugin_action(menu)

    def _hide_self_from_menu(self):
        if not self._tools_menu:
            return
        def hide_action():
            for action in self._tools_menu.actions():
                if action.text().replace("&", "") == self.displayName():
                    action.setVisible(False)
                    break
        hide_action()
        self._tools_menu.aboutToShow.connect(hide_action)

    def _main_window(self):
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMainWindow):
                return widget
        return None


def createPlugin():
    return MyPlugin()
