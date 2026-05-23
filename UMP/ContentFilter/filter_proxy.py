"""QSortFilterProxyModel для фильтрации mod list по имени."""

from typing import Optional, Callable, Dict
import logging

try:
    from PyQt6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, pyqtSignal
    PYQT_VERSION = 6
except ImportError:
    from PyQt5.QtCore import Qt, QSortFilterProxyModel, QModelIndex, pyqtSignal
    PYQT_VERSION = 5

from .content_flags import ContentFlags
from .scanner import ModContentScanner

logger = logging.getLogger("ContentFilter.Proxy")


class FilterMode:
    SHOW_MATCHING = "show"
    HIDE_MATCHING = "hide"


class FilterLogic:
    AND = "AND"
    OR = "OR"
    ONLY = "ONLY"


class ContentFilterProxy(QSortFilterProxyModel):
    """Прокси-модель для фильтрации модов по имени."""

    filterStatsChanged = pyqtSignal(int, int)
    MOD_NAME_COLUMN = 0

    def __init__(self, scanner: ModContentScanner, parent=None):
        super().__init__(parent)
        self._scanner = scanner
        self._filter_enabled = False
        self._show_patterns: set[str] = set()
        self._hide_patterns: set[str] = set()
        self._mod_name_extractor: Optional[Callable[[QModelIndex], str]] = None
        self.setFilterKeyColumn(-1)
        logger.debug("ContentFilterProxy initialized (name-based)")

    def set_mod_name_extractor(self, extractor: Callable[[QModelIndex], str]) -> None:
        self._mod_name_extractor = extractor

    def add_pattern(self, word: str, mode: str) -> None:
        w = (word or "").strip()
        if not w:
            return
        wl = w.lower()
        if mode == FilterMode.SHOW_MATCHING:
            if wl not in self._show_patterns:
                self._show_patterns.add(wl)
                self._hide_patterns.discard(wl)
                logger.debug(f"Added SHOW pattern: '{w}'")
                self.invalidateFilter()
        else:
            if wl not in self._hide_patterns:
                self._hide_patterns.add(wl)
                self._show_patterns.discard(wl)
                logger.debug(f"Added HIDE pattern: '{w}'")
                self.invalidateFilter()

    def remove_pattern(self, word: str) -> None:
        wl = (word or "").strip().lower()
        if wl in self._show_patterns or wl in self._hide_patterns:
            self._show_patterns.discard(wl)
            self._hide_patterns.discard(wl)
            logger.debug(f"Removed pattern: '{word}'")
            self.invalidateFilter()

    def update_pattern_mode(self, word: str, mode: str) -> None:
        wl = (word or "").strip().lower()
        if not wl:
            return
        if mode == FilterMode.SHOW_MATCHING:
            if wl not in self._show_patterns:
                self._show_patterns.add(wl)
            self._hide_patterns.discard(wl)
        else:
            if wl not in self._hide_patterns:
                self._hide_patterns.add(wl)
            self._show_patterns.discard(wl)
        logger.debug(f"Updated pattern mode: '{word}' -> {mode}")
        self.invalidateFilter()

    def clear_patterns(self) -> None:
        if self._show_patterns or self._hide_patterns:
            self._show_patterns.clear()
            self._hide_patterns.clear()
            logger.debug("Cleared all patterns")
            self.invalidateFilter()

    def patterns(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for w in self._show_patterns:
            out[w] = FilterMode.SHOW_MATCHING
        for w in self._hide_patterns:
            out[w] = FilterMode.HIDE_MATCHING
        return out

    def set_filter_enabled(self, enabled: bool) -> None:
        if self._filter_enabled != enabled:
            self._filter_enabled = enabled
            logger.debug(f"Filter enabled: {enabled}")
            self.invalidateFilter()

    def set_filter_mode(self, mode: "FilterMode") -> None:
        logger.debug(f"Filter mode set (unused): {mode}")
        self.invalidateFilter()

    @property
    def is_active(self) -> bool:
        return self._filter_enabled and bool(self._hide_patterns)

    def get_mod_name_from_index(self, source_index: QModelIndex) -> Optional[str]:
        if not source_index.isValid():
            return None
        if self._mod_name_extractor:
            try:
                return self._mod_name_extractor(source_index)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Custom extractor failed: {e}")

        source_model = self.sourceModel()
        if source_model is None:
            return None

        name_index = source_model.index(
            source_index.row(),
            self.MOD_NAME_COLUMN,
            source_index.parent(),
        )

        if PYQT_VERSION == 6:
            role = Qt.ItemDataRole.DisplayRole
            user_role = Qt.ItemDataRole.UserRole
        else:
            role = Qt.DisplayRole
            user_role = Qt.UserRole

        mod_name = source_model.data(name_index, role)
        user_data = source_model.data(name_index, user_role)

        if user_data is not None:
            if hasattr(user_data, "name") and callable(user_data.name):
                try:
                    name = user_data.name()
                    if isinstance(name, str):
                        return name
                except Exception:  # noqa: BLE001
                    pass
            if hasattr(user_data, "name") and isinstance(user_data.name, str):
                return user_data.name

        if isinstance(mod_name, str):
            return mod_name

        return None

    def _to_int(self, value) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                return None
        return None

    def _extract_priority(self, source_index: QModelIndex) -> Optional[int]:
        source_model = self.sourceModel()
        if source_model is None:
            return None

        if PYQT_VERSION == 6:
            user_role = Qt.ItemDataRole.UserRole
            display_role = Qt.ItemDataRole.DisplayRole
        else:
            user_role = Qt.UserRole
            display_role = Qt.DisplayRole

        user_data = source_model.data(source_index, user_role)
        if user_data is not None:
            for attr in ["priority", "modPriority", "mod_priority", "priorityIndex"]:
                if hasattr(user_data, attr):
                    val = getattr(user_data, attr)
                    if callable(val):
                        try:
                            val = val()
                        except Exception:
                            val = None
                    out = self._to_int(val)
                    if out is not None:
                        return out

        display_val = source_model.data(source_index, display_role)
        return self._to_int(display_val)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        l_val = self._extract_priority(left)
        r_val = self._extract_priority(right)
        if l_val is not None and r_val is not None and left.column() == right.column():
            return l_val < r_val
        return super().lessThan(left, right)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._filter_enabled:
            return True

        source_model = self.sourceModel()
        if source_model is None:
            return True

        source_index = source_model.index(source_row, 0, source_parent)
        if source_model.hasChildren(source_index):
            return True

        mod_name = self.get_mod_name_from_index(source_index)
        if not mod_name:
            return True

        name_lc = mod_name.lower()
        for pat in self._hide_patterns:
            if pat and pat in name_lc:
                return False

        return True

    def invalidateFilter(self) -> None:
        super().invalidateFilter()
        visible = self.rowCount()
        source = self.sourceModel()
        total = source.rowCount() if source else 0
        self.filterStatsChanged.emit(visible, total)
        logger.debug(f"Filter applied: {visible}/{total} visible")


class FilterMode:
    SHOW_MATCHING = "show"
    HIDE_MATCHING = "hide"
