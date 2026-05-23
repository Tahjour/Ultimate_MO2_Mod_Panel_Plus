import mobase
from PyQt6.QtCore import Qt, QSettings, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QVBoxLayout,
    QWidget,
)


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

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.mod_list_widget = QListWidget(self)
        self.mod_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mod_list_widget.setAlternatingRowColors(True)
        self._set_rows_height(self.mod_list_widget, 20, fixed=True)
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
        recent_layout.addWidget(self.recent_list_widget)

        clear_btn = QPushButton("Clear Recent History", self)
        clear_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_btn)

        splitter.addWidget(recent_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _set_rows_height(self, view: QListWidget, rows: int, fixed: bool) -> int:
        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = view.fontMetrics().height() + 6
        height = row_height * rows + view.frameWidth() * 2
        if fixed:
            view.setMinimumHeight(height)
            view.setMaximumHeight(height)
        else:
            view.setMinimumHeight(0)
            view.setMaximumHeight(height)
        return height

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
        all_mods = list(self.mod_list.allMods())

        def _priority(name: str) -> int:
            try:
                return int(self.mod_list.priority(name))
            except Exception:
                return 0

        all_mods.sort(key=_priority)

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

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.plugin_list_widget = QListWidget(self)
        self.plugin_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.plugin_list_widget.setAlternatingRowColors(True)
        self._set_plugin_rows_height(self.plugin_list_widget, 20, fixed=True)
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
        recent_layout.addWidget(self.recent_list_widget)

        clear_btn = QPushButton("Clear History", self)
        clear_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_btn)

        splitter.addWidget(recent_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

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

    def _set_plugin_rows_height(self, view: QListWidget, rows: int, fixed: bool) -> int:
        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = view.fontMetrics().height() + 6
        height = row_height * rows + view.frameWidth() * 2
        if fixed:
            view.setMinimumHeight(height)
            view.setMaximumHeight(height)
        else:
            view.setMinimumHeight(0)
            view.setMaximumHeight(height)
        return height

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

    def _find_plugin_index(self, name: str):
        model = self.plugins_view.model()
        if not model:
            return None

        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            name,
            1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )

        if not matches:
            matches = model.match(
                model.index(0, 0),
                Qt.ItemDataRole.DisplayRole,
                name,
                1,
                Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive,
            )

        if matches:
            return matches[0]
        return None

    def _smooth_scroll_to_index(self, index):
        view = self.plugins_view
        scrollbar = view.verticalScrollBar()

        if not scrollbar:
            view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            return

        parent = index.parent()
        while parent.isValid():
            view.expand(parent)
            parent = parent.parent()

        start = scrollbar.value()
        view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        end = scrollbar.value()

        if start == end:
            return

        scrollbar.setValue(start)

        anim = QPropertyAnimation(scrollbar, b"value", view)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim = anim
        anim.start()

    def _select_plugin_in_view(self, item: QListWidgetItem, add_to_recent: bool = True):
        if not item:
            return

        plugin_name = item.data(Qt.ItemDataRole.UserRole)

        if not self.plugins_view or not self.plugins_view.model():
            self.plugin_selected.emit("Error: Plugins view not available")
            return

        index = self._find_plugin_index(plugin_name)

        if index:
            self.plugins_view.setCurrentIndex(index)
            self.plugins_view.setFocus()
            self._smooth_scroll_to_index(index)

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


class ModNotesSearchTab(QWidget):
    SETTINGS_KEY = "FullModSearch"
    MAX_RECENT_ITEMS = 10

    mod_selected = pyqtSignal(str)

    def __init__(self, parent, organizer: "mobase.IOrganizer", mods_view: "QTreeView", mod_list: "mobase.IModList"):
        super().__init__(parent)
        self._organizer = organizer
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
        self.search_input.setPlaceholderText("Search in notes or descriptions...")
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        self.case_sensitive_cb = QCheckBox("Case Sensitive", self)
        search_layout.addWidget(self.case_sensitive_cb)

        layout.addLayout(search_layout)

        scope_layout = QHBoxLayout()

        self.notes_cb = QCheckBox("Notes", self)
        self.notes_cb.setChecked(True)
        scope_layout.addWidget(self.notes_cb)

        self.description_cb = QCheckBox("Description", self)
        self.description_cb.setChecked(True)
        scope_layout.addWidget(self.description_cb)

        scope_layout.addStretch()
        layout.addLayout(scope_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        results_group = QGroupBox("Search Results", self)
        results_group.setFlat(True)
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(4, 2, 4, 2)

        self.mod_list_widget = QListWidget(self)
        self.mod_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mod_list_widget.setAlternatingRowColors(True)
        self._set_rows_height(self.mod_list_widget, 20, fixed=True)
        results_layout.addWidget(self.mod_list_widget)

        self.results_label = QLabel("0 mods found", self)
        results_layout.addWidget(self.results_label)

        splitter.addWidget(results_group)

        recent_group = QGroupBox("Recent Selections", self)
        recent_group.setFlat(True)
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(4, 2, 4, 2)

        self.recent_list_widget = QListWidget(self)
        self.recent_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.recent_list_widget.setAlternatingRowColors(True)
        recent_layout.addWidget(self.recent_list_widget)

        clear_btn = QPushButton("Clear History", self)
        clear_btn.clicked.connect(self._clear_recent)
        recent_layout.addWidget(clear_btn)

        splitter.addWidget(recent_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _set_rows_height(self, view: QListWidget, rows: int, fixed: bool) -> int:
        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = view.fontMetrics().height() + 6
        height = row_height * rows + view.frameWidth() * 2
        if fixed:
            view.setMinimumHeight(height)
            view.setMaximumHeight(height)
        else:
            view.setMinimumHeight(0)
            view.setMaximumHeight(height)
        return height

    def _connect_signals(self):
        self.search_input.textChanged.connect(self.filter_mods)
        self.case_sensitive_cb.stateChanged.connect(lambda: self.filter_mods(self.search_input.text()))
        self.notes_cb.stateChanged.connect(lambda: self.filter_mods(self.search_input.text()))
        self.description_cb.stateChanged.connect(lambda: self.filter_mods(self.search_input.text()))

        self.mod_list_widget.itemClicked.connect(self._on_mod_selected)
        self.mod_list_widget.itemDoubleClicked.connect(self._on_mod_double_clicked)
        self.recent_list_widget.itemClicked.connect(self._on_recent_selected)
        self.recent_list_widget.itemDoubleClicked.connect(self._on_mod_double_clicked)

    def _load_recent_mods(self):
        self.recent_mods = self.settings.value(f"{self.SETTINGS_KEY}/RecentNotesMods", [], type=list)
        self._update_recent_list()

    def _save_recent_mods(self):
        self.settings.setValue(f"{self.SETTINGS_KEY}/RecentNotesMods", self.recent_mods)
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
        all_mods = list(self.mod_list.allMods())

        def _priority(name: str) -> int:
            try:
                return int(self.mod_list.priority(name))
            except Exception:
                return 0

        all_mods.sort(key=_priority)

        for internal_name in all_mods:
            if self.mod_list.state(internal_name) & mobase.ModState.EXISTS:
                display_name = self.mod_list.displayName(internal_name)
                mod_info = None
                try:
                    mod_info = self._organizer.getMod(internal_name)
                except Exception:
                    mod_info = None

                notes_text = ""
                desc_text = ""
                if mod_info is not None:
                    if hasattr(mod_info, "notes"):
                        try:
                            notes_text = mod_info.notes() or ""
                        except Exception:
                            notes_text = ""
                    if hasattr(mod_info, "comments"):
                        try:
                            desc_text = mod_info.comments() or ""
                        except Exception:
                            desc_text = ""

                item = QListWidgetItem(display_name)
                item.setData(Qt.ItemDataRole.UserRole, internal_name)
                item.setData(Qt.ItemDataRole.UserRole + 1, notes_text)
                item.setData(Qt.ItemDataRole.UserRole + 2, desc_text)
                self.mod_list_widget.addItem(item)

        self._update_results_count()
        self._loaded = True

    def refresh_if_needed(self):
        self.load_mods()

    def filter_mods(self, text: str):
        case_sensitive = self.case_sensitive_cb.isChecked()
        search_text = text if case_sensitive else text.lower()
        use_notes = self.notes_cb.isChecked()
        use_desc = self.description_cb.isChecked()

        visible_count = 0

        for i in range(self.mod_list_widget.count()):
            item = self.mod_list_widget.item(i)
            notes_text = item.data(Qt.ItemDataRole.UserRole + 1) or ""
            desc_text = item.data(Qt.ItemDataRole.UserRole + 2) or ""

            notes_cmp = notes_text if case_sensitive else notes_text.lower()
            desc_cmp = desc_text if case_sensitive else desc_text.lower()

            if search_text:
                matches = (
                    (use_notes and search_text in notes_cmp)
                    or (use_desc and search_text in desc_cmp)
                )
            else:
                matches = (
                    (use_notes and bool(notes_text.strip()))
                    or (use_desc and bool(desc_text.strip()))
                )

            item.setHidden(not matches)
            if matches:
                visible_count += 1

        self._update_results_count(visible_count)

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

        if not self.mods_view or not self.mods_view.model():
            self.mod_selected.emit("Error: Mods view not available")
            return

        model = self.mods_view.model()

        search_names = []
        try:
            search_names.append(self.mod_list.displayName(internal_name))
        except Exception:
            search_names.append(display_name)
        search_names.append(internal_name)

        seen = set()
        unique_names = []
        for name in search_names:
            if name and name not in seen:
                seen.add(name)
                unique_names.append(name)

        matches = None
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

            self.mod_selected.emit(f"Selected: {display_name}")
        else:
            self.mod_selected.emit(f"Could not find: {internal_name}")

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()


__all__ = ["ModNameSearchTab", "PluginSearchTab", "ModNotesSearchTab"]
