import os
import logging
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QSortFilterProxyModel,
    QSettings,
    QPersistentModelIndex,
    QModelIndex,
    QByteArray,
)
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTreeView,
    QHeaderView,
    QLineEdit,
    QProgressBar,
    QAbstractItemView,
)

import mobase
from esp_viewer.ui.esp_structure_loader import EspStructureLoader

logger = logging.getLogger(__name__)

HEADER_LABELS = ["Asset Path", "Field", "Source Record"]
DEFAULT_COL_WIDTHS = [400, 80, 150]


class EspStructureFilterProxyModel(QSortFilterProxyModel):
    """
    Прокси-модель для фильтрации дерева ассетов.
    Обеспечивает видимость родительских узлов, если хотя бы один потомок подходит под фильтр.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(0)


class EspStructureTabPage(QWidget):
    """Панель вкладки со структурой файлов внутри ESP."""

    LOADER_TIMEOUT_MS = 60_000
    SETTINGS_KEY = "esp_structure/column_state"

    def __init__(
        self,
        mod: mobase.IModInterface,
        cache: Dict[str, Any],
        organizer: Any,
    ):
        super().__init__()
        self.mod = mod
        self.cache = cache
        self._organizer = organizer
        self.loader: Optional[EspStructureLoader] = None
        self._timeout_timer: Optional[QTimer] = None
        self._is_destroyed = False
        self._settings: Optional[QSettings] = None
        self._header_signals_blocked = False

        self._setup_ui()
        self._start_loading()

    # ── UI ───────────────────────────────────────────────────────

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # --- Шапка ---
        header_layout = QHBoxLayout()
        self.status_label = QLabel(f"Mod: <b>{self.mod.name()}</b>")
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter files/records...")
        self.search_box.setFixedWidth(250)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._on_filter_text_changed)
        header_layout.addWidget(self.search_box)
        self.main_layout.addLayout(header_layout)

        # --- Debounce-таймер фильтрации (300 мс) ---
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(300)
        self._filter_timer.timeout.connect(self._apply_filter)

        # --- Debounce-таймер сохранения колонок (500 мс) ---
        self._save_header_timer = QTimer(self)
        self._save_header_timer.setSingleShot(True)
        self._save_header_timer.setInterval(500)
        self._save_header_timer.timeout.connect(self._do_save_header_state)

        # --- Модель ---
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(HEADER_LABELS)

        # --- Прокси ---
        self.proxy_model = EspStructureFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        # --- Дерево ---
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tree_view.setUniformRowHeights(True)

        # --- Заголовок ---
        self.header = self.tree_view.header()
        self.header.setStretchLastSection(False)
        self.header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.header.sectionResized.connect(self._on_header_resized)

        self.main_layout.addWidget(self.tree_view)

        # --- Прогресс ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.main_layout.addWidget(self.progress)

        # --- Восстановление размеров колонок ---
        self._load_header_state()

    # ── Настройки (QSettings) ────────────────────────────────────

    def _get_settings(self) -> QSettings:
        """Возвращает кешированный объект настроек."""
        if self._settings is not None:
            return self._settings

        try:
            data_path = self._organizer.pluginDataPath()
            if data_path:
                os.makedirs(data_path, exist_ok=True)
                ini_path = os.path.join(
                    data_path, "esp_structure_settings.ini"
                )
                self._settings = QSettings(
                    ini_path, QSettings.Format.IniFormat
                )
                logger.debug("Settings path: %s", ini_path)
                return self._settings
        except Exception as e:
            logger.warning(
                "Could not use MO2 plugin data path: %s", e
            )

        self._settings = QSettings("ModOrganizer", "ESPStructureTab")
        return self._settings

    # ── Сохранение / загрузка колонок ────────────────────────────

    def _on_header_resized(self, logical_index: int, old_size: int, new_size: int):
        """Вызывается при каждом изменении ширины колонки."""
        if self._header_signals_blocked:
            return
        self._save_header_timer.start()

    def _do_save_header_state(self):
        """Сохраняет ширины колонок через QSettings (debounced)."""
        if self._is_destroyed:
            return
        try:
            settings = self._get_settings()
            widths = [
                self.header.sectionSize(i)
                for i in range(self.header.count())
            ]
            settings.setValue(self.SETTINGS_KEY, widths)
            settings.sync()
            logger.debug("Saved column widths: %s", widths)
        except Exception as e:
            logger.warning("Failed to save header state: %s", e)

    def _load_header_state(self):
        """Загружает ширины колонок из QSettings."""
        self._header_signals_blocked = True
        try:
            settings = self._get_settings()
            widths = settings.value(self.SETTINGS_KEY)

            if widths and isinstance(widths, list):
                int_widths = []
                for w in widths:
                    try:
                        int_widths.append(int(w))
                    except (ValueError, TypeError):
                        int_widths.append(None)

                for i, w in enumerate(int_widths):
                    if i < self.header.count() and w and w > 0:
                        self.tree_view.setColumnWidth(i, w)

                logger.debug("Restored column widths: %s", int_widths)
            else:
                for i, w in enumerate(DEFAULT_COL_WIDTHS):
                    if i < self.header.count():
                        self.tree_view.setColumnWidth(i, w)
                logger.debug("Applied default column widths")
        except Exception as e:
            logger.warning("Failed to load header state: %s", e)
            for i, w in enumerate(DEFAULT_COL_WIDTHS):
                if i < self.header.count():
                    self.tree_view.setColumnWidth(i, w)
        finally:
            self._header_signals_blocked = False

    # ── Загрузка данных ──────────────────────────────────────────

    def _start_loading(self):
        mod_path = self.mod.absolutePath()
        if not mod_path or not os.path.exists(mod_path):
            self.status_label.setText("⚠ Mod directory not found.")
            return

        esp_paths: List[str] = []
        try:
            logger.info(
                "Scanning physical directory for plugins: %s", mod_path
            )
            for f in os.listdir(mod_path):
                if f.lower().endswith((".esp", ".esm", ".esl")):
                    full_path = os.path.join(mod_path, f)
                    if os.path.isfile(full_path):
                        esp_paths.append(full_path)
                        logger.info("Found plugin for analysis: %s", f)
        except Exception as e:
            logger.error("Error listing physical mod directory: %s", e)
            self.status_label.setText(
                "⚠ Error reading physical mod directory."
            )
            return

        if not esp_paths:
            self.status_label.setText(
                "No plugin files found in the mod's physical root."
            )
            return

        self.status_label.setText(
            f"Scanning {len(esp_paths)} plugin(s) from mod folder..."
        )
        self.progress.setVisible(True)

        # Очищаем строки, НЕ трогая заголовки — сохраняем ширины колонок
        self.model.removeRows(0, self.model.rowCount())

        # Создаём загрузчик
        self.loader = EspStructureLoader(esp_paths, self.cache)

        logger.info("Connecting loader signals to UI slots...")
        self.loader.pluginDataReady.connect(self._on_plugin_data_ready)
        self.loader.allFinished.connect(self._on_all_finished)
        self.loader.started.connect(
            lambda: logger.info("Loader thread STARTED")
        )
        self.loader.finished.connect(
            lambda: logger.info("Loader thread FINISHED (low-level)")
        )

        # Таймаут
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_loading_timeout)
        self._timeout_timer.start(self.LOADER_TIMEOUT_MS)

        # Запуск с небольшой задержкой для Event Loop
        logger.info("Scheduling loader start in 50ms...")
        QTimer.singleShot(50, self.loader.start)

    # ── Обработка данных от загрузчика ───────────────────────────

    def _on_plugin_data_ready(self, esp_path: str, esp_data: Any):
        logger.info(
            "UI thread received pluginDataReady for %s",
            os.path.basename(esp_path),
        )
        if self._is_destroyed:
            return

        try:
            self.tree_view.setUpdatesEnabled(False)
            try:
                esp_name = os.path.basename(esp_path)

                if isinstance(esp_data, str):
                    esp_item = QStandardItem(f"{esp_name} (Error)")
                    esp_item.setEditable(False)
                    detail_item = QStandardItem(esp_data)
                    detail_item.setEditable(False)
                    error_item = QStandardItem("Error")
                    error_item.setEditable(False)
                    self.model.appendRow(
                        [esp_item, error_item, detail_item]
                    )
                    return

                if not esp_data:
                    esp_item = QStandardItem(f"{esp_name} (Empty)")
                    esp_item.setEditable(False)
                    empty_item = QStandardItem("Empty")
                    empty_item.setEditable(False)
                    no_paths_item = QStandardItem("No paths found")
                    no_paths_item.setEditable(False)
                    self.model.appendRow(
                        [esp_item, empty_item, no_paths_item]
                    )
                    return

                for sig in sorted(esp_data.keys()):
                    root_text = f"{esp_name} ({sig})"
                    root_item = QStandardItem(root_text)
                    root_item.setEditable(False)
                    font = root_item.font()
                    font.setBold(True)
                    root_item.setFont(font)

                    records = esp_data[sig]
                    for rec_id, assets in sorted(records.items()):
                        for field_sig, path in assets:
                            path_item = QStandardItem(path)
                            path_item.setEditable(False)
                            field_item = QStandardItem(field_sig)
                            field_item.setEditable(False)
                            rec_item = QStandardItem(rec_id)
                            rec_item.setEditable(False)
                            root_item.appendRow(
                                [path_item, field_item, rec_item]
                            )

                    col1 = QStandardItem("")
                    col1.setEditable(False)
                    col2 = QStandardItem("")
                    col2.setEditable(False)
                    self.model.appendRow([root_item, col1, col2])

                    # Используем QPersistentModelIndex для безопасного
                    # отложенного разворачивания
                    persistent_idx = QPersistentModelIndex(
                        root_item.index()
                    )
                    QTimer.singleShot(
                        0,
                        lambda idx=persistent_idx: self._expand_item(idx),
                    )

            finally:
                self.tree_view.setUpdatesEnabled(True)
                self.tree_view.update()
        except Exception as e:
            logger.error(
                "Error in UI thread while processing %s: %s",
                esp_path,
                e,
                exc_info=True,
            )

    def _on_all_finished(self):
        logger.info("UI thread received allFinished signal.")
        if self._is_destroyed:
            return
        self._stop_timeout()
        self.progress.setVisible(False)
        self.status_label.setText(
            f"Analysis complete for <b>{self.mod.name()}</b>"
        )

    def _expand_item(self, source_idx):
        """Разворачивает узел дерева по QPersistentModelIndex."""
        if self._is_destroyed:
            return
        if not source_idx.isValid():
            return
        model_idx = QModelIndex(source_idx)
        proxy_idx = self.proxy_model.mapFromSource(model_idx)
        if proxy_idx.isValid():
            self.tree_view.setExpanded(proxy_idx, True)

    # ── Таймаут ──────────────────────────────────────────────────

    def _on_loading_timeout(self):
        if self._is_destroyed:
            return
        logger.warning("Loader timed out for mod %s", self.mod.name())
        self.cleanup()
        self.status_label.setText(
            "⚠ Loading timed out (plugin files too large or complex)."
        )
        self.progress.setVisible(False)

    def _stop_timeout(self):
        if self._timeout_timer:
            self._timeout_timer.stop()
            self._timeout_timer = None

    # ── Фильтрация ──────────────────────────────────────────────

    def _on_filter_text_changed(self, text: str):
        self._filter_timer.start()

    def _apply_filter(self):
        text = self.search_box.text().strip()
        self.proxy_model.setFilterFixedString(text)

        if text:
            self.tree_view.expandAll()
        else:
            self.tree_view.collapseAll()
            for i in range(self.proxy_model.rowCount()):
                idx = self.proxy_model.index(i, 0)
                self.tree_view.setExpanded(idx, True)

    # ── Очистка ресурсов ─────────────────────────────────────────

    def cleanup(self):
        """Останавливает фоновый поток и сохраняет состояние."""
        if self._is_destroyed:
            return
        self._is_destroyed = True

        # Принудительно сохраняем колонки перед уничтожением
        self._save_header_timer.stop()
        self._do_save_header_state()

        self._stop_timeout()

        if self.loader:
            try:
                self.loader.pluginDataReady.disconnect(
                    self._on_plugin_data_ready
                )
            except (TypeError, RuntimeError):
                pass
            try:
                self.loader.allFinished.disconnect(
                    self._on_all_finished
                )
            except (TypeError, RuntimeError):
                pass

            if self.loader.isRunning():
                self.loader.stop()
                if not self.loader.wait(3000):
                    logger.error(
                        "Loader thread did not stop in time, terminating"
                    )
                    self.loader.terminate()
                    self.loader.wait(1000)
            self.loader = None

    def hideEvent(self, event):
        """
        Вызывается когда виджет скрывается (переключение вкладки,
        закрытие диалога). Сохраняем колонки.
        """
        self._save_header_timer.stop()
        self._do_save_header_state()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def __del__(self):
        """Подстраховка: попытка очистки при сборке мусора."""
        try:
            self.cleanup()
        except (RuntimeError, Exception):
            pass