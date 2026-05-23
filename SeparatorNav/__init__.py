

from __future__ import annotations

from typing import Optional

import mobase
from PyQt6.QtCore import Qt, QTimer, QModelIndex
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QTreeView,
    QAbstractItemView,
)


def _find_right_pane(window) -> Optional[QTabWidget]:
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
    best: Optional[QTabWidget] = None
    bx = -1
    for tw in tabs:
        if not tw.isVisible() or tw.count() < 2:
            continue
        x = window.mapFromGlobal(tw.mapToGlobal(tw.rect().topLeft())).x()
        if x > cx * 0.4 and x > bx:
            best, bx = tw, x
    return best


def _find_modlist_view(window) -> Optional[QTreeView]:
    """Ищем QTreeView модлиста — он находится в левой панели MO2."""
    trees = window.findChildren(QTreeView)
    if not trees:
        return None

    cx = window.geometry().width() // 2
    best: Optional[QTreeView] = None
    best_rows = 0

    for tv in trees:
        if not tv.isVisible():
            continue
        model = tv.model()
        if model is None:
            continue
        rows = model.rowCount()
        if rows < 2:
            continue
        # Модлист обычно слева
        x = window.mapFromGlobal(tv.mapToGlobal(tv.rect().topLeft())).x()
        if x < cx and rows > best_rows:
            best = tv
            best_rows = rows
    return best


class SeparatorPanelWidget(QWidget):
    def __init__(
        self,
        organizer: mobase.IOrganizer,
        main_window,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._org = organizer
        self._window = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._header = QLabel("Separators", self)
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._header)

        self._list = QListWidget(self)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()

        self.refresh()

    # ------------------------------------------------------------------ #
    #  Сбор сепараторов
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self._list.clear()
        modlist = self._org.modList()
        all_mods = modlist.allMods()

        for mod_name in all_mods:
            if not mod_name.endswith("_separator"):
                continue

            display = mod_name[: -len("_separator")]

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, mod_name)

            # Цвет сепаратора — пытаемся достать из MO2
            try:
                sep_color = modlist.getModColor(mod_name)  # type: ignore[attr-defined]
                if sep_color and sep_color.isValid():
                    item.setForeground(sep_color)
            except Exception:
                pass

            state = modlist.state(mod_name)
            if state & mobase.ModState.ACTIVE:  # type: ignore[attr-defined]
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

            self._list.addItem(item)

        self._header.setText(f"Separators ({self._list.count()})")

    # ------------------------------------------------------------------ #
    #  Клик → скролл в модлисте
    # ------------------------------------------------------------------ #
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        mod_name: str = item.data(Qt.ItemDataRole.UserRole)
        if not mod_name:
            return

        tv = _find_modlist_view(self._window)
        if tv is None:
            return

        model = tv.model()
        if model is None:
            return

        idx = self._find_mod_index(model, mod_name)
        if idx.isValid():
            tv.setCurrentIndex(idx)
            tv.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)

    # ------------------------------------------------------------------ #
    #  Поиск QModelIndex по имени мода
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_mod_index(model, mod_name: str) -> QModelIndex:
        """Перебираем строки модели и ищем совпадение по тексту первого столбца."""
        rows = model.rowCount()
        for r in range(rows):
            idx = model.index(r, 0)
            text = model.data(idx, Qt.ItemDataRole.DisplayRole)
            if text is not None and str(text) == mod_name:
                return idx

            # Иногда MO2 показывает имя без суффикса _separator
            display = mod_name
            if mod_name.endswith("_separator"):
                display = mod_name[: -len("_separator")]
            if text is not None and str(text) == display:
                return idx

        # Фоллбек: поиск через match (column 0)
        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            mod_name,
            1,
            Qt.MatchFlag.MatchExactly,
        )
        if matches:
            return matches[0]

        if mod_name.endswith("_separator"):
            display = mod_name[: -len("_separator")]
            matches = model.match(
                model.index(0, 0),
                Qt.ItemDataRole.DisplayRole,
                display,
                1,
                Qt.MatchFlag.MatchExactly,
            )
            if matches:
                return matches[0]

        return QModelIndex()


# ==================================================================== #
#  Плагин
# ==================================================================== #
class SeparatorNavPlugin(mobase.IPluginTool):
    NAME = "Separator Navigator"

    def __init__(self) -> None:
        super().__init__()
        self._org: Optional[mobase.IOrganizer] = None
        self._window = None
        self._widget: Optional[SeparatorPanelWidget] = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._on_ui_ready)
        return True

    def name(self) -> str:
        return self.NAME

    def author(self) -> str:
        return "Separator Navigator"

    def description(self) -> str:
        return "Shows a list of separators and scrolls the mod-list on click."

    def version(self) -> mobase.VersionInfo:
        try:
            return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)
        except AttributeError:
            return mobase.VersionInfo(1, 0, 0)

    def requirements(self) -> list:
        return []

    def isActive(self) -> bool:
        return True

    def settings(self) -> list[mobase.PluginSetting]:
        return []

    def displayName(self) -> str:
        return self.NAME

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

    # ---------------------------------------------------------------- #
    def _on_ui_ready(self, main_window) -> None:
        self._window = main_window
        QTimer.singleShot(800, self._inject_tab)

    def _inject_tab(self) -> None:
        if not self._window or self._widget is not None:
            return
        tw = _find_right_pane(self._window)
        if not tw:
            return

        tab_title = "Separators"
        for i in range(tw.count()):
            if tw.tabText(i) == tab_title:
                w = tw.widget(i)
                if isinstance(w, SeparatorPanelWidget):
                    self._widget = w
                    return

        self._widget = SeparatorPanelWidget(self._org, self._window)
        tw.addTab(self._widget, tab_title)


def createPlugin() -> mobase.IPluginTool:
    return SeparatorNavPlugin()
