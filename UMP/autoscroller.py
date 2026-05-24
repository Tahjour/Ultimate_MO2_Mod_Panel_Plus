"""
Auto Scroll Highlight Plugin for Mod Organizer 2
v2.0 — Optimized, no UI lag
"""

import mobase
from PyQt6.QtCore import (
    Qt, QTimer, QEvent, QObject, QModelIndex,
    QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtWidgets import (
    QApplication, QTreeView, QAbstractItemView,
)
from PyQt6.QtGui import QShortcut, QKeySequence
from typing import Optional, Dict, Callable


DEBUG = False  # Включить для отладки


def _log(msg: str) -> None:
    if DEBUG:
        print(f"[AutoScroll] {msg}")


class ViewSelectionWatcher(QObject):
    """Следит ТОЛЬКО за selectionChanged — никаких paint/event filter."""

    def __init__(
        self,
        view: QTreeView,
        callback: Callable[[str], None],
        view_name: str = "",
        skip_parents: bool = False,
    ):
        super().__init__(view)
        self._view = view
        self._callback = callback
        self._view_name = view_name
        self._skip_parents = skip_parents
        self._connect()

        # Переподключение при смене модели
        view.installEventFilter(self)

    # ── Подключение к selectionModel ──────────────────────────

    def _connect(self) -> None:
        sel = self._view.selectionModel()
        if not sel:
            return
        try:
            sel.selectionChanged.disconnect(self._on_selection)
        except (TypeError, RuntimeError):
            pass
        sel.selectionChanged.connect(self._on_selection)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Единственное, что ловим — смена дочерних объектов (= смена модели)
        if obj is self._view and event.type() == QEvent.Type.ChildAdded:
            QTimer.singleShot(200, self._connect)
        return False

    # ── Обработка выбора ──────────────────────────────────────

    def _on_selection(self, selected, _deselected) -> None:
        indexes = selected.indexes()
        if not indexes:
            return

        index = indexes[0]

        # BSPlugins: пропускаем группы-родители
        if self._skip_parents and not index.parent().isValid():
            model = self._view.model()
            if model and model.hasChildren(index):
                return

        name = index.data(Qt.ItemDataRole.DisplayRole)
        if name:
            _log(f"[{self._view_name}] selected: {name}")
            self._callback(str(name))


class AutoScrollHighlightPlugin(mobase.IPlugin):
    """Синхронная прокрутка modList ↔ pluginList по выбору."""

    def __init__(self):
        super().__init__()
        self._organizer: Optional[mobase.IOrganizer] = None
        self._mods_view: Optional[QTreeView] = None
        self._plugins_view: Optional[QTreeView] = None
        self._syncing = False
        self._enabled = True
        self._using_bsplugins = False
        self._mod_watcher = None
        self._plugin_watcher = None

        # Кэш: plugin_name → mod_name (строится один раз, сбрасывается по необходимости)
        self._origin_cache: Dict[str, str] = {}
        self._origin_cache_valid = False

        # prevent GC
        self._refs: list = []

    # ── IPlugin interface ─────────────────────────────────────

    def name(self) -> str:
        return "Auto Scroll Highlight"

    def author(self) -> str:
        return "Plugin Author"

    def description(self) -> str:
        return "Автопрокрутка modList ↔ pluginList при выборе элемента"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(2, 0, 0, mobase.ReleaseType.FINAL)

    def isActive(self) -> bool:
        return True

    def settings(self) -> list:
        return []

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        organizer.onUserInterfaceInitialized(self._setup)
        return True

    # ── Setup ─────────────────────────────────────────────────

    def _setup(self, main_window=None) -> None:
        self._refresh_views()

        # Сбрасываем кэш при изменении списка модов/плагинов
        if self._organizer:
            self._organizer.modList().onModStateChanged(
                self._on_mod_state_changed
            )
            self._organizer.pluginList().onPluginStateChanged(
                self._on_plugin_state_changed
            )

        # Горячая клавиша
        if main_window:
            sc = QShortcut(QKeySequence(Qt.Key.Key_F10), main_window)
            sc.activated.connect(self._toggle)
            self._refs.append(sc)

        _log("Setup complete. F10 to toggle.")

    def _on_mod_state_changed(self, _changes: dict) -> None:
        self._invalidate_cache()

    def _on_plugin_state_changed(self, _changes: dict) -> None:
        self._invalidate_cache()

    def _refresh_views(self) -> None:
        mods_view = None
        plugins_view = None
        using_bsplugins = False
        for widget in QApplication.allWidgets():
            if not isinstance(widget, QTreeView):
                continue
            name = widget.objectName()
            if name == "modList":
                mods_view = widget
            elif name == "pluginList":
                plugins_view = widget
                using_bsplugins = True
            elif name == "espList" and plugins_view is None:
                plugins_view = widget

        self._mods_view = mods_view
        self._plugins_view = plugins_view
        self._using_bsplugins = using_bsplugins
        self._attach_watchers()

    def _attach_watchers(self) -> None:
        if self._mods_view:
            if self._mod_watcher is None or getattr(self._mod_watcher, "_view", None) is not self._mods_view:
                w = ViewSelectionWatcher(
                    self._mods_view, self._on_mod_selected,
                    view_name="modList", skip_parents=False,
                )
                self._mod_watcher = w
                self._refs.append(w)

        if self._plugins_view:
            if self._plugin_watcher is None or getattr(self._plugin_watcher, "_view", None) is not self._plugins_view:
                w = ViewSelectionWatcher(
                    self._plugins_view, self._on_plugin_selected,
                    view_name="pluginList", skip_parents=self._using_bsplugins,
                )
                self._plugin_watcher = w
                self._refs.append(w)

    # ── Кэш origin ───────────────────────────────────────────

    def _invalidate_cache(self) -> None:
        self._origin_cache_valid = False
        self._origin_cache.clear()

    def _ensure_cache(self) -> None:
        if self._origin_cache_valid:
            return
        pl = self._organizer.pluginList()
        if not pl:
            return
        cache: Dict[str, str] = {}
        for plugin_name in pl.pluginNames():
            origin = pl.origin(plugin_name)
            if origin:
                cache[plugin_name] = origin
        self._origin_cache = cache
        self._origin_cache_valid = True

    # ── Переключение ──────────────────────────────────────────

    def _toggle(self) -> None:
        self._enabled = not self._enabled
        if self._enabled:
            self._syncing = False
            self._refresh_views()
            self._invalidate_cache()
        print(f"[AutoScroll] {'ENABLED' if self._enabled else 'DISABLED'}")

    # ── Мод выбран → скроллим к плагину ───────────────────────

    def _on_mod_selected(self, mod_name: str) -> None:
        if not self._enabled or self._syncing:
            return
        if not self._plugins_view or not self._organizer:
            return

        self._ensure_cache()

        # Быстрый поиск первого плагина мода через кэш
        target_plugin: Optional[str] = None
        mod_list = self._organizer.modList()

        for plugin_name, origin in self._origin_cache.items():
            if origin == mod_name:
                target_plugin = plugin_name
                break
            # Сравниваем по displayName
            if mod_list and mod_list.displayName(origin) == mod_name:
                target_plugin = plugin_name
                break

        if not target_plugin:
            _log(f"No plugin for mod '{mod_name}'")
            return

        _log(f"Mod '{mod_name}' → plugin '{target_plugin}'")
        self._do_scroll(self._plugins_view, target_plugin)

    # ── Плагин выбран → скроллим к моду ───────────────────────

    def _on_plugin_selected(self, plugin_name: str) -> None:
        if not self._enabled or self._syncing:
            return
        if not self._mods_view or not self._organizer:
            return

        self._ensure_cache()
        mod_name = self._origin_cache.get(plugin_name)

        if not mod_name or mod_name.lower() in ("data", "overwrite", "<data>", ""):
            return

        # display name для поиска в modList
        mod_list = self._organizer.modList()
        display = mod_list.displayName(mod_name) if mod_list else mod_name

        _log(f"Plugin '{plugin_name}' → mod '{display}'")
        self._do_scroll(self._mods_view, display)

    # ── Прокрутка ─────────────────────────────────────────────

    def _do_scroll(self, view: QTreeView, item_name: str) -> None:
        """Находит элемент и плавно скроллит к нему."""
        self._syncing = True

        index = self._find_index(view, item_name)
        if index and index.isValid():
            self._smooth_scroll(view, index)
        else:
            _log(f"'{item_name}' not found in {view.objectName()}")

        # Снимаем блокировку через 200 мс
        QTimer.singleShot(200, self._unlock)

    def _find_index(self, view: QTreeView, name: str) -> Optional[QModelIndex]:
        model = view.model()
        if not model:
            return None

        # Быстрый поиск через match
        matches = model.match(
            model.index(0, 0),
            Qt.ItemDataRole.DisplayRole,
            name, 1,
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )
        if matches:
            return matches[0]

        return None

    def _smooth_scroll(
        self, view: QTreeView, index: QModelIndex, duration: int = 200
    ) -> None:
        scrollbar = view.verticalScrollBar()
        if not scrollbar:
            view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
            return

        # Expand parents (BSPlugins)
        parent = index.parent()
        while parent.isValid():
            view.expand(parent)
            parent = parent.parent()

        start = scrollbar.value()

        # Узнаём целевую позицию без визуальных артефактов
        view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        end = scrollbar.value()

        if start == end:
            return  # уже видно

        # Возвращаем и анимируем
        scrollbar.setValue(start)

        anim = QPropertyAnimation(scrollbar, b"value", view)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        view._asc_anim = anim  # prevent GC
        anim.start()

    def _unlock(self) -> None:
        self._syncing = False


def createPlugin() -> mobase.IPlugin:
    return AutoScrollHighlightPlugin()
