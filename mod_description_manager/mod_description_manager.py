import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import mobase

try:
    from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QRect, QUrl, pyqtSignal
    from PyQt6.QtGui import QDesktopServices, QIcon, QPalette
    from PyQt6.QtWidgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QScrollArea,
        QLabel,
        QLineEdit,
        QTextEdit,
        QPushButton,
        QComboBox,
        QInputDialog,
        QMessageBox,
        QDialog,
        QListWidget,
        QListWidgetItem,
        QTabWidget,
        QMainWindow,
        QCheckBox,
        QLayout,
        QDialogButtonBox,
        QSpinBox,
        QFileDialog,
    )
    PYQT_VERSION = 6
except Exception:
    from PyQt5.QtCore import Qt, QTimer, QSize, QPoint, QRect, QUrl, pyqtSignal
    from PyQt5.QtGui import QDesktopServices, QIcon, QPalette
    from PyQt5.QtWidgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QScrollArea,
        QLabel,
        QLineEdit,
        QTextEdit,
        QPushButton,
        QComboBox,
        QInputDialog,
        QMessageBox,
        QDialog,
        QListWidget,
        QListWidgetItem,
        QTabWidget,
        QMainWindow,
        QCheckBox,
        QLayout,
        QDialogButtonBox,
        QSpinBox,
        QFileDialog,
    )
    PYQT_VERSION = 5

if PYQT_VERSION == 6:
    ROLE_DISPLAY = Qt.ItemDataRole.DisplayRole
    ROLE_USER = Qt.ItemDataRole.UserRole
    PAL_BUTTON = QPalette.ColorRole.Button
    PAL_BUTTON_TEXT = QPalette.ColorRole.ButtonText
    PAL_HIGHLIGHT = QPalette.ColorRole.Highlight
    PAL_HIGHLIGHT_TEXT = QPalette.ColorRole.HighlightedText
else:
    ROLE_DISPLAY = Qt.DisplayRole
    ROLE_USER = Qt.UserRole
    PAL_BUTTON = QPalette.Button
    PAL_BUTTON_TEXT = QPalette.ButtonText
    PAL_HIGHLIGHT = QPalette.Highlight
    PAL_HIGHLIGHT_TEXT = QPalette.HighlightedText


def _log(message: str) -> None:
    print(f"[ModDesc] {message}", flush=True)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_path(value) -> Optional[Path]:
    if value is None:
        return None
    if hasattr(value, "absolutePath"):
        try:
            value = value.absolutePath()
        except Exception:
            pass
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value:
        return Path(value)
    return None


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass
class ModDescription:
    short: str = ""
    detailed: str = ""
    tags: List[str] = field(default_factory=list)
    color_label: str = ""
    user_rating: int = 0
    notes: str = ""
    url: str = ""
    compatibility: str = ""
    last_edited: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "short": self.short,
            "detailed": self.detailed,
            "tags": list(self.tags),
            "color_label": self.color_label,
            "user_rating": int(self.user_rating or 0),
            "notes": self.notes,
            "url": self.url,
            "compatibility": self.compatibility,
            "last_edited": self.last_edited,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ModDescription":
        return ModDescription(
            short=str(data.get("short", "")),
            detailed=str(data.get("detailed", "")),
            tags=list(data.get("tags", []) or []),
            color_label=str(data.get("color_label", "")),
            user_rating=int(data.get("user_rating", 0) or 0),
            notes=str(data.get("notes", "")),
            url=str(data.get("url", "")),
            compatibility=str(data.get("compatibility", "")),
            last_edited=str(data.get("last_edited", "")),
        )


class DescriptionFileManager:
    def __init__(self, organizer: mobase.IOrganizer, settings: "SettingsManager") -> None:
        self._organizer = organizer
        self._settings = settings

    def _mods_path(self) -> Optional[Path]:
        return _to_path(self._organizer.modsPath())

    def _mod_dir(self, mod_name: str) -> Optional[Path]:
        base = self._mods_path()
        if base is None:
            return None
        mod_dir = base / mod_name
        if mod_dir.exists():
            return mod_dir
        return None

    def _desc_file(self, mod_name: str) -> Optional[Path]:
        mod_dir = self._mod_dir(mod_name)
        if mod_dir is None:
            return None
        filename = self._settings.data.get("description_filename", "_mod_description.json")
        return mod_dir / filename

    def load(self, mod_name: str) -> Dict[str, Any]:
        desc_file = self._desc_file(mod_name)
        if desc_file is None:
            return {}
        if not desc_file.exists():
            return {}
        try:
            with desc_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            _log(f"Failed to read description file for {mod_name}: {exc}")
            return {}

    def save(self, mod_name: str, data: Dict[str, Any]) -> bool:
        desc_file = self._desc_file(mod_name)
        if desc_file is None:
            return False
        try:
            _ensure_dir(desc_file.parent)
            if self._settings.data.get("backup_on_save", True) and desc_file.exists():
                try:
                    backup_path = desc_file.with_suffix(desc_file.suffix + ".bak")
                    if backup_path.exists():
                        backup_path.unlink()
                    backup_path.write_bytes(desc_file.read_bytes())
                except Exception as exc:
                    _log(f"Backup failed: {exc}")
            with desc_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            _log(f"Failed to save description file for {mod_name}: {exc}")
            return False

    def delete_profile(self, mod_name: str, profile_id: str) -> bool:
        data = self.load(mod_name)
        if not data:
            return False
        profiles = data.get("profiles", {})
        if profile_id in profiles:
            profiles.pop(profile_id, None)
            data["profiles"] = profiles
            return self.save(mod_name, data)
        return False


class ProfileManager:
    def __init__(self, settings_dir: Path) -> None:
        self._settings_dir = settings_dir
        self._profiles_path = settings_dir / "_profiles.json"
        self.data = {}
        self._load()

    def _default(self) -> Dict[str, Any]:
        return {
            "profiles": [
                {
                    "id": "_global",
                    "name": "Global Notes",
                    "created": _now_iso(),
                    "is_default": True,
                    "deletable": False,
                }
            ],
            "max_profiles": 10,
        }

    def _load(self) -> None:
        _ensure_dir(self._settings_dir)
        if not self._profiles_path.exists():
            self.data = self._default()
            self.save()
            return
        try:
            with self._profiles_path.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception as exc:
            _log(f"Failed to read profiles: {exc}")
            self.data = self._default()
            self.save()

    def save(self) -> None:
        try:
            _ensure_dir(self._settings_dir)
            with self._profiles_path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            _log(f"Failed to save profiles: {exc}")

    def profiles(self) -> List[Dict[str, Any]]:
        return list(self.data.get("profiles", []))

    def max_profiles(self) -> int:
        return int(self.data.get("max_profiles", 10) or 10)

    def add_profile(self, name: str) -> Optional[Dict[str, Any]]:
        if len(self.profiles()) >= self.max_profiles():
            return None
        pid = name.strip().replace(" ", "_")
        if not pid:
            return None
        if any(p.get("id") == pid for p in self.profiles()):
            return None
        rec = {
            "id": pid,
            "name": name.strip(),
            "created": _now_iso(),
            "is_default": False,
            "deletable": True,
        }
        self.data.setdefault("profiles", []).append(rec)
        self.save()
        return rec

    def rename_profile(self, pid: str, new_name: str) -> bool:
        for p in self.profiles():
            if p.get("id") == pid:
                if not p.get("deletable", True):
                    return False
                p["name"] = new_name.strip()
                self.save()
                return True
        return False

    def delete_profile(self, pid: str) -> bool:
        profiles = self.profiles()
        for p in profiles:
            if p.get("id") == pid:
                if not p.get("deletable", True):
                    return False
                profiles.remove(p)
                self.data["profiles"] = profiles
                self.save()
                return True
        return False


class SettingsManager:
    def __init__(self, settings_dir: Path) -> None:
        self._settings_dir = settings_dir
        self._settings_path = settings_dir / "_settings.json"
        self.data = {}
        self._load()

    def _default(self) -> Dict[str, Any]:
        return {
            "active_profile_id": "_global",
            "auto_save": True,
            "show_on_select": True,
            "font_size": 0,
            "compact_mode": False,
            "backup_on_save": True,
            "backup_count": 1,
            "last_selected_mod": "",
            "description_filename": "_mod_description.json",
            "details_open": True,
        }

    def _load(self) -> None:
        _ensure_dir(self._settings_dir)
        if not self._settings_path.exists():
            self.data = self._default()
            self.save()
            return
        try:
            with self._settings_path.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception as exc:
            _log(f"Failed to read settings: {exc}")
            self.data = self._default()
            self.save()

    def save(self) -> None:
        try:
            _ensure_dir(self._settings_dir)
            with self._settings_path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            _log(f"Failed to save settings: {exc}")


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items: List[Any] = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(+left, +top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is None or not widget.isVisible():
                continue
            space_x = self._hspacing
            space_y = self._vspacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + bottom


class TagsWidget(QWidget):
    tagsChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: List[str] = []
        self._layout = FlowLayout(self, margin=0, hspacing=6, vspacing=6)
        self.setLayout(self._layout)

    def _tag_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setCheckable(False)
        pal = btn.palette()
        pal.setColor(PAL_BUTTON, pal.color(PAL_HIGHLIGHT))
        pal.setColor(PAL_BUTTON_TEXT, pal.color(PAL_HIGHLIGHT_TEXT))
        btn.setPalette(pal)
        btn.clicked.connect(lambda: self._remove_tag(text))
        return btn

    def set_tags(self, tags: List[str]) -> None:
        self._tags = list(dict.fromkeys([t for t in tags if t]))
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for t in self._tags:
            self._layout.addWidget(self._tag_button(t))

    def add_tag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag or tag in self._tags:
            return
        self._tags.append(tag)
        self._layout.addWidget(self._tag_button(tag))
        self.tagsChanged.emit(self._tags)

    def _remove_tag(self, tag: str) -> None:
        ans = QMessageBox.question(self, "Remove tag", f"Remove tag '{tag}'?")
        if ans != QMessageBox.StandardButton.Yes:
            return
        if tag in self._tags:
            self._tags.remove(tag)
        self.set_tags(self._tags)
        self.tagsChanged.emit(self._tags)

    def tags(self) -> List[str]:
        return list(self._tags)


class StarRatingWidget(QWidget):
    ratingChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._buttons: List[QPushButton] = []
        for i in range(5):
            btn = QPushButton("☆")
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, x=i + 1: self.set_rating(x))
            self._buttons.append(btn)
            layout.addWidget(btn)
        layout.addStretch(1)
        self.setLayout(layout)
        self._update()

    def set_rating(self, value: int, emit: bool = True) -> None:
        value = int(value)
        if value == self._rating:
            self._rating = 0
        else:
            self._rating = max(0, min(5, value))
        self._update()
        if emit:
            self.ratingChanged.emit(self._rating)

    def rating(self) -> int:
        return self._rating

    def _update(self) -> None:
        for i, btn in enumerate(self._buttons, start=1):
            btn.setText("★" if i <= self._rating else "☆")


class ModSearchDialog(QDialog):
    modSelected = pyqtSignal(str)

    def __init__(self, organizer: mobase.IOrganizer, desc_manager: DescriptionFileManager, profile_id: str, parent=None):
        super().__init__(parent)
        self._organizer = organizer
        self._desc_manager = desc_manager
        self._profile_id = profile_id
        self._cache: List[Dict[str, Any]] = []
        self._cache_ready = False

        self.setWindowTitle("Search Descriptions")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter...")
        self._filter.textChanged.connect(self._apply_filter)
        row.addWidget(self._filter, 1)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._rebuild_cache)
        row.addWidget(self._refresh_btn)
        layout.addLayout(row)

        self._list = QListWidget()
        layout.addWidget(self._list, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._list.itemDoubleClicked.connect(self._on_item)
        self._rebuild_cache()

    def _mods_path(self) -> Optional[Path]:
        return _to_path(self._organizer.modsPath())

    def _rebuild_cache(self) -> None:
        self._cache = []
        mods_path = self._mods_path()
        if mods_path is None:
            return
        for mod_dir in mods_path.iterdir():
            if not mod_dir.is_dir():
                continue
            mod_name = mod_dir.name
            data = self._desc_manager.load(mod_name)
            profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
            entry = profiles.get(self._profile_id, {}) if isinstance(profiles, dict) else {}
            short = str(entry.get("short", ""))
            detailed = str(entry.get("detailed", ""))
            tags = entry.get("tags", [])
            tags_txt = " ".join(tags) if isinstance(tags, list) else ""
            if short or detailed or tags_txt:
                self._cache.append({
                    "mod": mod_name,
                    "short": short,
                    "tags": tags_txt,
                })
        self._cache_ready = True
        self._apply_filter(self._filter.text())

    def _apply_filter(self, text: str) -> None:
        self._list.clear()
        text = (text or "").strip().lower()
        for rec in self._cache:
            mod = rec["mod"]
            short = rec.get("short", "")
            tags = rec.get("tags", "")
            blob = f"{mod} {short} {tags}".lower()
            if text and text not in blob:
                continue
            item = QListWidgetItem(f"{mod} — {short}" if short else mod)
            item.setData(ROLE_USER, mod)
            self._list.addItem(item)

    def _on_item(self, item: QListWidgetItem) -> None:
        mod = item.data(ROLE_USER)
        if isinstance(mod, str) and mod:
            self.modSelected.emit(mod)
            self.accept()


class SettingsDialog(QDialog):
    def __init__(self, settings: SettingsManager, organizer: mobase.IOrganizer, desc_manager: DescriptionFileManager, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._organizer = organizer
        self._desc_manager = desc_manager
        self.setWindowTitle("Description Settings")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Font size"))
        self._font_size = QSpinBox()
        self._font_size.setRange(0, 24)
        self._font_size.setValue(int(self._settings.data.get("font_size", 0) or 0))
        font_row.addWidget(self._font_size)
        layout.addLayout(font_row)

        self._compact = QCheckBox("Compact mode")
        self._compact.setChecked(bool(self._settings.data.get("compact_mode", False)))
        layout.addWidget(self._compact)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Description file"))
        self._filename = QLineEdit(self._settings.data.get("description_filename", "_mod_description.json"))
        file_row.addWidget(self._filename)
        layout.addLayout(file_row)

        self._backup = QCheckBox("Backup on save")
        self._backup.setChecked(bool(self._settings.data.get("backup_on_save", True)))
        layout.addWidget(self._backup)

        export_btn = QPushButton("Export all descriptions")
        import_btn = QPushButton("Import descriptions")
        layout.addWidget(export_btn)
        layout.addWidget(import_btn)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        export_btn.clicked.connect(self._export)
        import_btn.clicked.connect(self._import)

    def apply(self) -> None:
        self._settings.data["font_size"] = int(self._font_size.value())
        self._settings.data["compact_mode"] = bool(self._compact.isChecked())
        self._settings.data["description_filename"] = self._filename.text().strip() or "_mod_description.json"
        self._settings.data["backup_on_save"] = bool(self._backup.isChecked())
        self._settings.save()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", "JSON Files (*.json)")
        if not path:
            return
        mods_path = _to_path(self._organizer.modsPath())
        if mods_path is None:
            QMessageBox.warning(self, "Export", "Mods path not found")
            return
        payload = {"_version": 1, "mods": {}}
        for mod_dir in mods_path.iterdir():
            if not mod_dir.is_dir():
                continue
            mod_name = mod_dir.name
            data = self._desc_manager.load(mod_name)
            if data:
                payload["mods"][mod_name] = data
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export", "Export complete")
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"Export failed: {exc}")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON Files (*.json)")
        if not path:
            return
        mods_path = _to_path(self._organizer.modsPath())
        if mods_path is None:
            QMessageBox.warning(self, "Import", "Mods path not found")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            QMessageBox.warning(self, "Import", f"Invalid file: {exc}")
            return
        mods = data.get("mods") if isinstance(data, dict) else None
        if not isinstance(mods, dict):
            mods = data if isinstance(data, dict) else {}
        total = 0
        saved = 0
        for mod_name, mod_data in mods.items():
            total += 1
            if not isinstance(mod_name, str):
                continue
            mod_dir = mods_path / mod_name
            if not mod_dir.exists():
                continue
            if isinstance(mod_data, dict):
                if self._desc_manager.save(mod_name, mod_data):
                    saved += 1
        QMessageBox.information(self, "Import", f"Imported {saved}/{total} mods")


class ModDescriptionWidget(QWidget):
    def __init__(self, organizer: mobase.IOrganizer, settings_dir: Path, parent=None):
        super().__init__(parent)
        self._organizer = organizer
        self._settings = SettingsManager(settings_dir)
        self._profiles = ProfileManager(settings_dir)
        self._desc_manager = DescriptionFileManager(organizer, self._settings)
        self._current_mod = ""
        self._dirty = False
        self._loading = False
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._mod_view = None

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll_mod_selection)
        self._timer.start()

        self._build_ui()
        self._load_profiles()
        self._apply_settings()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile:"))
        self._profile_combo = QComboBox()
        profile_row.addWidget(self._profile_combo, 1)
        self._profile_add = QPushButton("+")
        self._profile_rename = QPushButton("✏")
        self._profile_del = QPushButton("🗑")
        self._settings_btn = QPushButton("⚙")
        profile_row.addWidget(self._profile_add)
        profile_row.addWidget(self._profile_rename)
        profile_row.addWidget(self._profile_del)
        profile_row.addWidget(self._settings_btn)
        layout.addLayout(profile_row)

        mod_row = QHBoxLayout()
        self._mod_label = QLabel("No mod selected")
        mod_row.addWidget(self._mod_label, 1)
        self._search_btn = QPushButton("🔍")
        mod_row.addWidget(self._search_btn)
        layout.addLayout(mod_row)

        short_row = QHBoxLayout()
        short_row.addWidget(QLabel("Short:"))
        self._short_edit = QLineEdit()
        short_row.addWidget(self._short_edit, 1)
        layout.addLayout(short_row)

        layout.addWidget(QLabel("Description:"))
        self._detail_edit = QTextEdit()
        layout.addWidget(self._detail_edit)

        tags_row = QHBoxLayout()
        tags_row.addWidget(QLabel("Tags:"))
        self._tags_widget = TagsWidget()
        tags_row.addWidget(self._tags_widget, 1)
        self._tag_add = QPushButton("+ Add")
        tags_row.addWidget(self._tag_add)

        rating_row = QHBoxLayout()
        rating_row.addWidget(QLabel("Rating:"))
        self._rating = StarRatingWidget()
        rating_row.addWidget(self._rating, 1)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(24, 24)
        color_row.addWidget(self._color_btn)
        color_row.addStretch(1)

        self._details_toggle = QPushButton("Details ▼")
        layout.addWidget(self._details_toggle)

        self._details_container = QWidget()
        details_layout = QVBoxLayout(self._details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(4)

        compat_row = QHBoxLayout()
        compat_row.addWidget(QLabel("Compatibility:"))
        self._compat_edit = QLineEdit()
        compat_row.addWidget(self._compat_edit, 1)
        details_layout.addLayout(compat_row)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("URL:"))
        self._url_edit = QLineEdit()
        url_row.addWidget(self._url_edit, 1)
        self._url_open = QPushButton("🔗")
        url_row.addWidget(self._url_open)
        details_layout.addLayout(url_row)

        details_layout.addWidget(QLabel("Notes:"))
        self._notes_edit = QTextEdit()
        details_layout.addWidget(self._notes_edit)

        details_layout.addLayout(tags_row)
        details_layout.addLayout(rating_row)
        details_layout.addLayout(color_row)

        layout.addWidget(self._details_container)

        action_row = QHBoxLayout()
        self._save_btn = QPushButton("💾 Save")
        self._revert_btn = QPushButton("↩ Revert")
        self._port_btn = QPushButton("⇄ Port")
        self._import_btn = QPushButton("⬇ MO2")
        self._delete_btn = QPushButton("🗑 Del")
        self._autosave = QCheckBox("Auto-save")
        action_row.addWidget(self._save_btn)
        action_row.addWidget(self._revert_btn)
        action_row.addWidget(self._port_btn)
        action_row.addWidget(self._import_btn)
        action_row.addWidget(self._delete_btn)
        action_row.addStretch(1)
        action_row.addWidget(self._autosave)
        layout.addLayout(action_row)

        self._status = QLabel("Ready")
        layout.addWidget(self._status)

        self._connect_signals()

    def _connect_signals(self) -> None:
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self._profile_add.clicked.connect(self._on_profile_add)
        self._profile_rename.clicked.connect(self._on_profile_rename)
        self._profile_del.clicked.connect(self._on_profile_delete)
        self._settings_btn.clicked.connect(self._on_settings)
        self._search_btn.clicked.connect(self._on_search)
        self._short_edit.textChanged.connect(self._mark_dirty)
        self._detail_edit.textChanged.connect(self._mark_dirty)
        self._compat_edit.textChanged.connect(self._mark_dirty)
        self._notes_edit.textChanged.connect(self._mark_dirty)
        self._url_edit.textChanged.connect(self._mark_dirty)
        self._tags_widget.tagsChanged.connect(lambda _: self._mark_dirty())
        self._tag_add.clicked.connect(self._on_add_tag)
        self._rating.ratingChanged.connect(lambda _: self._mark_dirty())
        self._color_btn.clicked.connect(self._on_color)
        self._url_open.clicked.connect(self._on_open_url)
        self._save_btn.clicked.connect(self._save_current)
        self._revert_btn.clicked.connect(self._revert_current)
        self._port_btn.clicked.connect(self._on_port_notes_desc)
        self._import_btn.clicked.connect(self._on_import_from_mo2)
        self._delete_btn.clicked.connect(self._delete_current)
        self._autosave.stateChanged.connect(self._on_autosave_changed)
        self._details_toggle.clicked.connect(self._toggle_details)

    def _apply_settings(self) -> None:
        self._autosave.setChecked(bool(self._settings.data.get("auto_save", True)))
        open_state = bool(self._settings.data.get("details_open", True))
        self._details_container.setVisible(open_state)
        self._details_toggle.setText("Details ▼" if open_state else "Details ▶")
        compact = bool(self._settings.data.get("compact_mode", False))
        self._details_container.setVisible(open_state and not compact)
        self._details_toggle.setVisible(not compact)
        font_size = int(self._settings.data.get("font_size", 0) or 0)
        if font_size > 0:
            for w in [self._short_edit, self._detail_edit, self._compat_edit, self._notes_edit, self._url_edit]:
                f = w.font()
                f.setPointSize(font_size)
                w.setFont(f)

    def _load_profiles(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for p in self._profiles.profiles():
            self._profile_combo.addItem(p.get("name", p.get("id", "")), p.get("id"))
        active = self._settings.data.get("active_profile_id", "_global")
        idx = self._profile_combo.findData(active)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.blockSignals(False)

    def _current_profile_id(self) -> str:
        return str(self._profile_combo.currentData() or "_global")

    def _on_profile_changed(self) -> None:
        if self._dirty and self._autosave.isChecked():
            self._save_current()
        self._settings.data["active_profile_id"] = self._current_profile_id()
        self._settings.save()
        self._load_current()

    def _on_profile_add(self) -> None:
        name, ok = QInputDialog.getText(self, "New profile", "Profile name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if self._profiles.add_profile(name) is None:
            QMessageBox.warning(self, "Profile", "Cannot add profile")
            return
        self._load_profiles()

    def _on_profile_rename(self) -> None:
        pid = self._current_profile_id()
        if pid == "_global":
            QMessageBox.warning(self, "Profile", "Global profile cannot be renamed")
            return
        name, ok = QInputDialog.getText(self, "Rename profile", "New name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if not self._profiles.rename_profile(pid, name):
            QMessageBox.warning(self, "Profile", "Cannot rename profile")
            return
        self._load_profiles()

    def _on_profile_delete(self) -> None:
        pid = self._current_profile_id()
        if pid == "_global":
            QMessageBox.warning(self, "Profile", "Global profile cannot be deleted")
            return
        ans = QMessageBox.question(self, "Delete profile", "Descriptions in mod folders will remain. Continue?")
        if ans != QMessageBox.StandardButton.Yes:
            return
        if not self._profiles.delete_profile(pid):
            QMessageBox.warning(self, "Profile", "Cannot delete profile")
            return
        self._load_profiles()

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self._organizer, self._desc_manager, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply()
            self._apply_settings()
            self._load_current()

    def _on_search(self) -> None:
        dlg = ModSearchDialog(self._organizer, self._desc_manager, self._current_profile_id(), self)
        dlg.modSelected.connect(self._set_mod)
        dlg.exec()

    def _on_add_tag(self) -> None:
        tag, ok = QInputDialog.getText(self, "Add tag", "Tag:")
        if not ok:
            return
        self._tags_widget.add_tag(tag)

    def _on_port_notes_desc(self) -> None:
        if not self._current_mod:
            QMessageBox.warning(self, "Port", "No mod selected")
            return
        profiles = self._profiles.profiles()
        current_pid = self._current_profile_id()
        targets = [p for p in profiles if p.get("id") != current_pid]
        if not targets:
            QMessageBox.information(self, "Port", "No target profiles available")
            return
        items = []
        mapping = {}
        for p in targets:
            pid = str(p.get("id", "")).strip()
            name = str(p.get("name", "")).strip() or pid
            if not pid:
                continue
            label = f"{name} ({pid})" if name != pid else pid
            items.append(label)
            mapping[label] = pid
        if not items:
            QMessageBox.information(self, "Port", "No target profiles available")
            return
        choice, ok = QInputDialog.getItem(self, "Port", "Target profile:", items, 0, False)
        if not ok or not choice:
            return
        target_pid = mapping.get(choice)
        if not target_pid:
            return
        data = self._desc_manager.load(self._current_mod)
        if not isinstance(data, dict):
            data = {}
        profiles_map = data.get("profiles", {})
        if not isinstance(profiles_map, dict):
            profiles_map = {}
        entry = profiles_map.get(target_pid, {})
        if not isinstance(entry, dict):
            entry = {}
        current_desc = self._current_desc()
        entry["detailed"] = current_desc.detailed
        entry["notes"] = current_desc.notes
        entry["last_edited"] = _now_iso()
        profiles_map[target_pid] = entry
        data["profiles"] = profiles_map
        if self._desc_manager.save(self._current_mod, data):
            self._status.setText(f"Ported to {target_pid}")
        else:
            self._status.setText("Port failed")

    def _on_import_from_mo2(self) -> None:
        if not self._current_mod:
            QMessageBox.warning(self, "Import", "No mod selected")
            return
        mod = None
        try:
            mod = self._organizer.getMod(self._current_mod)
        except Exception:
            mod = None
        if not mod:
            QMessageBox.warning(self, "Import", "Cannot access mod info")
            return
        mo2_comments = ""
        mo2_notes = ""
        if hasattr(mod, "comments"):
            try:
                mo2_comments = mod.comments() or ""
            except Exception:
                mo2_comments = ""
        if hasattr(mod, "notes"):
            try:
                mo2_notes = mod.notes() or ""
            except Exception:
                mo2_notes = ""
        if not mo2_comments and not mo2_notes:
            QMessageBox.information(self, "Import", "MO2 notes and descriptions are empty")
            return
        profiles = self._profiles.profiles()
        items = []
        mapping = {}
        for p in profiles:
            pid = str(p.get("id", "")).strip()
            name = str(p.get("name", "")).strip() or pid
            if not pid:
                continue
            label = f"{name} ({pid})" if name != pid else pid
            items.append(label)
            mapping[label] = pid
        if not items:
            QMessageBox.information(self, "Import", "No target profiles available")
            return
        choice, ok = QInputDialog.getItem(self, "Import", "Target profile:", items, 0, False)
        if not ok or not choice:
            return
        target_pid = mapping.get(choice)
        if not target_pid:
            return
        data = self._desc_manager.load(self._current_mod)
        if not isinstance(data, dict):
            data = {}
        profiles_map = data.get("profiles", {})
        if not isinstance(profiles_map, dict):
            profiles_map = {}
        entry = profiles_map.get(target_pid, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["detailed"] = mo2_notes
        entry["notes"] = mo2_comments
        entry["last_edited"] = _now_iso()
        profiles_map[target_pid] = entry
        data["profiles"] = profiles_map
        if self._desc_manager.save(self._current_mod, data):
            self._status.setText(f"Imported from MO2 to {target_pid}")
            if target_pid == self._current_profile_id():
                self._load_current()
        else:
            self._status.setText("Import failed")

    def _on_open_url(self) -> None:
        url = self._url_edit.text().strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _on_color(self) -> None:
        try:
            from PyQt6.QtWidgets import QColorDialog
        except Exception:
            from PyQt5.QtWidgets import QColorDialog
        color = QColorDialog.getColor()
        if not color.isValid():
            return
        hex_color = color.name()
        self._color_btn.setStyleSheet(f"background-color: {hex_color};")
        self._color_btn.setProperty("color_value", hex_color)
        self._mark_dirty()

    def _toggle_details(self) -> None:
        if bool(self._settings.data.get("compact_mode", False)):
            return
        visible = not self._details_container.isVisible()
        self._details_container.setVisible(visible)
        self._details_toggle.setText("Details ▼" if visible else "Details ▶")
        self._settings.data["details_open"] = visible
        self._settings.save()

    def _on_autosave_changed(self) -> None:
        self._settings.data["auto_save"] = self._autosave.isChecked()
        self._settings.save()

    def _mark_dirty(self) -> None:
        if self._loading:
            return
        if not self._dirty:
            self._dirty = True
            font = self._mod_label.font()
            font.setBold(True)
            self._mod_label.setFont(font)

    def _clear_dirty(self) -> None:
        self._dirty = False
        font = self._mod_label.font()
        font.setBold(False)
        self._mod_label.setFont(font)

    def _current_desc(self) -> ModDescription:
        return ModDescription(
            short=self._short_edit.text().strip(),
            detailed=self._detail_edit.toPlainText().strip(),
            tags=self._tags_widget.tags(),
            color_label=self._color_btn.property("color_value") or "",
            user_rating=self._rating.rating(),
            notes=self._notes_edit.toPlainText().strip(),
            url=self._url_edit.text().strip(),
            compatibility=self._compat_edit.text().strip(),
            last_edited=_now_iso(),
        )

    def _load_current(self) -> None:
        if not self._current_mod:
            return
        data = self._desc_manager.load(self._current_mod)
        self._cache[self._current_mod] = data
        profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        entry = profiles.get(self._current_profile_id(), {}) if isinstance(profiles, dict) else {}
        desc = ModDescription.from_dict(entry if isinstance(entry, dict) else {})
        self._apply_desc(desc)
        self._clear_dirty()
        self._update_status_counts("Ready")

    def _apply_desc(self, desc: ModDescription) -> None:
        self._loading = True
        self._short_edit.setText(desc.short)
        self._detail_edit.setText(desc.detailed)
        self._tags_widget.set_tags(desc.tags)
        self._compat_edit.setText(desc.compatibility)
        self._notes_edit.setText(desc.notes)
        self._url_edit.setText(desc.url)
        self._rating.set_rating(desc.user_rating, emit=False)
        color = desc.color_label
        if color:
            self._color_btn.setStyleSheet(f"background-color: {color};")
            self._color_btn.setProperty("color_value", color)
        else:
            self._color_btn.setStyleSheet("")
            self._color_btn.setProperty("color_value", "")
        self._loading = False

    def _save_current(self) -> None:
        if not self._current_mod:
            return
        data = self._desc_manager.load(self._current_mod)
        if not isinstance(data, dict):
            data = {}
        data.setdefault("_version", 1)
        data.setdefault("_mod_name", self._current_mod)
        profiles = data.get("profiles", {}) if isinstance(data.get("profiles"), dict) else {}
        desc = self._current_desc().to_dict()
        profiles[self._current_profile_id()] = desc
        data["profiles"] = profiles
        if self._desc_manager.save(self._current_mod, data):
            self._update_status_counts("Saved")
            self._clear_dirty()
        else:
            self._status.setText("Save failed")

    def _revert_current(self) -> None:
        self._load_current()
        self._update_status_counts("Reverted")

    def _delete_current(self) -> None:
        if not self._current_mod:
            return
        ans = QMessageBox.question(self, "Delete", "Delete description for current profile?")
        if ans != QMessageBox.StandardButton.Yes:
            return
        if self._desc_manager.delete_profile(self._current_mod, self._current_profile_id()):
            self._update_status_counts("Deleted")
            self._load_current()
        else:
            self._status.setText("Delete failed")

    def _find_mod_list_view(self) -> Optional[QWidget]:
        for w in QApplication.allWidgets():
            if isinstance(w, QWidget) and w.objectName() == "modList":
                return w
        return None

    def _poll_mod_selection(self) -> None:
        if self._mod_view is None or not self._mod_view.isVisible():
            self._mod_view = self._find_mod_list_view()
        if self._mod_view is None:
            return
        model = self._mod_view.model()
        if model is None:
            return
        sel = self._mod_view.selectionModel()
        if sel is None:
            return
        indexes = sel.selectedRows(0)
        if not indexes:
            return
        idx = indexes[0]
        name = idx.data(ROLE_DISPLAY)
        if not isinstance(name, str) or not name.strip():
            return
        name = name.strip()
        if name == self._current_mod:
            return
        if self._dirty and self._autosave.isChecked():
            self._save_current()
        self._set_mod(name)

    def _set_mod(self, name: str) -> None:
        self._current_mod = name
        self._settings.data["last_selected_mod"] = name
        self._settings.save()
        self._mod_label.setText(name)
        self._load_current()

    def _update_status_counts(self, prefix: str) -> None:
        mods_path = _to_path(self._organizer.modsPath())
        if mods_path is None:
            self._status.setText(prefix)
            return
        total = 0
        described = 0
        pid = self._current_profile_id()
        for mod_dir in mods_path.iterdir():
            if not mod_dir.is_dir():
                continue
            total += 1
            mod_name = mod_dir.name
            data = self._desc_manager.load(mod_name)
            profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
            entry = profiles.get(pid, {}) if isinstance(profiles, dict) else {}
            if isinstance(entry, dict) and not self._is_desc_empty(entry):
                described += 1
        self._status.setText(f"{prefix} | {described}/{total} mods described")

    def _is_desc_empty(self, entry: Dict[str, Any]) -> bool:
        if entry.get("short"):
            return False
        if entry.get("detailed"):
            return False
        if entry.get("notes"):
            return False
        if entry.get("url"):
            return False
        if entry.get("compatibility"):
            return False
        if entry.get("color_label"):
            return False
        if int(entry.get("user_rating", 0) or 0) > 0:
            return False
        tags = entry.get("tags", [])
        if isinstance(tags, list) and any(tags):
            return False
        return True


def _find_main_window() -> Optional[QMainWindow]:
    app = QApplication.instance()
    if not app:
        return None
    for w in app.topLevelWidgets():
        if isinstance(w, QMainWindow):
            return w
    return None


def _find_right_tab_widget(window: QMainWindow) -> Optional[QTabWidget]:
    tabs = window.findChildren(QTabWidget)
    if not tabs:
        return None
    known = {"plugins", "archives", "data", "saves", "downloads"}
    for tw in tabs:
        if not tw.isVisible() or tw.count() < 2:
            continue
        labels = {tw.tabText(i).lower() for i in range(tw.count())}
        if len(labels & known) >= 2:
            return tw
    cx = window.geometry().width() // 2
    best, bx = None, -1
    for tw in tabs:
        if not tw.isVisible() or tw.count() < 2:
            continue
        x = window.mapFromGlobal(tw.mapToGlobal(tw.rect().topLeft())).x()
        if x > cx * 0.4 and x > bx:
            best, bx = tw, x
    return best


class ModDescriptionPlugin(mobase.IPluginTool):
    def __init__(self) -> None:
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._widget: Optional[ModDescriptionWidget] = None
        self._attempts = 0
        self._settings_dir: Optional[Path] = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        base = _to_path(organizer.basePath())
        if base is not None:
            self._settings_dir = base / "plugins" / "mod_descriptions_settings"
        QTimer.singleShot(5000, self._try_attach)
        return True

    def name(self) -> str:
        return "Mod Description Manager"

    def author(self) -> str:
        return "Mod Description Manager"

    def description(self) -> str:
        return "Per-mod description manager"

    def version(self) -> mobase.VersionInfo:
        try:
            return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)
        except Exception:
            return mobase.VersionInfo(1, 0, 0)

    def isActive(self) -> bool:
        return True

    def settings(self) -> list:
        return []

    def displayName(self) -> str:
        return "Descriptions"

    def tooltip(self) -> str:
        return self.description()

    def icon(self) -> QIcon:
        return QIcon()

    def display(self) -> None:
        if not self._widget:
            return
        parent = self._widget.parent()
        while parent and not isinstance(parent, QTabWidget):
            parent = parent.parent()
        if isinstance(parent, QTabWidget):
            idx = parent.indexOf(self._widget)
            if idx >= 0:
                parent.setCurrentIndex(idx)

    def _try_attach(self) -> None:
        if self._attempts >= 15:
            return
        self._attempts += 1
        window = _find_main_window()
        if window is None or self._organizer is None:
            QTimer.singleShot(3000, self._try_attach)
            return
        tabs = _find_right_tab_widget(window)
        if tabs is None:
            QTimer.singleShot(3000, self._try_attach)
            return
        for i in range(tabs.count()):
            if tabs.tabText(i) == "📝 Descriptions":
                w = tabs.widget(i)
                if isinstance(w, ModDescriptionWidget):
                    self._widget = w
                return
        settings_dir = self._settings_dir or (_to_path(self._organizer.basePath()) / "plugins" / "mod_descriptions_settings")
        self._widget = ModDescriptionWidget(self._organizer, settings_dir)
        tabs.addTab(self._widget, "📝 Descriptions")


def createPlugin() -> mobase.IPluginTool:
    return ModDescriptionPlugin()
