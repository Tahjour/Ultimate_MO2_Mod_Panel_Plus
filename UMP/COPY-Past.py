# -*- coding: utf-8 -*-

import logging
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import (
    QObject, QEvent, Qt, QTimer, QPoint, QModelIndex
)
from PyQt6.QtGui import QDropEvent, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QApplication, QTreeView, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox
)

import mobase

try:
    from PyQt6 import sip as _sip
except Exception:
    _sip = None

log = logging.getLogger("MoveModsCtrlC_CtrlV")


def _is_deleted(obj) -> bool:
    if _sip is None:
        return False
    try:
        return _sip.isdeleted(obj)
    except Exception:
        return False


KEY_MAP = {
    "A": Qt.Key.Key_A, "B": Qt.Key.Key_B, "C": Qt.Key.Key_C,
    "D": Qt.Key.Key_D, "E": Qt.Key.Key_E, "F": Qt.Key.Key_F,
    "G": Qt.Key.Key_G, "H": Qt.Key.Key_H, "I": Qt.Key.Key_I,
    "J": Qt.Key.Key_J, "K": Qt.Key.Key_K, "L": Qt.Key.Key_L,
    "M": Qt.Key.Key_M, "N": Qt.Key.Key_N, "O": Qt.Key.Key_O,
    "P": Qt.Key.Key_P, "Q": Qt.Key.Key_Q, "R": Qt.Key.Key_R,
    "S": Qt.Key.Key_S, "T": Qt.Key.Key_T, "U": Qt.Key.Key_U,
    "V": Qt.Key.Key_V, "W": Qt.Key.Key_W, "X": Qt.Key.Key_X,
    "Y": Qt.Key.Key_Y, "Z": Qt.Key.Key_Z,
    "0": Qt.Key.Key_0, "1": Qt.Key.Key_1, "2": Qt.Key.Key_2,
    "3": Qt.Key.Key_3, "4": Qt.Key.Key_4, "5": Qt.Key.Key_5,
    "6": Qt.Key.Key_6, "7": Qt.Key.Key_7, "8": Qt.Key.Key_8,
    "9": Qt.Key.Key_9,
    "F1": Qt.Key.Key_F1, "F2": Qt.Key.Key_F2, "F3": Qt.Key.Key_F3,
    "F4": Qt.Key.Key_F4, "F5": Qt.Key.Key_F5, "F6": Qt.Key.Key_F6,
    "F7": Qt.Key.Key_F7, "F8": Qt.Key.Key_F8, "F9": Qt.Key.Key_F9,
    "F10": Qt.Key.Key_F10, "F11": Qt.Key.Key_F11, "F12": Qt.Key.Key_F12,
}


def parse_hotkey(hotkey_str):
    if not hotkey_str or not isinstance(hotkey_str, str):
        return None, None

    parts = [p.strip().upper() for p in hotkey_str.split("+")]

    modifiers = Qt.KeyboardModifier.NoModifier
    key = None

    for part in parts:
        if part in ("CTRL", "CONTROL"):
            modifiers |= Qt.KeyboardModifier.ControlModifier
        elif part in ("SHIFT",):
            modifiers |= Qt.KeyboardModifier.ShiftModifier
        elif part in ("ALT",):
            modifiers |= Qt.KeyboardModifier.AltModifier
        elif part in ("META", "WIN"):
            modifiers |= Qt.KeyboardModifier.MetaModifier
        elif part in KEY_MAP:
            key = KEY_MAP[part]
        else:
            log.warning("Unknown key in hotkey '%s': '%s'", hotkey_str, part)
            return None, None

    return modifiers, key


# ============================================================
#  File picker dialog (без изменений)
# ============================================================

class FilePickerDialog(QDialog):
    RESULT_COPY = QDialog.DialogCode.Accepted + 1
    RESULT_MOVE = QDialog.DialogCode.Accepted + 2

    def __init__(self, mod_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select files (Ctrl+X)")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        self._mod_paths = mod_paths
        self._result_mode = None

        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Name", "Path"])
        self._model.itemChanged.connect(self._on_item_changed)

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(False)
        self._tree.setColumnWidth(0, 400)
        self._tree.header().setStretchLastSection(True)

        check_layout = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(self._select_all)
        btn_deselect_all = QPushButton("Deselect All")
        btn_deselect_all.clicked.connect(self._deselect_all)
        check_layout.addWidget(btn_select_all)
        check_layout.addWidget(btn_deselect_all)
        check_layout.addStretch()

        action_layout = QHBoxLayout()

        btn_copy = QPushButton("COPY")
        btn_copy.setToolTip("Copy selected files to target mod")
        btn_copy.setMinimumWidth(100)
        btn_copy.setStyleSheet(
            "QPushButton { background-color: #2d5f2d; color: white; "
            "font-weight: bold; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #3a7a3a; }"
        )
        btn_copy.clicked.connect(self._on_copy_clicked)

        btn_move = QPushButton("MOVE")
        btn_move.setToolTip("Move selected files to target mod")
        btn_move.setMinimumWidth(100)
        btn_move.setStyleSheet(
            "QPushButton { background-color: #8b4513; color: white; "
            "font-weight: bold; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #a0522d; }"
        )
        btn_move.clicked.connect(self._on_move_clicked)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(80)
        btn_cancel.clicked.connect(self.reject)

        action_layout.addStretch()
        action_layout.addWidget(btn_copy)
        action_layout.addWidget(btn_move)
        action_layout.addWidget(btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Check the files and folders you want to transfer.\n"
            "Then choose COPY (keep originals) or MOVE (delete originals):"
        ))
        layout.addWidget(self._tree)
        layout.addLayout(check_layout)
        layout.addLayout(action_layout)

        self._populate()
        self._tree.expandAll()

    def _on_copy_clicked(self):
        self._result_mode = "copy"
        self.done(self.RESULT_COPY)

    def _on_move_clicked(self):
        self._result_mode = "move"
        self.done(self.RESULT_MOVE)

    @property
    def result_mode(self):
        return self._result_mode

    def _populate(self):
        self._model.blockSignals(True)
        for mod_name, mod_path in self._mod_paths.items():
            mod_item = QStandardItem(mod_name)
            mod_item.setCheckable(True)
            mod_item.setCheckState(Qt.CheckState.Unchecked)
            mod_item.setData(mod_name, Qt.ItemDataRole.UserRole)
            mod_item.setData("", Qt.ItemDataRole.UserRole + 1)
            mod_item.setEditable(False)

            path_item = QStandardItem(str(mod_path))
            path_item.setEditable(False)

            self._model.appendRow([mod_item, path_item])
            self._add_directory(mod_item, mod_path, mod_name, "")
        self._model.blockSignals(False)

    def _add_directory(self, parent_item, dir_path, mod_name, rel_prefix):
        try:
            entries = sorted(os.listdir(dir_path),
                             key=lambda x: (not os.path.isdir(
                                 os.path.join(dir_path, x)), x.lower()))
        except OSError:
            return

        for entry in entries:
            full_path = os.path.join(dir_path, entry)
            rel_path = os.path.join(rel_prefix, entry) if rel_prefix else entry

            item = QStandardItem(entry)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(mod_name, Qt.ItemDataRole.UserRole)
            item.setData(rel_path, Qt.ItemDataRole.UserRole + 1)
            item.setEditable(False)

            path_display = QStandardItem(rel_path)
            path_display.setEditable(False)

            parent_item.appendRow([item, path_display])

            if os.path.isdir(full_path):
                self._add_directory(item, full_path, mod_name, rel_path)

    def _on_item_changed(self, item):
        self._model.blockSignals(True)
        state = item.checkState()
        self._set_children_check(item, state)
        self._update_parent_check(item)
        self._model.blockSignals(False)

    def _set_children_check(self, item, state):
        for r in range(item.rowCount()):
            child = item.child(r, 0)
            if child:
                child.setCheckState(state)
                self._set_children_check(child, state)

    def _update_parent_check(self, item):
        parent = item.parent()
        if parent is None:
            parent_index = self._model.indexFromItem(item).parent()
            if not parent_index.isValid():
                return
            parent = self._model.itemFromIndex(parent_index)
            if parent is None:
                return

        checked = 0
        unchecked = 0
        total = parent.rowCount()

        for r in range(total):
            child = parent.child(r, 0)
            if child:
                cs = child.checkState()
                if cs == Qt.CheckState.Checked:
                    checked += 1
                elif cs == Qt.CheckState.PartiallyChecked:
                    checked += 0.5
                else:
                    unchecked += 1

        if checked == total:
            parent.setCheckState(Qt.CheckState.Checked)
        elif unchecked == total:
            parent.setCheckState(Qt.CheckState.Unchecked)
        else:
            parent.setCheckState(Qt.CheckState.PartiallyChecked)

        self._update_parent_check(parent)

    def _select_all(self):
        self._model.blockSignals(True)
        for r in range(self._model.rowCount()):
            item = self._model.item(r, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
                self._set_children_check(item, Qt.CheckState.Checked)
        self._model.blockSignals(False)

    def _deselect_all(self):
        self._model.blockSignals(True)
        for r in range(self._model.rowCount()):
            item = self._model.item(r, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
                self._set_children_check(item, Qt.CheckState.Unchecked)
        self._model.blockSignals(False)

    def get_selected_files(self):
        result = []
        for r in range(self._model.rowCount()):
            item = self._model.item(r, 0)
            if item:
                mod_name = item.data(Qt.ItemDataRole.UserRole)
                self._collect_checked_leaves(item, mod_name, result)
        return result

    def _collect_checked_leaves(self, item, mod_name, result):
        if item.rowCount() == 0:
            if item.checkState() == Qt.CheckState.Checked:
                rel_path = item.data(Qt.ItemDataRole.UserRole + 1)
                if rel_path:
                    result.append((mod_name, rel_path))
        else:
            for r in range(item.rowCount()):
                child = item.child(r, 0)
                if child:
                    self._collect_checked_leaves(child, mod_name, result)


# ============================================================
#  Key filter
# ============================================================

class _KeyFilter(QObject):
    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin
        self._hotkeys = {}

    def register_hotkey(self, hotkey_str, callback):
        modifiers, key = parse_hotkey(hotkey_str)
        if key is not None:
            self._hotkeys[(modifiers, key)] = callback
            log.debug("Registered hotkey: %s", hotkey_str)
        else:
            log.warning("Failed to register hotkey: %s", hotkey_str)

    def clear_hotkeys(self):
        self._hotkeys.clear()

    def eventFilter(self, obj, event):
        # ── безопасность из NEW версии ──
        if obj is None or _is_deleted(obj):
            return False

        event_type = event.type()
        if event_type not in (QEvent.Type.KeyPress,
                              QEvent.Type.ShortcutOverride):
            return False

        modifiers = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.ShiftModifier |
            Qt.KeyboardModifier.AltModifier |
            Qt.KeyboardModifier.MetaModifier
        )
        key = event.key()

        callback = self._hotkeys.get((modifiers, key))
        if not callback:
            return False

        # ShortcutOverride: принять, чтобы потом получить KeyPress
        if event_type == QEvent.Type.ShortcutOverride:
            event.accept()
            return True

        try:
            callback()
        except Exception as e:
            log.error("Hotkey callback error: %s", e)
        return True


# ============================================================
#  Main plugin
# ============================================================

class MoveModsCtrlC_CtrlV(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self._organizer = None
        self._modList = None
        self._view = None
        self._filter = None
        self._clipboardMods = []
        self._cut_files = []
        self._file_mode = None

        self._SETTING_COPY_MODS = "hotkey_copy_mods"
        self._SETTING_PASTE_MODS = "hotkey_paste_mods"
        self._SETTING_PICK_FILES = "hotkey_pick_files"
        self._SETTING_PASTE_FILES = "hotkey_paste_files"

    def name(self):
        return "Move Mods (Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+B)"

    def author(self):
        return "User"

    def version(self):
        return mobase.VersionInfo(1, 3, 0)

    def description(self):
        return (
            "Ctrl+C/V — move entire mods across separators.\n"
            "Ctrl+X — pick files from selected mods (copy or move).\n"
            "Ctrl+B — paste picked files into target mod."
        )

    def settings(self):
        return [
            mobase.PluginSetting(
                self._SETTING_COPY_MODS,
                "Hotkey to copy selected mods to clipboard. "
                "Examples: Ctrl+C, Ctrl+1, F5, Ctrl+Shift+D",
                "Ctrl+C"
            ),
            mobase.PluginSetting(
                self._SETTING_PASTE_MODS,
                "Hotkey to paste mods from clipboard after selected mod. "
                "Examples: Ctrl+V, Ctrl+2, F6",
                "Ctrl+V"
            ),
            mobase.PluginSetting(
                self._SETTING_PICK_FILES,
                "Hotkey to open file picker dialog for selected mods. "
                "Examples: Ctrl+X, Ctrl+3, F7",
                "Ctrl+X"
            ),
            mobase.PluginSetting(
                self._SETTING_PASTE_FILES,
                "Hotkey to paste picked files into target mod. "
                "Examples: Ctrl+B, Ctrl+4, F8",
                "Ctrl+B"
            ),
        ]

    def isActive(self):
        return True

    def init(self, organizer: mobase.IOrganizer):
        self._organizer = organizer
        self._modList = organizer.modList()

        self._filter = _KeyFilter(self)
        self._register_hotkeys()

        QTimer.singleShot(2000, self._install_event_filter)

        log.info("Plugin initialized")
        return True

    # ────────────────────────────────────────────────────────
    #  ★ FIX: детекция конфликтов хоткеев
    # ────────────────────────────────────────────────────────

    def _register_hotkeys(self):
        self._filter.clear_hotkeys()

        hk_copy = self._organizer.pluginSetting(
            self.name(), self._SETTING_COPY_MODS)
        hk_paste = self._organizer.pluginSetting(
            self.name(), self._SETTING_PASTE_MODS)
        hk_pick = self._organizer.pluginSetting(
            self.name(), self._SETTING_PICK_FILES)
        hk_paste_files = self._organizer.pluginSetting(
            self.name(), self._SETTING_PASTE_FILES)

        # ── проверка конфликтов ─────────────────────────────
        all_hk = [
            ("copy_mods",   hk_copy),
            ("paste_mods",  hk_paste),
            ("pick_files",  hk_pick),
            ("paste_files", hk_paste_files),
        ]

        seen = {}
        conflicts = []
        for action, hk in all_hk:
            if not hk:
                continue
            norm = "+".join(p.strip().upper() for p in hk.split("+"))
            if norm in seen:
                conflicts.append(
                    f"'{hk}' → '{seen[norm]}' and '{action}'"
                )
                log.error("HOTKEY CONFLICT: %s used by '%s' and '%s'",
                          hk, seen[norm], action)
            seen[norm] = action

        if conflicts:
            msg = (
                "Hotkey conflict in MoveModsCtrlC_CtrlV!\n\n"
                + "\n".join(f"  • {c}" for c in conflicts)
                + "\n\nThe LAST registered action will win, the other "
                  "will be silently ignored.\n"
                  "Please fix in Settings → Plugins."
            )
            QTimer.singleShot(
                3000,
                lambda m=msg: self._show_warning(m),
            )
        # ────────────────────────────────────────────────────

        self._filter.register_hotkey(hk_copy, self.on_copy)
        self._filter.register_hotkey(hk_paste, self.on_paste)
        self._filter.register_hotkey(hk_pick, self.on_cut_files)
        self._filter.register_hotkey(hk_paste_files, self.on_paste_files)

        log.info("Hotkeys: copy=%s, paste=%s, pick=%s, paste_files=%s",
                 hk_copy, hk_paste, hk_pick, hk_paste_files)

    def _show_warning(self, message):
        try:
            QMessageBox.warning(
                None, "MoveModsCtrlC_CtrlV — Hotkey Conflict", message)
        except Exception:
            pass

    # ────────────────────────────────────────────────────────
    #  View discovery (улучшенная из NEW + переподключение)
    # ────────────────────────────────────────────────────────

    def _view_ready(self) -> bool:
        return self._view is not None and not _is_deleted(self._view)

    def _find_mod_list_view(self) -> QTreeView | None:
        known = ["modList", "modListView", "ModList", "leftPane"]

        for w in QApplication.allWidgets():
            if isinstance(w, QTreeView) and w.objectName() in known:
                return w

        candidates = []
        for w in QApplication.allWidgets():
            if not isinstance(w, QTreeView):
                continue
            m = w.model()
            if m is None:
                continue
            try:
                rows = m.rowCount()
            except Exception:
                continue
            candidates.append((rows, w))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _install_event_filter(self):
        view = self._find_mod_list_view()
        if view is None:
            log.warning("modList widget not found, retrying...")
            QTimer.singleShot(3000, self._install_event_filter)
            return

        if (self._view is not None
                and self._view is not view
                and not _is_deleted(self._view)):
            try:
                self._view.removeEventFilter(self._filter)
                vp = self._view.viewport()
                if vp is not None:
                    vp.removeEventFilter(self._filter)
            except Exception:
                pass

        self._view = view
        try:
            view.destroyed.connect(self._install_event_filter)
        except Exception:
            pass

        view.installEventFilter(self._filter)
        vp = view.viewport()
        if vp is not None:
            vp.installEventFilter(self._filter)

        log.info("Event filter installed on modList QTreeView")

    def _get_mod_path(self, mod_name):
        mods_dir = self._organizer.modsPath()
        mod_path = os.path.join(mods_dir, mod_name)
        if os.path.isdir(mod_path):
            return mod_path
        return None

    # ================================================================
    #  Ctrl+C — copy mods  (без изменений)
    # ================================================================

    def on_copy(self):
        if not self._view_ready():
            return

        sel_model = self._view.selectionModel()
        if sel_model is None:
            return

        indexes = sel_model.selectedRows(0)
        if not indexes:
            return

        model = self._view.model()
        if model is None:
            return

        collected_names = []
        seen = set()

        sorted_indexes = sorted(indexes, key=lambda i: (
            i.parent().row() if i.parent().isValid() else -1,
            i.row()
        ))

        for idx in sorted_indexes:
            if not idx.isValid():
                continue
            try:
                name = idx.data()
            except RuntimeError:
                return
            if name is None or name in seen:
                continue

            try:
                has_children = model.hasChildren(idx)
            except RuntimeError:
                return

            if has_children:
                seen.add(name)
                collected_names.append(name)
                try:
                    child_count = model.rowCount(idx)
                except RuntimeError:
                    return
                for r in range(child_count):
                    try:
                        child_name = model.index(r, 0, idx).data()
                    except RuntimeError:
                        return
                    if child_name and child_name not in seen:
                        seen.add(child_name)
                        collected_names.append(child_name)
            else:
                seen.add(name)
                collected_names.append(name)

        self._clipboardMods = collected_names
        log.info("Copied %d items", len(self._clipboardMods))

    # ================================================================
    #  ★ FIX: Ctrl+V — paste mods (ВОЗВРАТ к рабочему OLD подходу)
    #
    #  OLD использовал model.dropMimeData() — нативный механизм MO2.
    #  NEW заменил на allMods() + setPriority() — allMods() возвращает
    #  моды АЛФАВИТНО, что ломало весь порядок.
    # ================================================================

    def on_paste(self):
        if not self._clipboardMods or not self._view_ready():
            return

        model = self._view.model()
        if model is None:
            return

        sel_model = self._view.selectionModel()
        if sel_model is None:
            return

        current = sel_model.currentIndex()
        if not current.isValid():
            return

        try:
            anchor_mod = current.siblingAtColumn(0).data()
        except RuntimeError:
            return
        if not anchor_mod:
            return

        target_row, target_parent = self._get_paste_position(model, current)

        source_indexes = self._find_indexes_by_name(
            model, self._clipboardMods)
        if not source_indexes:
            return

        mime_data = model.mimeData(source_indexes)
        if mime_data is None:
            return

        # ── Нативный drop через модель MO2 ──
        success = model.dropMimeData(
            mime_data, Qt.DropAction.MoveAction,
            target_row, 0, target_parent
        )

        if success:
            log.info("dropMimeData succeeded")
            return

        # ── Fallback: эмуляция QDropEvent ──
        self._emulate_drop(mime_data, target_row, target_parent)

    def _get_paste_position(self, model, current_index):
        parent = current_index.parent()
        row = current_index.row() + 1
        return row, parent

    def _find_indexes_by_name(self, model, names):
        name_set = set(names)
        found = {}
        self._search_model(model, QModelIndex(), name_set, found)
        return [found[n] for n in names if n in found]

    def _search_model(self, model, parent, name_set, found):
        rows = model.rowCount(parent)
        for r in range(rows):
            idx = model.index(r, 0, parent)
            name = idx.data()
            if name in name_set and name not in found:
                found[name] = idx
                if len(found) == len(name_set):
                    return
            if model.hasChildren(idx):
                self._search_model(model, idx, name_set, found)
                if len(found) == len(name_set):
                    return

    def _emulate_drop(self, mime_data, target_row, target_parent):
        if not self._view_ready():
            return
        viewport = self._view.viewport()
        model = self._view.model()
        if viewport is None or model is None:
            return

        if target_row < model.rowCount(target_parent):
            target_idx = model.index(target_row, 0, target_parent)
            rect = self._view.visualRect(target_idx)
            drop_pos = QPoint(rect.center().x(), rect.top())
        else:
            last_row = model.rowCount(target_parent) - 1
            if last_row >= 0:
                last_idx = model.index(last_row, 0, target_parent)
                rect = self._view.visualRect(last_idx)
                drop_pos = QPoint(rect.center().x(), rect.bottom() + 1)
            else:
                drop_pos = QPoint(10, 10)

        drop_event = QDropEvent(
            drop_pos.toPointF(), Qt.DropAction.MoveAction,
            mime_data, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, QEvent.Type.Drop
        )
        QApplication.sendEvent(viewport, drop_event)

        if drop_event.isAccepted():
            log.info("Drop event accepted")
        else:
            log.warning("Drop event NOT accepted")

    # ================================================================
    #  Ctrl+X — pick files (без изменений)
    # ================================================================

    def on_cut_files(self):
        if not self._view_ready():
            return

        sel_model = self._view.selectionModel()
        if sel_model is None:
            return

        indexes = sel_model.selectedRows(0)
        if not indexes:
            return

        model = self._view.model()
        if model is None:
            return

        mod_names = []
        seen = set()

        for idx in sorted(indexes, key=lambda i: i.row()):
            name = idx.data()
            if name is None or name in seen:
                continue

            if model.hasChildren(idx):
                child_count = model.rowCount(idx)
                for r in range(child_count):
                    child_name = model.index(r, 0, idx).data()
                    if child_name and child_name not in seen:
                        seen.add(child_name)
                        mod_names.append(child_name)
            else:
                seen.add(name)
                mod_names.append(name)

        mod_paths = {}
        for mod_name in mod_names:
            path = self._get_mod_path(mod_name)
            if path:
                mod_paths[mod_name] = path

        if not mod_paths:
            return

        dialog = FilePickerDialog(mod_paths, self._view)
        result = dialog.exec()

        if result == QDialog.DialogCode.Rejected:
            log.debug("File picker cancelled")
            return

        selected = dialog.get_selected_files()
        mode = dialog.result_mode

        if not selected or mode is None:
            log.debug("No files selected or no mode")
            return

        self._cut_files = selected
        self._file_mode = mode

        log.info("%s %d files from %d mods (mode: %s)",
                 "Selected" if mode == "copy" else "Cut",
                 len(self._cut_files),
                 len(set(m for m, _ in self._cut_files)),
                 mode.upper())

    # ================================================================
    #  Ctrl+B — paste files (с overwrite_all из OLD)
    # ================================================================

    def on_paste_files(self):
        if not self._cut_files:
            log.debug("Ctrl+B: no files in buffer")
            return

        if not self._view_ready():
            return

        sel_model = self._view.selectionModel()
        if sel_model is None:
            return

        current = sel_model.currentIndex()
        if not current.isValid():
            return

        try:
            target_mod = current.siblingAtColumn(0).data()
        except RuntimeError:
            return
        if target_mod is None:
            return

        target_path = self._get_mod_path(target_mod)
        if target_path is None:
            log.error("Target mod path not found for '%s'", target_mod)
            return

        is_move = (self._file_mode == "move")
        action_word = "Move" if is_move else "Copy"

        log.info("%s %d files into '%s'",
                 action_word, len(self._cut_files), target_mod)

        conflicts = []
        for mod_name, rel_path in self._cut_files:
            dest = os.path.join(target_path, rel_path)
            if os.path.exists(dest):
                conflicts.append(rel_path)

        overwrite_all = False
        skip_all = False

        if conflicts:
            msg = (
                f"{len(conflicts)} file(s) already exist in "
                f"'{target_mod}'.\n\nExamples:\n"
            )
            for c in conflicts[:5]:
                msg += f"  • {c}\n"
            if len(conflicts) > 5:
                msg += f"  ... and {len(conflicts) - 5} more\n"
            msg += "\nOverwrite existing files?"

            reply = QMessageBox.question(
                self._view,
                "Files already exist",
                msg,
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Cancel:
                log.info("File paste cancelled")
                return
            elif reply == QMessageBox.StandardButton.Yes:
                overwrite_all = True
            else:
                skip_all = True

        moved = 0
        skipped = 0
        errors = 0

        for mod_name, rel_path in self._cut_files:
            src_mod_path = self._get_mod_path(mod_name)
            if src_mod_path is None:
                errors += 1
                continue

            src = os.path.join(src_mod_path, rel_path)
            dest = os.path.join(target_path, rel_path)

            if not os.path.exists(src):
                log.warning("Source missing: %s", src)
                errors += 1
                continue

            if os.path.exists(dest):
                if skip_all:
                    skipped += 1
                    continue

            try:
                dest_dir = os.path.dirname(dest)
                os.makedirs(dest_dir, exist_ok=True)

                if os.path.exists(dest):
                    if os.path.isdir(dest):
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)

                if is_move:
                    shutil.move(src, dest)
                else:
                    if os.path.isdir(src):
                        shutil.copytree(src, dest)
                    else:
                        shutil.copy2(src, dest)

                moved += 1

            except Exception as e:
                log.error("Error %s %s/%s: %s",
                          "moving" if is_move else "copying",
                          mod_name, rel_path, e)
                errors += 1

        if is_move:
            source_mods = set(mod_name for mod_name, _ in self._cut_files)
            for mod_name in source_mods:
                src_mod_path = self._get_mod_path(mod_name)
                if src_mod_path:
                    self._cleanup_empty_dirs(src_mod_path)

        self._cut_files = []
        self._file_mode = None

        summary = f"{action_word}d {moved} file(s) to '{target_mod}'."
        if skipped:
            summary += f"\nSkipped {skipped} existing file(s)."
        if errors:
            summary += f"\n{errors} error(s) occurred."

        log.info(summary)

        QMessageBox.information(
            self._view,
            f"File {action_word} Complete",
            summary
        )

        self._organizer.refresh()

    def _cleanup_empty_dirs(self, root_path):
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
            if dirpath == root_path:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass


def createPlugin():
    return MoveModsCtrlC_CtrlV()