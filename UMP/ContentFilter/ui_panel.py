"""UI компоненты: управление фильтром по словам в названии модов."""

from typing import Dict
import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal, QSettings
    from PyQt6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QCheckBox,
        QPushButton,
        QGroupBox,
        QLabel,
        QLineEdit,
        QFrame,
        QRadioButton,
        QButtonGroup,
        QComboBox,
        QInputDialog,
        QTreeView,
    )
    from PyQt6.QtGui import QFont
    PYQT_VERSION = 6
except ImportError:  # pragma: no cover
    from PyQt5.QtCore import Qt, pyqtSignal, QSettings
    from PyQt5.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QCheckBox,
        QPushButton,
        QGroupBox,
        QLabel,
        QLineEdit,
        QFrame,
        QRadioButton,
        QButtonGroup,
        QComboBox,
        QInputDialog,
        QTreeView,
    )
    from PyQt5.QtGui import QFont
    PYQT_VERSION = 5

try:
    import mobase
except ImportError:  # pragma: no cover
    mobase = None

from .filter_proxy import ContentFilterProxy, FilterMode

logger = logging.getLogger("ContentFilter.UI")


class WordItem(QWidget):
    def __init__(self, word: str, initial_mode: str, on_mode_changed, on_remove, parent=None):
        super().__init__(parent)
        self._word = word
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(word)
        layout.addWidget(self._label)

        layout.addStretch()

        self._btn_group = QButtonGroup(self)
        self._rb_show = QRadioButton("Show")
        self._rb_hide = QRadioButton("Hide")
        self._btn_group.addButton(self._rb_show)
        self._btn_group.addButton(self._rb_hide)

        if initial_mode == FilterMode.SHOW_MATCHING:
            self._rb_show.setChecked(True)
        else:
            self._rb_hide.setChecked(True)

        layout.addWidget(self._rb_show)
        layout.addWidget(self._rb_hide)

        self._remove_btn = QPushButton("Remove")
        layout.addWidget(self._remove_btn)

        self._rb_show.toggled.connect(
            lambda checked: checked and on_mode_changed(self._word, FilterMode.SHOW_MATCHING)
        )
        self._rb_hide.toggled.connect(
            lambda checked: checked and on_mode_changed(self._word, FilterMode.HIDE_MATCHING)
        )
        self._remove_btn.clicked.connect(lambda: on_remove(self._word))


class FilterControlPanel(QWidget):
    rescanRequested = pyqtSignal()
    filterToggled = pyqtSignal(bool)

    def __init__(self, filter_proxy: ContentFilterProxy, organizer: "mobase.IOrganizer", parent=None):
        super().__init__(parent)

        self._filter_proxy = filter_proxy
        self._organizer = organizer
        self._items: Dict[str, WordItem] = {}
        self._profiles: Dict[str, Dict[str, str]] = {}
        self._active_profile: str = ""

        self._setup_ui()
        self._connect_signals()
        self._init_settings()
        self._update_status()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        profiles_layout = QHBoxLayout()
        profiles_label = QLabel("Profile:")
        self._profiles_combo = QComboBox()
        self._profile_new_btn = QPushButton("New")
        self._profile_rename_btn = QPushButton("Rename")
        self._profile_delete_btn = QPushButton("Delete")
        self._profiles_combo.setToolTip("Select a word list profile")
        self._profile_new_btn.setToolTip("Create a new word profile")
        self._profile_rename_btn.setToolTip("Rename the current profile")
        self._profile_delete_btn.setToolTip("Delete the current profile (if more than one)")
        self._enable_checkbox = QCheckBox("Enable filter")
        self._enable_checkbox.setFont(self._bold_font())
        self._enable_checkbox.setToolTip("Enable or disable name-based mod filtering")
        profiles_layout.addWidget(profiles_label)
        profiles_layout.addWidget(self._profiles_combo)
        profiles_layout.addWidget(self._profile_new_btn)
        profiles_layout.addWidget(self._profile_rename_btn)
        profiles_layout.addWidget(self._profile_delete_btn)
        profiles_layout.addStretch()
        profiles_layout.addWidget(self._enable_checkbox)
        layout.addLayout(profiles_layout)

        info_label = QLabel(
            "Type words or drag mod to list, to hide mods by name, switch profiles for different lists."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        add_layout = QHBoxLayout()
        self._word_edit = QLineEdit()
        self._word_edit.setPlaceholderText("Word/substring to hide")
        self._word_edit.setToolTip(
            "Type part of a mod name and click Add, or drag a mod from the list"
        )
        self._add_btn = QPushButton("Add")
        self._add_btn.setToolTip("Add the entered word to the hide list")
        add_layout.addWidget(self._word_edit)
        add_layout.addWidget(self._add_btn)
        layout.addLayout(add_layout)

        words_group = QGroupBox("Filter words")
        self._words_layout = QVBoxLayout(words_group)
        self._words_layout.setSpacing(4)
        self._words_layout.addStretch()
        layout.addWidget(words_group)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine if PYQT_VERSION == 6 else QFrame.HLine)
        layout.addWidget(line1)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setToolTip("Shows how many mods are visible after filtering")
        layout.addWidget(self._status_label)

        layout.addStretch()

    def _bold_font(self) -> QFont:
        font = QFont()
        font.setBold(True)
        return font

    def _connect_signals(self) -> None:
        self._enable_checkbox.stateChanged.connect(self._on_enable_changed)
        self._add_btn.clicked.connect(self._on_add_word)
        self._filter_proxy.filterStatsChanged.connect(self._on_stats_changed)
        self._profiles_combo.currentIndexChanged.connect(self._on_profile_changed)
        self._profile_new_btn.clicked.connect(self._on_profile_new)
        self._profile_rename_btn.clicked.connect(self._on_profile_rename)
        self._profile_delete_btn.clicked.connect(self._on_profile_delete)
        self.setAcceptDrops(True)

    def _on_enable_changed(self, state: int) -> None:
        if PYQT_VERSION == 6:
            enabled = state == Qt.CheckState.Checked.value
        else:
            enabled = state == Qt.Checked

        self._filter_proxy.set_filter_enabled(enabled)
        self._word_edit.setEnabled(enabled)
        self._add_btn.setEnabled(enabled)
        for item in self._items.values():
            item.setEnabled(enabled)

        s = QSettings("ContentFilter", "NameFilter")
        s.setValue("filter/enabled", enabled)
        s.sync()

        self._update_status()
        self.filterToggled.emit(enabled)

    def is_enabled(self) -> bool:
        return self._enable_checkbox.isChecked()

    def _on_add_word(self) -> None:
        text = self._word_edit.text().strip()
        if not text:
            return
        key = text.lower()
        if key in self._items:
            self._update_status()
            return

        self._filter_proxy.add_pattern(text, FilterMode.HIDE_MATCHING)
        item = WordItem(text, FilterMode.HIDE_MATCHING, self._on_item_mode_changed, self._on_item_remove)
        self._items[key] = item
        last_item = self._words_layout.takeAt(self._words_layout.count() - 1)
        self._words_layout.addWidget(item)
        if last_item is not None:
            self._words_layout.addItem(last_item)

        self._word_edit.clear()
        self._profile_set_word(text, FilterMode.HIDE_MATCHING)
        self._update_status()

    def _on_item_mode_changed(self, word: str, mode: str) -> None:
        self._filter_proxy.update_pattern_mode(word, mode)
        self._profile_set_word(word, mode)
        self._update_status()

    def _on_item_remove(self, word: str) -> None:
        key = word.strip().lower()
        w = self._items.pop(key, None)
        if w is not None:
            self._words_layout.removeWidget(w)
            w.deleteLater()
        self._filter_proxy.remove_pattern(word)
        self._profile_remove_word(word)
        self._update_status()

    def _on_stats_changed(self, visible: int, total: int) -> None:
        self._current_visible = visible
        self._current_total = total
        self._update_status()

    def _update_status(self) -> None:
        if not self._filter_proxy.is_active:
            self._status_label.setText("Filter is off or the word list is empty")
            return

        visible = getattr(self, "_current_visible", 0)
        total = getattr(self, "_current_total", 0)
        text = f"Showing {visible} of {total} mods"
        if total > 0:
            percent = int((visible / total) * 100)
            text += f" ({percent}%)"
        self._status_label.setText(text)

    def update_counts(self) -> None:
        self._update_status()

    def _init_settings(self) -> None:
        s = QSettings("ContentFilter", "NameFilter")
        names = s.value("profiles/names", [], type=list)
        if not names:
            names = ["Default"]
            s.setValue("profiles/names", names)
            s.setValue("profiles/active", "Default")
            s.setValue("profile/Default", [])
        self._profiles_combo.clear()
        for n in names:
            self._profiles_combo.addItem(n)
        active = s.value("profiles/active", "Default")
        idx = self._profiles_combo.findText(active)
        if idx < 0:
            idx = 0
        self._profiles_combo.setCurrentIndex(idx)
        enabled = s.value("filter/enabled", False, type=bool)
        self._enable_checkbox.setChecked(enabled)
        self._load_profile(self._profiles_combo.currentText())

    def _save_profiles_list(self) -> None:
        s = QSettings("ContentFilter", "NameFilter")
        names = [self._profiles_combo.itemText(i) for i in range(self._profiles_combo.count())]
        s.setValue("profiles/names", names)
        s.setValue("profiles/active", self._active_profile)
        s.setValue("filter/enabled", self._enable_checkbox.isChecked())

    def _load_profile(self, name: str) -> None:
        self._active_profile = name
        s = QSettings("ContentFilter", "NameFilter")
        entries = s.value(f"profile/{name}", [], type=list)
        self._items.clear()
        while self._words_layout.count() > 0:
            item = self._words_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._words_layout.addStretch()
        self._filter_proxy.clear_patterns()
        for rec in entries:
            try:
                word, mode = rec
            except Exception:  # noqa: BLE001
                continue
            key = word.strip().lower()
            if not key:
                continue
            self._filter_proxy.add_pattern(word, mode)
            wi = WordItem(word, mode, self._on_item_mode_changed, self._on_item_remove)
            last_item = self._words_layout.takeAt(self._words_layout.count() - 1)
            self._words_layout.addWidget(wi)
            if last_item is not None:
                self._words_layout.addItem(last_item)
            self._items[key] = wi
        self._update_status()

    def _store_current_profile(self) -> None:
        s = QSettings("ContentFilter", "NameFilter")
        entries = []
        for key, wi in self._items.items():
            _ = key
            _ = wi
        entries = []
        pat = self._filter_proxy.patterns()
        for w, m in pat.items():
            entries.append([w, m])
        s.setValue(f"profile/{self._active_profile}", entries)

    def _profile_set_word(self, word: str, mode: str) -> None:
        s = QSettings("ContentFilter", "NameFilter")
        entries = s.value(f"profile/{self._active_profile}", [], type=list)
        w = word.strip().lower()
        found = False
        for rec in entries:
            if rec and rec[0].lower() == w:
                rec[1] = mode
                found = True
                break
        if not found:
            entries.append([word, mode])
        s.setValue(f"profile/{self._active_profile}", entries)

    def _profile_remove_word(self, word: str) -> None:
        s = QSettings("ContentFilter", "NameFilter")
        entries = s.value(f"profile/{self._active_profile}", [], type=list)
        w = word.strip().lower()
        entries = [rec for rec in entries if rec and rec[0].strip().lower() != w]
        s.setValue(f"profile/{self._active_profile}", entries)

    def _on_profile_changed(self) -> None:
        name = self._profiles_combo.currentText()
        self._active_profile = name
        self._save_profiles_list()
        self._load_profile(name)

    def _on_profile_new(self) -> None:
        name, ok = QInputDialog.getText(self, "New profile", "Profile name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if self._profiles_combo.findText(name) >= 0:
            self._profiles_combo.setCurrentText(name)
            return
        self._profiles_combo.addItem(name)
        self._profiles_combo.setCurrentText(name)
        s = QSettings("ContentFilter", "NameFilter")
        s.setValue(f"profile/{name}", [])
        self._save_profiles_list()

    def _on_profile_rename(self) -> None:
        old = self._profiles_combo.currentText()
        name, ok = QInputDialog.getText(self, "Rename profile", "New name:", text=old)
        if not ok:
            return
        name = name.strip()
        if not name or name == old:
            return
        if self._profiles_combo.findText(name) >= 0:
            self._profiles_combo.setCurrentText(name)
            return
        s = QSettings("ContentFilter", "NameFilter")
        entries = s.value(f"profile/{old}", [], type=list)
        s.remove(f"profile/{old}")
        s.setValue(f"profile/{name}", entries)
        idx = self._profiles_combo.findText(old)
        self._profiles_combo.setItemText(idx, name)
        self._profiles_combo.setCurrentText(name)
        self._save_profiles_list()

    def _on_profile_delete(self) -> None:
        if self._profiles_combo.count() <= 1:
            return
        name = self._profiles_combo.currentText()
        s = QSettings("ContentFilter", "NameFilter")
        s.remove(f"profile/{name}")
        idx = self._profiles_combo.currentIndex()
        self._profiles_combo.removeItem(idx)
        self._save_profiles_list()
        self._load_profile(self._profiles_combo.currentText())

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        src = event.source()
        if isinstance(src, QTreeView) or mime.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        src = event.source()
        handled = False
        if isinstance(src, QTreeView):
            indexes = src.selectedIndexes()
            seen = set()
            for idx in indexes:
                if idx.column() != 0:
                    continue
                name = str(idx.data() or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen or key in self._items:
                    continue
                seen.add(key)
                self._filter_proxy.add_pattern(name, FilterMode.HIDE_MATCHING)
                item = WordItem(
                    name,
                    FilterMode.HIDE_MATCHING,
                    self._on_item_mode_changed,
                    self._on_item_remove,
                )
                self._items[key] = item
                last_item = self._words_layout.takeAt(self._words_layout.count() - 1)
                self._words_layout.addWidget(item)
                if last_item is not None:
                    self._words_layout.addItem(last_item)
                self._profile_set_word(name, FilterMode.HIDE_MATCHING)
            if seen:
                handled = True

        if not handled:
            mime = event.mimeData()
            if mime.hasText():
                text = mime.text()
                for line in text.splitlines():
                    w = line.strip()
                    if not w:
                        continue
                    key = w.lower()
                    if key in self._items:
                        continue
                    self._filter_proxy.add_pattern(w, FilterMode.HIDE_MATCHING)
                    item = WordItem(
                        w,
                        FilterMode.HIDE_MATCHING,
                        self._on_item_mode_changed,
                        self._on_item_remove,
                    )
                    self._items[key] = item
                    last_item = self._words_layout.takeAt(self._words_layout.count() - 1)
                    self._words_layout.addWidget(item)
                    if last_item is not None:
                        self._words_layout.addItem(last_item)
                    self._profile_set_word(w, FilterMode.HIDE_MATCHING)
                handled = True

        if handled:
            self._update_status()
            event.acceptProposedAction()
        else:
            event.ignore()
