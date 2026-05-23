import mobase
import json
import os
import time
import copy
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QToolButton,
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QTextEdit, QLabel, QLineEdit, QMenu,
    QAbstractItemView, QSplitter, QMessageBox, QInputDialog,
    QHeaderView, QWidget, QFileDialog, QStatusBar, QComboBox,
    QCheckBox, QFrame, QSizePolicy, QStyle, QStyledItemDelegate
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QColor, QPainter, QPen, QBrush,
    QAction, QKeySequence, QFont, QShortcut
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QSize, QMimeData, QRect, QEvent


# ═══════════════════════════════════════════════════════
#  Константы и утилиты
# ═══════════════════════════════════════════════════════

GROUP_COLORS = {
    "None":    None,
    "Red":     QColor(239, 83, 80),
    "Orange":  QColor(255, 167, 38),
    "Yellow":  QColor(255, 238, 88),
    "Green":   QColor(102, 187, 106),
    "Blue":    QColor(66, 165, 245),
    "Purple":  QColor(171, 71, 188),
    "Grey":    QColor(158, 158, 158),
}

SORT_OPTIONS = [
    "Manual (drag & drop)",
    "A → Z",
    "Z → A",
    "Most used first",
    "Recently used first",
]


def make_pl_icon(size=18) -> QIcon:
    """Единая иконка PL — оранжевый контур + буквы PL, без заливки"""
    color = QColor("#d67500")

    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # Только контур, без заливки
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(color, 1.5))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)

    # Буквы "PL"
    font = QFont("Arial", max(size // 3, 6), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(color)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "✨")

    p.end()
    return QIcon(px)


def make_colored_icon(color: QColor, size=16) -> QIcon:
    return make_pl_icon(size)


def make_folder_icon(color: QColor = None) -> QIcon:
    return make_pl_icon(18)


def make_star_icon(filled=True) -> QIcon:
    return make_pl_icon(16)


def make_plugin_icon() -> QIcon:
    return make_pl_icon(24)


# ═══════════════════════════════════════════════════════
#  Кастомное дерево с контролем DnD
# ═══════════════════════════════════════════════════════

class ToolTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAnimated(True)
        self.setIndentation(20)
        self.setAlternatingRowColors(True)

    def dropEvent(self, event):
        dragged = self.currentItem()
        if not dragged:
            event.ignore()
            return

        dragged_data = dragged.data(0, Qt.ItemDataRole.UserRole) or {}
        target = self.itemAt(event.position().toPoint())

        if dragged_data.get("type") == "group":
            if target is not None:
                target_data = target.data(0, Qt.ItemDataRole.UserRole) or {}
                if target_data.get("type") != "group" and target.parent():
                    event.ignore()
                    return
            super().dropEvent(event)
            return

        if dragged_data.get("type") == "tool":
            if target is None:
                event.ignore()
                return
            target_data = target.data(0, Qt.ItemDataRole.UserRole) or {}
            if target_data.get("type") == "group":
                super().dropEvent(event)
            elif target_data.get("type") == "tool" and target.parent():
                super().dropEvent(event)
            else:
                event.ignore()
                return
        else:
            super().dropEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            item = self.currentItem()
            if item:
                data = item.data(0, Qt.ItemDataRole.UserRole) or {}
                if data.get("type") == "tool":
                    # Toggle favorite
                    parent_dialog = self.parent()
                    while parent_dialog and not isinstance(parent_dialog, ToolManagerDialog):
                        parent_dialog = parent_dialog.parent()
                    if parent_dialog:
                        parent_dialog._toggle_favorite(item)
                    return
        super().keyPressEvent(event)


# ═══════════════════════════════════════════════════════
#  Диалог менеджера
# ═══════════════════════════════════════════════════════

class ToolManagerDialog(QDialog):
    def __init__(self, parent, actions_dict, config, config_path):
        super().__init__(parent)
        self._actions = actions_dict
        self._config = config
        self._config_path = config_path
        self._undo_stack = []
        self._max_undo = 10

        self.setWindowTitle("🔧 Tools Manager")
        self.setWindowIcon(make_plugin_icon())
        self.resize(780, 620)
        self.setMinimumSize(500, 400)

        self._build_ui()
        self._setup_shortcuts()
        self._sync_and_populate()
        self._update_status()

    # ─── UI ───

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Верхняя панель: поиск + сортировка ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search tools... (Ctrl+F)")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        top_bar.addWidget(self._search, 3)

        top_bar.addWidget(QLabel("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(SORT_OPTIONS)
        self._sort_combo.currentIndexChanged.connect(self._apply_sort)
        top_bar.addWidget(self._sort_combo, 1)

        self._fav_filter = QCheckBox("★ Only")
        self._fav_filter.setToolTip("Show only favorites")
        self._fav_filter.toggled.connect(self._filter)
        top_bar.addWidget(self._fav_filter)

        root.addLayout(top_bar)

        # ── Основной сплиттер ──
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Дерево
        self._tree = ToolTree()
        self._tree.setHeaderLabels(["Name", "Original Name", "Uses", "★"])
        self._tree.setColumnCount(4)

        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 50)
        header.resizeSection(3, 30)

        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._ctx_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemSelectionChanged.connect(self._sel_changed)
        self._tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 3px 2px;
                min-height: 24px;
            }
            QTreeWidget::item:selected {
                background: #0078d7;
                color: white;
            }
            QTreeWidget::item:hover:!selected {
                background: #e3f2fd;
            }
        """)
        splitter.addWidget(self._tree)

        # Панель описания
        desc_box = QWidget()
        desc_lay = QVBoxLayout(desc_box)
        desc_lay.setContentsMargins(0, 4, 0, 0)
        desc_lay.setSpacing(2)

        desc_header = QHBoxLayout()
        desc_header.addWidget(QLabel("📝 Description:"))
        self._desc_tool_label = QLabel("")
        self._desc_tool_label.setStyleSheet("color: #666; font-style: italic;")
        desc_header.addWidget(self._desc_tool_label)
        desc_header.addStretch()
        desc_lay.addLayout(desc_header)

        self._desc = QTextEdit()
        self._desc.setMaximumHeight(90)
        self._desc.setPlaceholderText("Write a description for the selected tool…")
        self._desc.textChanged.connect(self._desc_changed)
        self._desc.setEnabled(False)
        self._desc.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        desc_lay.addWidget(self._desc)
        splitter.addWidget(desc_box)

        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        # ── Кнопки ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        buttons_left = [
            ("📁 + Group",   self._add_group,  "Create new group"),
            ("✏️ Rename",    self._rename_sel,  "Rename selected (F2)"),
            ("★ Favorite",   self._toggle_favorite_sel, "Toggle favorite (Space)"),
        ]
        for text, slot, tip in buttons_left:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            btn_row.addWidget(b)

        btn_row.addStretch()

        # Правая группа кнопок
        buttons_right = [
            ("↩ Undo",       self._undo,          "Undo last action"),
            ("📥 Import",    self._import_config,  "Import configuration"),
            ("📤 Export",    self._export_config,  "Export configuration"),
            ("▶ Run",        self._run_selected,   "Run selected tool (Enter)"),
            ("💾 Save",      self._save,           "Save configuration"),
            ("Close",        self.close,           "Close dialog"),
        ]
        for text, slot, tip in buttons_right:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            if text == "▶ Run":
                b.setStyleSheet("QPushButton { background: #4CAF50; color: white; font-weight: bold; padding: 4px 12px; border-radius: 3px; }")
            elif text == "💾 Save":
                b.setStyleSheet("QPushButton { background: #2196F3; color: white; font-weight: bold; padding: 4px 12px; border-radius: 3px; }")
            btn_row.addWidget(b)

        root.addLayout(btn_row)

        # ── Статус-бар ──
        self._status = QLabel("")
        self._status.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        root.addWidget(self._status)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F2"), self, self._rename_sel)
        QShortcut(QKeySequence("Delete"), self, self._delete_selected)
        QShortcut(QKeySequence("Return"), self, self._run_selected)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self._search.setFocus())
        QShortcut(QKeySequence("Ctrl+G"), self, self._add_group)
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo)
        QShortcut(QKeySequence("Ctrl+S"), self, self._save)
        QShortcut(QKeySequence("Ctrl+E"), self, self._expand_all)
        QShortcut(QKeySequence("Ctrl+W"), self, self._collapse_all)

    # ─── Undo ───

    def _save_undo(self, label="action"):
        snapshot = copy.deepcopy(self._config)
        tree_state = self._serialize_tree()
        self._undo_stack.append((label, snapshot, tree_state))
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            self._flash_status("Nothing to undo")
            return
        label, snapshot, tree_state = self._undo_stack.pop()
        self._config = snapshot
        self._restore_tree(tree_state)
        self._flash_status(f"Undone: {label}")

    def _serialize_tree(self):
        groups = []
        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            items = []
            for j in range(group.childCount()):
                child = group.child(j)
                data = child.data(0, Qt.ItemDataRole.UserRole) or {}
                if data.get("type") == "tool":
                    items.append(data["key"])
            groups.append({
                "name": group.text(0),
                "items": items,
                "expanded": group.isExpanded()
            })
        return groups

    def _restore_tree(self, tree_state):
        self._tree.clear()
        for g in tree_state:
            gi = self._make_group(g["name"])
            for key in g["items"]:
                if key in self._actions:
                    self._make_tool(gi, key)
            gi.setExpanded(g.get("expanded", True))
        self._update_status()

    # ─── Populate ───

    def _sync_and_populate(self):
        real_keys = set(self._actions.keys())
        groups = self._config.get("groups", [])

        placed = set()
        cleaned_groups = []
        for g in groups:
            items = [k for k in g.get("items", []) if k in real_keys]
            placed.update(items)
            cleaned_groups.append({
                "name": g["name"],
                "items": items,
                "color": g.get("color"),
                "collapsed": g.get("collapsed", False)
            })

        new_tools = sorted(real_keys - placed, key=str.lower)

        if not cleaned_groups and not groups:
            cleaned_groups = [{
                "name": "All Tools",
                "items": sorted(real_keys, key=str.lower)
            }]
            new_tools = []

        self._config["groups"] = cleaned_groups
        self._tree.clear()

        for g in cleaned_groups:
            color_name = g.get("color")
            color = GROUP_COLORS.get(color_name) if color_name else None
            gi = self._make_group(g["name"], color)
            for key in g["items"]:
                self._make_tool(gi, key)
            gi.setExpanded(not g.get("collapsed", False))

        if new_tools:
            gi = self._make_group("New / Ungrouped", QColor(158, 158, 158))
            for key in new_tools:
                self._make_tool(gi, key)
            gi.setExpanded(True)

    def _make_group(self, name, color=None):
        item = QTreeWidgetItem(self._tree)
        item.setText(0, name)
        item.setText(1, "")
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "group", "color": color})
        item.setIcon(0, make_folder_icon(color))

        font = item.font(0)
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        item.setFont(0, font)

        if color:
            lighter = QColor(color)
            lighter.setAlpha(30)
            item.setBackground(0, QBrush(lighter))

        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsDropEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        return item

    def _make_tool(self, parent, key):
        display = self._config.get("customNames", {}).get(key, key)
        uses = self._config.get("usageCount", {}).get(key, 0)
        is_fav = key in self._config.get("favorites", [])

        item = QTreeWidgetItem(parent)
        item.setText(0, display)
        item.setText(1, key if display != key else "")
        item.setText(2, str(uses) if uses > 0 else "")
        item.setText(3, "★" if is_fav else "")
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "tool", "key": key})

        # Выравнивание
        item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignCenter)

        # Иконка
        action = self._actions.get(key)
        if action and not action.icon().isNull():
            item.setIcon(0, action.icon())
        else:
            item.setIcon(0, make_colored_icon(QColor(100, 181, 246)))

        # Цвет звёздочки
        if is_fav:
            item.setForeground(3, QBrush(QColor(255, 193, 7)))
            font3 = item.font(3)
            font3.setPointSize(font3.pointSize() + 2)
            item.setFont(3, font3)

        item.setFlags(
            (item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            & ~Qt.ItemFlag.ItemIsDropEnabled
        )
        return item

    # ─── Actions ───

    def _on_double_click(self, item, col):
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "tool":
            if col == 3:
                self._toggle_favorite(item)
            else:
                self._run_item(item)
        elif data.get("type") == "group":
            item.setExpanded(not item.isExpanded())

    def _run_selected(self):
        items = self._tree.selectedItems()
        if items:
            self._run_item(items[0])

    def _run_item(self, item):
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "tool":
            return
        key = data.get("key")
        action = self._actions.get(key)
        if not action:
            return

        try:
            from PyQt6 import sip
            if sip.isdeleted(action):
                QMessageBox.warning(self, "Error", "Action no longer exists.")
                return
        except ImportError:
            pass

        # Обновить статистику
        counts = self._config.setdefault("usageCount", {})
        counts[key] = counts.get(key, 0) + 1
        self._config.setdefault("lastUsed", {})[key] = time.time()
        item.setText(2, str(counts[key]))

        self.close()
        action.trigger()

    def _sel_changed(self):
        self._desc.blockSignals(True)
        items = self._tree.selectedItems()

        if not items:
            self._desc.clear()
            self._desc.setEnabled(False)
            self._desc_tool_label.setText("")
            self._desc.blockSignals(False)
            return

        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "tool":
            key = data["key"]
            self._desc.setText(
                self._config.get("descriptions", {}).get(key, ""))
            self._desc.setEnabled(True)
            self._desc_tool_label.setText(f"  — {key}")
        else:
            self._desc.clear()
            self._desc.setEnabled(False)
            self._desc_tool_label.setText(f"  — Group: {item.text(0)}")

        self._desc.blockSignals(False)
        self._update_status()

    def _desc_changed(self):
        items = self._tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "tool":
            return
        self._config.setdefault("descriptions", {})[
            data["key"]] = self._desc.toPlainText()

    # ─── Favorites ───

    def _toggle_favorite_sel(self):
        for item in self._tree.selectedItems():
            self._toggle_favorite(item)

    def _toggle_favorite(self, item):
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "tool":
            return

        key = data["key"]
        favs = self._config.setdefault("favorites", [])

        if key in favs:
            favs.remove(key)
            item.setText(3, "")
            item.setForeground(3, QBrush(QColor(200, 200, 200)))
        else:
            favs.append(key)
            item.setText(3, "★")
            item.setForeground(3, QBrush(QColor(255, 193, 7)))
            font3 = item.font(3)
            font3.setPointSize(font3.pointSize() + 2)
            item.setFont(3, font3)

    # ─── Groups ───

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if ok and name.strip():
            self._save_undo("add group")
            gi = self._make_group(name.strip())
            self._tree.setCurrentItem(gi)
            self._flash_status(f"Group '{name.strip()}' created")
            self._update_status()

    def _set_group_color(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "group":
            return

        color_names = list(GROUP_COLORS.keys())
        chosen, ok = QInputDialog.getItem(
            self, "Group Color", "Choose color:",
            color_names, 0, False)
        if not ok:
            return

        self._save_undo("change group color")
        color = GROUP_COLORS[chosen]
        data["color"] = color
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        item.setIcon(0, make_folder_icon(color))

        if color:
            lighter = QColor(color)
            lighter.setAlpha(30)
            item.setBackground(0, QBrush(lighter))
        else:
            item.setBackground(0, QBrush())

    def _delete_group(self, item):
        name = item.text(0)
        child_count = item.childCount()

        if child_count > 0:
            reply = QMessageBox.question(
                self, "Delete Group",
                f"Delete group '{name}'?\n"
                f"{child_count} tool(s) will be moved to 'Ungrouped'.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._save_undo("delete group")

        # Найти или создать Ungrouped
        ungrouped = None
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            if top.text(0) == "Ungrouped":
                ungrouped = top
                break
        if not ungrouped and child_count > 0:
            ungrouped = self._make_group("Ungrouped", QColor(158, 158, 158))

        while item.childCount():
            child = item.takeChild(0)
            if ungrouped:
                ungrouped.addChild(child)

        idx = self._tree.indexOfTopLevelItem(item)
        if idx >= 0:
            self._tree.takeTopLevelItem(idx)

        self._flash_status(f"Group '{name}' deleted")
        self._update_status()

    def _delete_selected(self):
        items = self._tree.selectedItems()
        if not items:
            return
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}

        if data.get("type") == "group":
            self._delete_group(item)
        elif data.get("type") == "tool":
            # Перемещаем в Ungrouped
            parent = item.parent()
            if not parent:
                return

            self._save_undo("remove tool from group")

            ungrouped = None
            for i in range(self._tree.topLevelItemCount()):
                top = self._tree.topLevelItem(i)
                if top.text(0) == "Ungrouped":
                    ungrouped = top
                    break
            if not ungrouped:
                ungrouped = self._make_group("Ungrouped", QColor(158, 158, 158))

            idx = parent.indexOfChild(item)
            taken = parent.takeChild(idx)
            ungrouped.addChild(taken)
            self._flash_status(f"'{item.text(0)}' moved to Ungrouped")

    # ─── Rename ───

    def _rename_sel(self):
        items = self._tree.selectedItems()
        if not items:
            return
        item = items[0]
        old = item.text(0)
        new, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=old)
        if not ok or not new.strip() or new.strip() == old:
            return

        self._save_undo("rename")
        item.setText(0, new.strip())
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") == "tool":
            self._config.setdefault("customNames", {})[
                data["key"]] = new.strip()
            item.setText(1, data["key"])

    def _reset_name(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if data.get("type") != "tool":
            return
        self._save_undo("reset name")
        key = data["key"]
        item.setText(0, key)
        item.setText(1, "")
        self._config.get("customNames", {}).pop(key, None)

    # ─── Sorting ───

    def _apply_sort(self, index):
        if index == 0:
            return  # Manual

        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            children = []
            while group.childCount():
                children.append(group.takeChild(0))

            if index == 1:  # A-Z
                children.sort(key=lambda c: c.text(0).lower())
            elif index == 2:  # Z-A
                children.sort(key=lambda c: c.text(0).lower(), reverse=True)
            elif index == 3:  # Most used
                counts = self._config.get("usageCount", {})
                children.sort(
                    key=lambda c: counts.get(
                        (c.data(0, Qt.ItemDataRole.UserRole) or {}).get("key", ""), 0),
                    reverse=True
                )
            elif index == 4:  # Recently used
                last_used = self._config.get("lastUsed", {})
                children.sort(
                    key=lambda c: last_used.get(
                        (c.data(0, Qt.ItemDataRole.UserRole) or {}).get("key", ""), 0),
                    reverse=True
                )

            for child in children:
                group.addChild(child)

    # ─── Filter ───

    def _filter(self, *_):
        text = self._search.text().lower()
        fav_only = self._fav_filter.isChecked()
        favs = set(self._config.get("favorites", []))

        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            any_visible = False

            for j in range(group.childCount()):
                child = group.child(j)
                data = child.data(0, Qt.ItemDataRole.UserRole) or {}
                key = data.get("key", "")

                match_text = (not text or
                              text in child.text(0).lower() or
                              text in child.text(1).lower() or
                              text in key.lower())

                match_fav = (not fav_only or key in favs)

                visible = match_text and match_fav
                child.setHidden(not visible)
                if visible:
                    any_visible = True

            group.setHidden(not any_visible and (bool(text) or fav_only))

    # ─── Expand/Collapse ───

    def _expand_all(self):
        self._tree.expandAll()

    def _collapse_all(self):
        self._tree.collapseAll()

    # ─── Context menu ───

    def _ctx_menu(self, pos):
        item = self._tree.itemAt(pos)
        m = QMenu(self)

        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}

            if data.get("type") == "tool":
                key = data.get("key", "")
                is_fav = key in self._config.get("favorites", [])

                run_action = m.addAction("▶  Run")
                run_action.triggered.connect(lambda: self._run_item(item))

                fav_text = "☆  Remove from favorites" if is_fav else "★  Add to favorites"
                fav_action = m.addAction(fav_text)
                fav_action.triggered.connect(lambda: self._toggle_favorite(item))

                m.addSeparator()
                m.addAction("✏️  Rename (F2)").triggered.connect(self._rename_sel)
                m.addAction("↩  Reset name").triggered.connect(lambda: self._reset_name(item))
                m.addSeparator()
                m.addAction("🗑  Remove from group (Del)").triggered.connect(self._delete_selected)

            elif data.get("type") == "group":
                m.addAction("✏️  Rename group").triggered.connect(self._rename_sel)
                m.addAction("🎨  Set color").triggered.connect(lambda: self._set_group_color(item))
                m.addSeparator()
                m.addAction("🗑  Delete group").triggered.connect(lambda: self._delete_group(item))

        m.addSeparator()
        m.addAction("📁  New group (Ctrl+G)").triggered.connect(self._add_group)
        m.addSeparator()
        m.addAction("🔽  Expand all (Ctrl+E)").triggered.connect(self._expand_all)
        m.addAction("🔼  Collapse all (Ctrl+W)").triggered.connect(self._collapse_all)

        m.exec(self._tree.viewport().mapToGlobal(pos))

    # ─── Import / Export ───

    def _export_config(self):
        self._collect_config_from_tree()
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Configuration",
            "tools_manager_config.json",
            "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            self._flash_status(f"Exported to {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", str(e))

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Configuration", "",
            "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                new_config = json.load(f)

            self._save_undo("import config")
            self._config.update(new_config)
            self._sync_and_populate()
            self._flash_status(f"Imported from {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Import Error", str(e))

    # ─── Save ───

    def _collect_config_from_tree(self):
        groups = []
        for i in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(i)
            items = []
            for j in range(group.childCount()):
                child = group.child(j)
                data = child.data(0, Qt.ItemDataRole.UserRole) or {}
                if data.get("type") == "tool":
                    items.append(data["key"])

            group_data = group.data(0, Qt.ItemDataRole.UserRole) or {}
            color = group_data.get("color")
            color_name = None
            if color:
                for cname, cval in GROUP_COLORS.items():
                    if cval and cval == color:
                        color_name = cname
                        break

            groups.append({
                "name": group.text(0),
                "items": items,
                "color": color_name,
                "collapsed": not group.isExpanded()
            })

        self._config["groups"] = groups

    def _save(self):
        self._collect_config_from_tree()

        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            self._flash_status("✅ Configuration saved!")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    # ─── Status ───

    def _update_status(self):
        total_tools = 0
        total_groups = self._tree.topLevelItemCount()
        for i in range(total_groups):
            total_tools += self._tree.topLevelItem(i).childCount()

        favs = len(self._config.get("favorites", []))
        sel = len(self._tree.selectedItems())

        parts = [f"{total_tools} tools", f"{total_groups} groups"]
        if favs:
            parts.append(f"{favs} favorites")
        if sel:
            parts.append(f"{sel} selected")
        if self._undo_stack:
            parts.append(f"{len(self._undo_stack)} undo")

        self._status.setText("  |  ".join(parts))

    def _flash_status(self, msg):
        self._status.setText(msg)
        QTimer.singleShot(3000, self._update_status)

    def event(self, e):
        if e.type() == QEvent.Type.WindowDeactivate:
            # Не прячем сразу — даём время дочернему диалогу (Rename и т.д.) взять фокус
            QTimer.singleShot(150, self._check_should_hide)
        return super().event(e)

    def _check_should_hide(self):
        """Прячем flyout, только если фокус ушёл НЕ в дочерний диалог."""
        if not self.isVisible():
            return

        # Если flyout снова активен — не трогаем
        active = QApplication.activeWindow()
        if active is self:
            return

        # Если открыт дочерний диалог (QInputDialog, QMessageBox, QFileDialog…) — не трогаем
        if active is not None and active.parent() is self:
            return

        # Если открыт любой модальный виджет — не трогаем
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return

        self.hide()

# ═══════════════════════════════════════════════════════
#  Главный плагин
# ═══════════════════════════════════════════════════════

class ToolsManager(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._organizer = None
        self._config = {}
        self._config_path = ""
        self._toolbar_button = None
        self._retry_count = 0
        self._tools_menu = None
        self._flyout_dialog = None

    def init(self, organizer):
        self._organizer = organizer
        self._config_path = os.path.join(
            organizer.basePath(),
            "plugin_data", "tools_manager", "config.json"
        )
        self._load_config()
        QTimer.singleShot(3000, self._setup_toolbar)
        return True

    def name(self):
        return "Tools Manager"

    def author(self):
        return "User"

    def description(self):
        return "Manage and organize tool plugins with groups, favorites, and sorting"

    def version(self):
        return mobase.VersionInfo(2, 0, 0)

    def requirements(self):
        return []

    def settings(self):
        return []

    def displayName(self):
        return "Tools Manager"

    def tooltip(self):
        return "Organize tool plugins into groups with favorites and sorting"

    def icon(self):
        return make_plugin_icon()

    def display(self):
        self._open_manager()

    # ── Основная логика ──

    def _open_manager(self):
        actions = self._get_tool_actions()
        if not actions:
            QMessageBox.warning(
                self._main_window(), "Tools Manager",
                "No tool plugins found!")
            return

        mw = self._main_window()
        if not mw:
            return

        dlg = self._flyout_dialog
        if dlg is not None and dlg.isVisible():
            dlg.hide()
            return

        if dlg is None:
            dlg = ToolManagerDialog(mw, actions, self._config, self._config_path)
            dlg.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self._flyout_dialog = dlg
        else:
            dlg._actions = actions
            dlg._sync_and_populate()
            dlg._update_status()

        anchor = self._toolbar_button or mw
        if isinstance(anchor, QToolButton):
            global_pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        else:
            global_pos = mw.mapToGlobal(QPoint(0, 0))

        dlg.move(global_pos)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ── Toolbar setup ──

    def _setup_toolbar(self):
        mw = self._main_window()
        if not mw:
            self._retry()
            return

        for tb in mw.findChildren(QToolBar):
            actions_list = tb.actions()

            for i, action in enumerate(actions_list):
                menu = self._find_menu(action, tb)
                if self._is_tools_menu(menu):
                    self._tools_menu = menu

                    btn = QToolButton(tb)
                    btn.setToolTip("Tools Manager — organize your tool plugins")
                    btn.setAutoRaise(True)
                    btn.setIcon(make_plugin_icon())
                    btn.setIconSize(QSize(30, 30))
                    btn.clicked.connect(self._open_manager)

                    # ─────────────── Главное изменение ───────────────
                    # Вставляем в САМОЕ начало тулбара
                    if actions_list:  # если в тулбаре уже есть хоть одно действие
                        tb.insertWidget(actions_list[0], btn)
                    else:
                        tb.addWidget(btn)  # на пустой тулбар просто добавляем

                    self._toolbar_button = btn
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
            da = widget.defaultAction()
            if da:
                menu = da.menu()
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
        for a in menu.actions():
            if self._normalize_text(a.text()) == target:
                return True
        return False

    def _is_tools_menu(self, menu):
        if not menu:
            return False
        return self._menu_title_matches(menu) or self._menu_has_plugin_action(menu)

    def _find_tools_menu_in_window(self, mw):
        menus = mw.findChildren(QMenu)
        for menu in menus:
            if self._menu_title_matches(menu):
                return menu
        for menu in menus:
            if self._menu_has_plugin_action(menu):
                return menu
        return None

    def _force_populate_menu(self, menu):
        if not menu:
            return
        menu.aboutToShow.emit()
        if len(menu.actions()) == 0:
            menu.popup(QPoint(-9999, -9999))
            menu.hide()

    def _get_tool_actions(self):
        menu = self._tools_menu

        if not menu:
            mw = self._main_window()
            if not mw:
                return {}
            for tb in mw.findChildren(QToolBar):
                for action in tb.actions():
                    candidate = self._find_menu(action, tb)
                    if self._is_tools_menu(candidate):
                        menu = candidate
                        self._tools_menu = menu
                        break
                if menu:
                    break
            if not menu:
                menu = self._find_tools_menu_in_window(mw)
                if menu:
                    self._tools_menu = menu

        if not menu:
            return {}

        self._force_populate_menu(menu)

        result = {}
        for a in menu.actions():
            if a.isSeparator():
                continue
            name = a.text().replace("&", "")
            if name == "Tools Manager":
                continue
            result[name] = a
        return result

    def _hide_self_from_menu(self):
        if not self._tools_menu:
            return

        def _do_hide():
            for a in self._tools_menu.actions():
                if a.text().replace("&", "") == "Tools Manager":
                    a.setVisible(False)
                    break

        _do_hide()
        self._tools_menu.aboutToShow.connect(_do_hide)

    def _main_window(self):
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMainWindow):
                return w
        return None

    def _load_config(self):
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                return
            except Exception:
                pass
        self._config = {
            "groups": [],
            "customNames": {},
            "descriptions": {},
            "favorites": [],
            "usageCount": {},
            "lastUsed": {}
        }


def createPlugin():
    return ToolsManager()
