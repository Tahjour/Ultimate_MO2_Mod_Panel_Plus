# -*- coding: utf-8 -*-
"""
Mod Renamer Plugin for Mod Organizer 2
Bulk rename mods using flexible patterns and prefix presets.

Hotkey: Ctrl+Shift+R
"""

import json
import logging
import os
import re
from datetime import datetime

try:
    from PyQt6.QtCore import QObject, QEvent, Qt, QTimer
    from PyQt6.QtGui import QColor, QBrush, QCursor
    from PyQt6.QtWidgets import (
        QApplication, QTreeView, QDialog, QVBoxLayout, QHBoxLayout,
        QGridLayout, QPushButton, QLabel, QLineEdit, QMessageBox,
        QGroupBox, QCheckBox, QSpinBox, QComboBox, QTableWidget,
        QTableWidgetItem, QHeaderView, QTextEdit, QTabWidget, QWidget,
        QMenu, QMainWindow
    )
    PYQT = 6
except ImportError:
    from PyQt5.QtCore import QObject, QEvent, Qt, QTimer
    from PyQt5.QtGui import QColor, QBrush, QCursor
    from PyQt5.QtWidgets import (
        QApplication, QTreeView, QDialog, QVBoxLayout, QHBoxLayout,
        QGridLayout, QPushButton, QLabel, QLineEdit, QMessageBox,
        QGroupBox, QCheckBox, QSpinBox, QComboBox, QTableWidget,
        QTableWidgetItem, QHeaderView, QTextEdit, QTabWidget, QWidget,
        QMenu, QMainWindow
    )
    PYQT = 5

import mobase

log = logging.getLogger("ModRenamer")


# ============================================================
#  Storage
# ============================================================

class RenamerStorage:
    """Storage for settings, prefixes, and history."""

    def __init__(self, storage_path):
        self._path = storage_path
        self._data = {
            "settings": {},
            "prefixes": [
                "[ANIM]", "[ARMOR]", "[BODY]", "[COMBAT]",
                "[ENV]", "[FIX]", "[MESH]", "[NPC]",
                "[PATCH]", "[TEX]", "[UI]", "[WEAP]"
            ],
            "history": []
        }
        self._load()

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for key in loaded:
                        self._data[key] = loaded[key]
            except Exception as e:
                log.error("Failed to load settings: %s", e)

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error("Failed to save: %s", e)

    @property
    def settings(self):
        return self._data.get("settings", {})

    def save_settings(self, settings):
        self._data["settings"] = settings
        self._save()

    def get_prefixes(self):
        return self._data.get("prefixes", [])

    def add_prefix(self, prefix):
        prefixes = self._data.get("prefixes", [])
        if prefix and prefix not in prefixes:
            prefixes.insert(0, prefix)
            self._data["prefixes"] = prefixes
            self._save()
            return True
        return False

    def remove_prefix(self, prefix):
        prefixes = self._data.get("prefixes", [])
        if prefix in prefixes:
            prefixes.remove(prefix)
            self._data["prefixes"] = prefixes
            self._save()
            return True
        return False

    def add_history(self, entry):
        history = self._data.get("history", [])
        history.insert(0, entry)
        self._data["history"] = history[:30]
        self._save()

    def get_history(self):
        return self._data.get("history", [])

    def remove_last_history(self):
        history = self._data.get("history", [])
        if history:
            removed = history.pop(0)
            self._data["history"] = history
            self._save()
            return removed
        return None

    def clear_history(self):
        self._data["history"] = []
        self._save()


# ============================================================
#  Rename Engine
# ============================================================

class RenameEngine:
    """Pattern-based renaming with prefix support."""

    PREFIX_PATTERN = re.compile(r'^(\[[^\]]+\]\s*)+')

    def __init__(self):
        self._counter = 1
        self._counter_step = 1
        self._counter_digits = 2

    def reset_counter(self, start=1, step=1, digits=2):
        self._counter = start
        self._counter_step = step
        self._counter_digits = digits

    def increment_counter(self):
        self._counter += self._counter_step

    @classmethod
    def strip_prefix(cls, name):
        """Remove existing [TAG] prefixes from name."""
        return cls.PREFIX_PATTERN.sub('', name).strip()

    def expand_prefix_tags(self, prefix, separator_name=""):
        """
        Expand special tags in prefix:
            {SEP} - separator name
            {N} - counter (no padding)
            {NN} - counter (2 digits)
            {NNN} - counter (3 digits)
            {DATE} - YYYY-MM-DD
            {YMD} - YYYYMMDD
        """
        result = prefix
        now = datetime.now()

        if "{SEP}" in result:
            sep_clean = separator_name.strip("-=*# \t") if separator_name else ""
            result = result.replace("{SEP}", sep_clean)

        result = result.replace("{DATE}", now.strftime("%Y-%m-%d"))
        result = result.replace("{YMD}", now.strftime("%Y%m%d"))
        result = result.replace("{NNN}", str(self._counter).zfill(3))
        result = result.replace("{NN}", str(self._counter).zfill(2))
        result = result.replace("{N}", str(self._counter))

        return result

    def apply_pattern(self, original_name, pattern, separator_name=""):
        """
        Apply full rename pattern.
        
        Tokens:
            [N] - original name
            [N1-5] - characters 1-5
            [N2,5] - 5 chars from position 2
            [C] / [C:3] - counter
            [S] - separator name
            [YMD], [Y], [M], [D] - date
            [hms], [h], [m], [s] - time
        """
        result = pattern
        now = datetime.now()

        result = result.replace("[N]", original_name)

        for match in re.finditer(r'\[N(\d+)-(\d+)\]', result):
            start = int(match.group(1)) - 1
            end = int(match.group(2))
            extracted = original_name[start:end] if start < len(original_name) else ""
            result = result.replace(match.group(0), extracted, 1)

        for match in re.finditer(r'\[N(\d+),(\d+)\]', result):
            pos = int(match.group(1)) - 1
            length = int(match.group(2))
            extracted = original_name[pos:pos + length] if pos < len(original_name) else ""
            result = result.replace(match.group(0), extracted, 1)

        sep_clean = separator_name.strip("-=*# \t") if separator_name else ""
        result = result.replace("[S]", sep_clean)

        result = result.replace("[YMD]", now.strftime("%Y%m%d"))
        result = result.replace("[Y]", now.strftime("%Y"))
        result = result.replace("[M]", now.strftime("%m"))
        result = result.replace("[D]", now.strftime("%d"))

        result = result.replace("[hms]", now.strftime("%H%M%S"))
        result = result.replace("[h]", now.strftime("%H"))
        result = result.replace("[m]", now.strftime("%M"))
        result = result.replace("[s]", now.strftime("%S"))

        for match in re.finditer(r'\[C:(\d+)\]', result):
            digits = int(match.group(1))
            result = result.replace(match.group(0), str(self._counter).zfill(digits), 1)

        result = result.replace("[C]", str(self._counter).zfill(self._counter_digits))

        return result

    def apply_search_replace(self, name, search, replace,
                             use_regex=False, ignore_case=False):
        """Apply search and replace with optional regex."""
        if not search:
            return name

        try:
            if use_regex:
                flags = re.IGNORECASE if ignore_case else 0
                return re.sub(search, replace, name, flags=flags)
            else:
                if ignore_case:
                    pattern = re.compile(re.escape(search), re.IGNORECASE)
                    return pattern.sub(replace, name)
                return name.replace(search, replace)
        except re.error as e:
            log.warning("Regex error: %s", e)
            return name

    def apply_case(self, name, mode):
        """Apply case transformation."""
        modes = {
            "lower": str.lower,
            "upper": str.upper,
            "title": str.title,
            "capitalize": str.capitalize
        }
        func = modes.get(mode)
        return func(name) if func else name

    @staticmethod
    def sanitize_name(name):
        """Remove invalid characters for folder names."""
        for char in '<>:"/\\|?*':
            name = name.replace(char, '')
        name = ' '.join(name.split())
        name = name.strip().strip('.')
        return name


# ============================================================
#  Rename Dialog
# ============================================================

class RenameDialog(QDialog):
    """Dialog for bulk mod renaming with prefix presets."""

    def __init__(self, mod_list, storage, rename_callback,
                 mods_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mod Renamer (Ctrl+Shift+R)")
        self.setMinimumSize(850, 650)

        self._mod_list = mod_list
        self._storage = storage
        self._rename_callback = rename_callback
        self._mods_path = mods_path
        self._engine = RenameEngine()
        self._preview_data = []

        self._setup_ui()
        self._load_settings()
        self._update_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # === Create buttons BEFORE tabs ===
        self._btn_undo = QPushButton("↶ Undo Last")
        self._btn_undo.clicked.connect(self._on_undo)

        self._btn_execute = QPushButton("✓ Execute")
        self._btn_execute.setStyleSheet(
            "QPushButton { background-color: #2d5f2d; color: white; "
            "font-weight: bold; padding: 8px 24px; }"
            "QPushButton:hover { background-color: #3a7a3a; }"
            "QPushButton:disabled { background-color: #555; }"
        )
        self._btn_execute.clicked.connect(self._on_execute)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)

        # === Tabs ===
        tabs = QTabWidget()
        layout.addWidget(tabs)

        rename_tab = QWidget()
        tabs.addTab(rename_tab, "Rename")
        self._setup_rename_tab(rename_tab)

        history_tab = QWidget()
        tabs.addTab(history_tab, "History")
        self._setup_history_tab(history_tab)

        # === Add buttons to layout ===
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._btn_undo)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_execute)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        self._update_buttons()

    def _setup_rename_tab(self, parent):
        layout = QVBoxLayout(parent)

        # === Prefix presets ===
        prefix_group = QGroupBox("Prefix Presets")
        prefix_layout = QHBoxLayout(prefix_group)

        self._prefix_combo = QComboBox()
        self._prefix_combo.setEditable(True)
        self._prefix_combo.setMinimumWidth(200)
        self._prefix_combo.setPlaceholderText("Select or type prefix...")
        self._prefix_combo.currentTextChanged.connect(self._on_prefix_changed)
        self._refresh_prefix_combo()
        prefix_layout.addWidget(self._prefix_combo)

        btn_add_prefix = QPushButton("+")
        btn_add_prefix.setFixedWidth(30)
        btn_add_prefix.setToolTip("Save current as preset")
        btn_add_prefix.clicked.connect(self._on_add_prefix)
        prefix_layout.addWidget(btn_add_prefix)

        btn_remove_prefix = QPushButton("×")
        btn_remove_prefix.setFixedWidth(30)
        btn_remove_prefix.setToolTip("Remove selected preset")
        btn_remove_prefix.clicked.connect(self._on_remove_prefix)
        prefix_layout.addWidget(btn_remove_prefix)

        self._replace_prefix_check = QCheckBox("Replace existing prefix")
        self._replace_prefix_check.setChecked(True)
        self._replace_prefix_check.stateChanged.connect(self._on_settings_changed)
        prefix_layout.addWidget(self._replace_prefix_check)

        prefix_layout.addStretch()

        btn_apply_prefix = QPushButton("Apply Prefix")
        btn_apply_prefix.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; padding: 4px 12px; }"
        )
        btn_apply_prefix.clicked.connect(self._on_apply_prefix)
        prefix_layout.addWidget(btn_apply_prefix)

        layout.addWidget(prefix_group)

        prefix_help = QLabel(
            "<small>Tags: <b>{SEP}</b>=separator, <b>{N}</b>=counter, "
            "<b>{NN}</b>=01, <b>{NNN}</b>=001, <b>{DATE}</b>=2024-12-15</small>"
        )
        prefix_help.setStyleSheet("color: #888;")
        layout.addWidget(prefix_help)

        # === Pattern & Options ===
        options_layout = QHBoxLayout()

        # Left: Pattern
        pattern_group = QGroupBox("Pattern (advanced)")
        pattern_layout = QVBoxLayout(pattern_group)

        pattern_row = QHBoxLayout()
        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText("[N] (original name)")
        self._pattern_edit.textChanged.connect(self._on_settings_changed)
        pattern_row.addWidget(QLabel("Pattern:"))
        pattern_row.addWidget(self._pattern_edit)
        pattern_layout.addLayout(pattern_row)

        pattern_help = QLabel(
            "<small>[N]=name [N1-5]=chars [C]=counter [S]=separator [YMD]=date</small>"
        )
        pattern_help.setStyleSheet("color: #888;")
        pattern_layout.addWidget(pattern_help)

        # Counter
        counter_row = QHBoxLayout()
        counter_row.addWidget(QLabel("Counter:"))
        self._counter_start = QSpinBox()
        self._counter_start.setRange(0, 9999)
        self._counter_start.setValue(1)
        self._counter_start.valueChanged.connect(self._on_settings_changed)
        counter_row.addWidget(QLabel("start"))
        counter_row.addWidget(self._counter_start)

        self._counter_step = QSpinBox()
        self._counter_step.setRange(1, 100)
        self._counter_step.setValue(1)
        self._counter_step.valueChanged.connect(self._on_settings_changed)
        counter_row.addWidget(QLabel("step"))
        counter_row.addWidget(self._counter_step)

        self._counter_digits = QSpinBox()
        self._counter_digits.setRange(1, 5)
        self._counter_digits.setValue(2)
        self._counter_digits.valueChanged.connect(self._on_settings_changed)
        counter_row.addWidget(QLabel("digits"))
        counter_row.addWidget(self._counter_digits)
        counter_row.addStretch()

        pattern_layout.addLayout(counter_row)
        options_layout.addWidget(pattern_group)

        # Right: Search/Replace & Case
        sr_group = QGroupBox("Search / Replace")
        sr_layout = QGridLayout(sr_group)

        self._search_edit = QLineEdit()
        self._search_edit.textChanged.connect(self._on_settings_changed)
        sr_layout.addWidget(QLabel("Find:"), 0, 0)
        sr_layout.addWidget(self._search_edit, 0, 1)

        self._replace_edit = QLineEdit()
        self._replace_edit.textChanged.connect(self._on_settings_changed)
        sr_layout.addWidget(QLabel("Replace:"), 1, 0)
        sr_layout.addWidget(self._replace_edit, 1, 1)

        check_row = QHBoxLayout()
        self._regex_check = QCheckBox("Regex")
        self._regex_check.stateChanged.connect(self._on_settings_changed)
        check_row.addWidget(self._regex_check)

        self._ignore_case_check = QCheckBox("Ignore case")
        self._ignore_case_check.stateChanged.connect(self._on_settings_changed)
        check_row.addWidget(self._ignore_case_check)
        check_row.addStretch()
        sr_layout.addLayout(check_row, 2, 0, 1, 2)

        case_row = QHBoxLayout()
        case_row.addWidget(QLabel("Case:"))
        self._case_combo = QComboBox()
        self._case_combo.addItems([
            "No change", "lowercase", "UPPERCASE", "Title Case", "Capitalize"
        ])
        self._case_combo.currentIndexChanged.connect(self._on_settings_changed)
        case_row.addWidget(self._case_combo)
        case_row.addStretch()
        sr_layout.addLayout(case_row, 3, 0, 1, 2)

        options_layout.addWidget(sr_group)
        layout.addLayout(options_layout)

        # === Preview table ===
        self._preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(self._preview_group)

        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(3)
        self._preview_table.setHorizontalHeaderLabels(["Original", "New Name", "Status"])
        self._preview_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._preview_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._preview_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._preview_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self._preview_table)

        layout.addWidget(self._preview_group, stretch=1)

    def _setup_history_tab(self, parent):
        layout = QVBoxLayout(parent)

        self._history_text = QTextEdit()
        self._history_text.setReadOnly(True)
        self._history_text.setStyleSheet("font-family: Consolas, monospace;")
        layout.addWidget(self._history_text)

        btn_row = QHBoxLayout()
        btn_clear = QPushButton("Clear History")
        btn_clear.clicked.connect(self._on_clear_history)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._refresh_history()

    # === Prefix methods ===

    def _refresh_prefix_combo(self):
        current = self._prefix_combo.currentText()
        self._prefix_combo.clear()
        self._prefix_combo.addItem("")
        for prefix in self._storage.get_prefixes():
            self._prefix_combo.addItem(prefix)
        idx = self._prefix_combo.findText(current)
        if idx >= 0:
            self._prefix_combo.setCurrentIndex(idx)

    def _on_prefix_changed(self, text):
        pass

    def _on_add_prefix(self):
        text = self._prefix_combo.currentText().strip()
        if text:
            if self._storage.add_prefix(text):
                self._refresh_prefix_combo()
                self._prefix_combo.setCurrentText(text)

    def _on_remove_prefix(self):
        text = self._prefix_combo.currentText().strip()
        if text and self._storage.remove_prefix(text):
            self._refresh_prefix_combo()

    def _on_apply_prefix(self):
        """Apply selected prefix to pattern."""
        prefix = self._prefix_combo.currentText().strip()
        if not prefix:
            QMessageBox.information(self, "No Prefix",
                                    "Please select or enter a prefix.")
            return

        self._pattern_edit.setText(f"{prefix} [N]")
        self._update_preview()

    # === Settings ===

    def _load_settings(self):
        s = self._storage.settings
        self._pattern_edit.setText(s.get("pattern", ""))
        self._search_edit.setText(s.get("search", ""))
        self._replace_edit.setText(s.get("replace", ""))
        self._regex_check.setChecked(s.get("use_regex", False))
        self._ignore_case_check.setChecked(s.get("ignore_case", False))
        self._case_combo.setCurrentIndex(s.get("case_index", 0))
        self._counter_start.setValue(s.get("counter_start", 1))
        self._counter_step.setValue(s.get("counter_step", 1))
        self._counter_digits.setValue(s.get("counter_digits", 2))
        self._replace_prefix_check.setChecked(s.get("replace_prefix", True))

    def _save_settings(self):
        self._storage.save_settings({
            "pattern": self._pattern_edit.text(),
            "search": self._search_edit.text(),
            "replace": self._replace_edit.text(),
            "use_regex": self._regex_check.isChecked(),
            "ignore_case": self._ignore_case_check.isChecked(),
            "case_index": self._case_combo.currentIndex(),
            "counter_start": self._counter_start.value(),
            "counter_step": self._counter_step.value(),
            "counter_digits": self._counter_digits.value(),
            "replace_prefix": self._replace_prefix_check.isChecked()
        })

    def _on_settings_changed(self):
        self._update_preview()

    # === Preview ===

    def _update_preview(self):
        self._preview_data = []
        self._preview_table.setRowCount(0)

        pattern = self._pattern_edit.text().strip()
        search = self._search_edit.text()
        replace = self._replace_edit.text()
        use_regex = self._regex_check.isChecked()
        ignore_case = self._ignore_case_check.isChecked()
        case_modes = ["none", "lower", "upper", "title", "capitalize"]
        case_mode = case_modes[self._case_combo.currentIndex()]
        replace_prefix = self._replace_prefix_check.isChecked()

        self._engine.reset_counter(
            self._counter_start.value(),
            self._counter_step.value(),
            self._counter_digits.value()
        )

        new_names_count = {}
        self._preview_table.setRowCount(len(self._mod_list))
        errors = 0
        changes = 0

        for row, (mod_name, sep_name) in enumerate(self._mod_list):
            error = ""
            new_name = mod_name
            working_name = mod_name

            if replace_prefix and pattern:
                if pattern.startswith("[") and "]" in pattern:
                    working_name = self._engine.strip_prefix(mod_name)

            if pattern:
                expanded_pattern = self._engine.expand_prefix_tags(pattern, sep_name)
                new_name = self._engine.apply_pattern(
                    working_name, expanded_pattern, sep_name)
            else:
                new_name = working_name

            new_name = self._engine.apply_search_replace(
                new_name, search, replace, use_regex, ignore_case)
            new_name = self._engine.apply_case(new_name, case_mode)
            new_name = self._engine.sanitize_name(new_name)

            if "[C" in pattern or "{N" in pattern:
                self._engine.increment_counter()

            if not new_name:
                error = "Empty name"
                errors += 1
            elif new_name != mod_name:
                new_names_count[new_name] = new_names_count.get(new_name, 0) + 1
                if new_names_count[new_name] > 1:
                    error = "Duplicate"
                    errors += 1
                elif os.path.exists(os.path.join(self._mods_path, new_name)):
                    if new_name.lower() != mod_name.lower():
                        error = "Already exists"
                        errors += 1
                    else:
                        changes += 1
                else:
                    changes += 1

            self._preview_data.append((mod_name, new_name, error))

            item_old = QTableWidgetItem(mod_name)
            item_new = QTableWidgetItem(new_name)
            item_status = QTableWidgetItem(
                error if error else ("Changed" if new_name != mod_name else "—"))

            if error:
                item_new.setForeground(QBrush(QColor("#e74c3c")))
                item_status.setForeground(QBrush(QColor("#e74c3c")))
            elif new_name != mod_name:
                item_new.setForeground(QBrush(QColor("#2ecc71")))
                item_status.setForeground(QBrush(QColor("#2ecc71")))
            else:
                item_new.setForeground(QBrush(QColor("#7f8c8d")))
                item_status.setForeground(QBrush(QColor("#7f8c8d")))

            self._preview_table.setItem(row, 0, item_old)
            self._preview_table.setItem(row, 1, item_new)
            self._preview_table.setItem(row, 2, item_status)

        self._preview_group.setTitle(
            f"Preview — {len(self._mod_list)} mods, {changes} changes"
            + (f", {errors} errors" if errors else "")
        )

        self._btn_execute.setEnabled(changes > 0 and errors == 0)

    def _update_buttons(self):
        history = self._storage.get_history()
        self._btn_undo.setEnabled(len(history) > 0)

    # === History ===

    def _refresh_history(self):
        history = self._storage.get_history()
        lines = []

        if not history:
            lines.append("No rename operations recorded yet.")
        else:
            for i, entry in enumerate(history, 1):
                ts = entry.get("timestamp", "?")
                renames = entry.get("renames", [])
                lines.append(f"{'─' * 50}")
                lines.append(f"#{i}  {ts}  ({len(renames)} items)")
                for old, new in renames[:10]:
                    lines.append(f"  {old}")
                    lines.append(f"    → {new}")
                if len(renames) > 10:
                    lines.append(f"  ... and {len(renames) - 10} more")

        self._history_text.setText("\n".join(lines))
        self._update_buttons()

    def _on_clear_history(self):
        if QMessageBox.question(
            self, "Clear History",
            "Clear all rename history? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._storage.clear_history()
            self._refresh_history()

    # === Actions ===

    def _on_execute(self):
        changes = [(old, new) for old, new, err in self._preview_data
                   if old != new and not err]

        if not changes:
            return

        if QMessageBox.question(
            self, "Confirm Rename",
            f"Rename {len(changes)} mod(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        self._save_settings()

        success = []
        failed = []

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            for old_name, new_name in changes:
                ok, err = self._rename_callback(old_name, new_name)
                if ok:
                    success.append((old_name, new_name))
                else:
                    failed.append((old_name, err))
        finally:
            QApplication.restoreOverrideCursor()

        if success:
            self._storage.add_history({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "renames": success
            })

        self._refresh_history()

        if failed:
            msg = f"Renamed {len(success)}, failed {len(failed)}:\n"
            for name, err in failed[:5]:
                msg += f"\n• {name}: {err}"
            QMessageBox.warning(self, "Partial Success", msg)
        else:
            QMessageBox.information(self, "Done",
                                    f"Renamed {len(success)} mod(s).")
            self.accept()

    def _on_undo(self):
        history = self._storage.get_history()
        if not history:
            return

        last = history[0]
        renames = last.get("renames", [])

        if QMessageBox.question(
            self, "Confirm Undo",
            f"Undo {len(renames)} rename(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        success = 0
        failed = []

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            for old_name, new_name in renames:
                new_path = os.path.join(self._mods_path, new_name)
                old_path = os.path.join(self._mods_path, old_name)

                if not os.path.exists(new_path):
                    failed.append((new_name, "Not found"))
                    continue
                if os.path.exists(old_path) and old_name.lower() != new_name.lower():
                    failed.append((new_name, f"'{old_name}' already exists"))
                    continue

                ok, err = self._rename_callback(new_name, old_name)
                if ok:
                    success += 1
                else:
                    failed.append((new_name, err))
        finally:
            QApplication.restoreOverrideCursor()

        self._storage.remove_last_history()
        self._refresh_history()

        if failed:
            msg = f"Restored {success}, failed {len(failed)}:\n"
            for name, err in failed[:5]:
                msg += f"\n• {name}: {err}"
            QMessageBox.warning(self, "Partial Undo", msg)
        else:
            QMessageBox.information(self, "Undo Complete",
                                    f"Restored {success} name(s).")


# ============================================================
#  Key Filter
# ============================================================

class _KeyFilter(QObject):
    """Key filter for Ctrl+Shift+R."""

    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin

    def eventFilter(self, obj, event):
        key_press_type = QEvent.Type.KeyPress if PYQT == 6 else QEvent.KeyPress
        if event.type() != key_press_type:
            return False

        mods = event.modifiers()
        ctrl_mod = Qt.KeyboardModifier.ControlModifier if PYQT == 6 else Qt.ControlModifier
        shift_mod = Qt.KeyboardModifier.ShiftModifier if PYQT == 6 else Qt.ShiftModifier
        if not (mods & ctrl_mod):
            return False
        if not (mods & shift_mod):
            return False

        key_r = Qt.Key.Key_R if PYQT == 6 else Qt.Key_R
        if event.key() == key_r:
            QTimer.singleShot(0, self._plugin.on_rename)
            return True

        return False


# ============================================================
#  Main Plugin
# ============================================================


class ModListMenuFilter(QObject):
    def __init__(self, view, callback, parent=None):
        super().__init__(parent)
        self._view = view
        self._callback = callback
        self._last_pos = None

    def eventFilter(self, obj, event):
        menu_event_type = QEvent.Type.ContextMenu if PYQT == 6 else QEvent.ContextMenu
        if event.type() == menu_event_type:
            self._last_pos = event.pos()
            QTimer.singleShot(0, self._inject_into_visible_menu)
        return False

    def _inject_into_visible_menu(self):
        app = QApplication.instance()
        if not app:
            return
        menu = app.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(50, self._inject_into_visible_menu_retry)
            return
        self._do_inject(menu)

    def _inject_into_visible_menu_retry(self):
        app = QApplication.instance()
        if not app:
            return
        menu = app.activePopupWidget()
        if isinstance(menu, QMenu):
            self._do_inject(menu)

    def _do_inject(self, menu):
        for action in menu.actions():
            if action.objectName() == "_mod_renamer_open":
                return

        mod_name = self._get_mod_under_cursor()

        menu.addSeparator()
        action = menu.addAction("Batch Rename")
        action.setObjectName("_mod_renamer_open")
        action.triggered.connect(lambda: self._callback(mod_name))

    def _get_mod_under_cursor(self):
        try:
            if self._last_pos is None:
                viewport = self._view.viewport()
                local_pos = viewport.mapFromGlobal(QCursor.pos())
            else:
                local_pos = self._last_pos
            index = self._view.indexAt(local_pos)
            if index.isValid():
                name_index = index.sibling(index.row(), 0)
                if PYQT == 6:
                    mod_name = name_index.data(Qt.ItemDataRole.DisplayRole)
                else:
                    mod_name = name_index.data(Qt.DisplayRole)
                if mod_name:
                    return str(mod_name)
        except Exception:
            return ""
        return ""

class ModRenamer(mobase.IPlugin):
    """MO2 plugin for bulk renaming mods. Hotkey: Ctrl+Shift+R"""

    def __init__(self):
        super().__init__()
        self._organizer = None
        self._modList = None
        self._view = None
        self._filter = None
        self._storage = None
        self._menu_filter = None
        self._dialog = None
        self._attempts = 0
        self._max_attempts = 15
        self._attached = False

    def __del__(self):
        if self._view and self._filter:
            try:
                self._view.removeEventFilter(self._filter)
            except Exception:
                pass
        if self._view and self._menu_filter:
            try:
                self._view.viewport().removeEventFilter(self._menu_filter)
            except Exception:
                pass

    def name(self):
        return "Mod Renamer"

    def author(self):
        return "User"

    def version(self):
        return mobase.VersionInfo(2, 1, 0)

    def description(self):
        return (
            "Bulk rename mods with patterns and prefix presets.\n\n"
            "Hotkey: Ctrl+Shift+R\n\n"
            "Features:\n"
            "• Prefix presets with tags ({SEP}, {N}, {DATE})\n"
            "• Pattern-based renaming\n"
            "• Search/replace with regex\n"
            "• Duplicate detection\n"
            "• Undo support"
        )

    def settings(self):
        return []

    def isActive(self):
        return True

    def init(self, organizer: mobase.IOrganizer):
        self._organizer = organizer
        self._modList = organizer.modList()

        base_path = organizer.basePath()
        if not base_path:
            return False

        storage_file = os.path.join(base_path, "mod_renamer", "settings.json")
        self._storage = RenamerStorage(storage_file)

        self._filter = _KeyFilter(self)

        try:
            organizer.onUserInterfaceInitialized(lambda w: self._start_attach())
        except Exception:
            QTimer.singleShot(3000, self._start_attach)

        return True

    def _start_attach(self):
        self._attempts = 0
        QTimer.singleShot(500, self._try_attach)

    def _try_attach(self):
        if self._attached:
            return

        self._attempts += 1

        window = self._find_main_window()
        if not window:
            if self._attempts < self._max_attempts:
                QTimer.singleShot(1500, self._try_attach)
            return

        modlist = self._find_modlist_view(window)
        if not modlist:
            if self._attempts < self._max_attempts:
                QTimer.singleShot(1500, self._try_attach)
            return

        self._view = modlist
        modlist.installEventFilter(self._filter)
        if not self._menu_filter:
            self._menu_filter = ModListMenuFilter(
                modlist, self._on_menu_rename, modlist
            )
            modlist.viewport().installEventFilter(self._menu_filter)
        self._attached = True

    def _find_main_window(self):
        app = QApplication.instance()
        if not app:
            return None
        for w in app.topLevelWidgets():
            if w.isVisible() and isinstance(w, QMainWindow):
                if w.centralWidget() is not None or w.menuBar() is not None:
                    return w
        for w in app.topLevelWidgets():
            if w.isVisible() and isinstance(w, QMainWindow):
                return w
        return None

    def _find_modlist_view(self, window):
        known_names = ["modList", "modListView", "ModList", "modlist"]
        for name in known_names:
            widget = window.findChild(QTreeView, name)
            if widget:
                return widget

        all_trees = window.findChildren(QTreeView)
        for tree in all_trees:
            obj_name = tree.objectName() or ""
            parent_name = tree.parent().objectName() if tree.parent() else ""
            check = (obj_name + parent_name).lower()
            if "plugin" not in obj_name.lower() and any(w in check for w in ["mod", "left", "plugin"]):
                return tree

        visible_trees = [t for t in all_trees if t.isVisible() and t.model()]
        if visible_trees:
            return max(visible_trees, key=lambda t: t.model().rowCount())

        return None

    # === Helpers ===

    def _is_separator(self, mod_name):
        """Check if mod is a separator."""
        try:
            pri = self._modList.priority(mod_name)
            if pri < 0:
                return True
        except Exception:
            pass

        mod_path = os.path.join(self._organizer.modsPath(), mod_name)
        if not os.path.exists(mod_path):
            return True

        return False

    def _get_mods_ordered(self):
        """Get all mods sorted by priority."""
        try:
            mods = list(self._modList.allMods())
            mods.sort(key=lambda m: self._modList.priority(m))
            return mods
        except Exception:
            return list(self._modList.allMods())

    def _find_separator_for_mod(self, mod_name, all_mods):
        """Find parent separator for a mod."""
        try:
            idx = all_mods.index(mod_name)
            for i in range(idx - 1, -1, -1):
                if self._is_separator(all_mods[i]):
                    return all_mods[i]
        except ValueError:
            pass
        return ""

    def _expand_selection(self, selected):
        """Expand separators to include contained mods."""
        if not selected:
            return []

        all_mods = self._get_mods_ordered()
        result = []
        seen = set()

        sep_indices = [i for i, m in enumerate(all_mods) if self._is_separator(m)]

        for name in selected:
            if name in seen:
                continue

            if self._is_separator(name):
                try:
                    sep_idx = all_mods.index(name)
                except ValueError:
                    continue

                next_sep = len(all_mods)
                for idx in sep_indices:
                    if idx > sep_idx:
                        next_sep = idx
                        break

                for i in range(sep_idx + 1, next_sep):
                    mod = all_mods[i]
                    if mod not in seen and not self._is_separator(mod):
                        seen.add(mod)
                        result.append(mod)
            else:
                seen.add(name)
                result.append(name)

        return result

    def _get_selected_mods(self):
        """Get selected mods with separator info."""
        if not self._view:
            return []

        sel = self._view.selectionModel()
        if not sel:
            return []

        indexes = sel.selectedRows(0)
        if not indexes:
            return []

        names = []
        for idx in sorted(indexes, key=lambda i: i.row()):
            name = idx.data()
            if name:
                names.append(name)

        expanded = self._expand_selection(names)

        all_mods = self._get_mods_ordered()
        result = []
        for mod in expanded:
            sep = self._find_separator_for_mod(mod, all_mods)
            result.append((mod, sep))

        return result

    def _rename_mod(self, old_name, new_name):
        """Rename mod using MO2 API (preserves state and position)."""
        if old_name == new_name:
            return True, ""

        try:
            mod = self._modList.getMod(old_name)
            if not mod:
                return False, "Mod not found"

            new_mod = self._modList.renameMod(mod, new_name)

            if new_mod:
                return True, ""
            else:
                return self._rename_mod_fallback(old_name, new_name)

        except AttributeError:
            return self._rename_mod_fallback(old_name, new_name)
        except Exception as e:
            return False, str(e)

    def _rename_mod_fallback(self, old_name, new_name):
        """Fallback: direct filesystem rename for older MO2 versions."""
        mods_path = self._organizer.modsPath()
        old_path = os.path.join(mods_path, old_name)
        new_path = os.path.join(mods_path, new_name)

        if not os.path.isdir(old_path):
            return False, "Source not found"

        if os.path.exists(new_path):
            if old_name.lower() == new_name.lower():
                tmp_name = f"_rename_tmp_{datetime.now().timestamp()}"
                tmp_path = os.path.join(mods_path, tmp_name)
                try:
                    os.rename(old_path, tmp_path)
                    os.rename(tmp_path, new_path)
                    self._refresh()
                    return True, ""
                except Exception as e:
                    if os.path.exists(tmp_path) and not os.path.exists(old_path):
                        try:
                            os.rename(tmp_path, old_path)
                        except Exception:
                            pass
                    return False, str(e)
            return False, "Target already exists"

        try:
            os.rename(old_path, new_path)
            self._refresh()
            return True, ""
        except PermissionError:
            return False, "Permission denied (file in use?)"
        except Exception as e:
            return False, str(e)

    def _refresh(self):
        """Refresh MO2 with save."""
        try:
            self._organizer.refresh(True)
        except TypeError:
            try:
                self._organizer.refresh()
            except Exception:
                pass
        except Exception:
            pass

    # === Main action ===

    def on_rename(self):
        self._show_dialog(None)

    def _on_menu_rename(self, mod_name):
        self._show_dialog(mod_name)

    def _show_dialog(self, mod_name):
        mods = []
        selected = self._get_selected_mods()
        selected_names = {name for name, _ in selected}

        if mod_name and selected:
            if mod_name in selected_names or len(selected) > 1:
                mods = selected
            else:
                all_mods = self._get_mods_ordered()
                sep = self._find_separator_for_mod(mod_name, all_mods)
                mods = [(mod_name, sep)]
        elif selected:
            mods = selected
        elif mod_name:
            all_mods = self._get_mods_ordered()
            sep = self._find_separator_for_mod(mod_name, all_mods)
            mods = [(mod_name, sep)]

        if not mods:
            QMessageBox.information(
                self._view, "No Selection",
                "Select mods in the list first.\n"
                "Selecting a separator includes all mods inside it."
            )
            return

        if self._dialog and self._dialog.isVisible():
            try:
                self._dialog.close()
            except Exception:
                pass

        self._dialog = RenameDialog(
            mods,
            self._storage,
            self._rename_mod,
            self._organizer.modsPath(),
            self._view
        )
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()


def createPlugin():
    return ModRenamer()
