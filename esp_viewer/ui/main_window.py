import logging
import os
from typing import Dict, List, Optional, Set, Tuple, Union

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QSettings, QByteArray, QModelIndex, QSize, 
    QAbstractItemModel, pyqtSignal as Signal
)
from PyQt6.QtGui import QAction, QBrush, QColor, QPalette, QStandardItem, QStandardItemModel, QGuiApplication, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QMenu,
    QSplitter,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QToolButton,
    QTreeView,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QTabWidget,
    QStyledItemDelegate,
    QStyle,
)

from esp_viewer.constants2 import RECORD_SIGNATURE_TYPES
from esp_viewer.core.conflict_analyzer import (
    ConflictAnalysisResult,
    ConflictStatus,
    is_conflict_status,
    is_winning_status,
    is_losing_status,
)
from esp_viewer.core.data_types import Group, PluginFile, Record, LazyPluginIndex
from esp_viewer.core.group_parser import MAX_RECURSION_DEPTH
from esp_viewer.core.plugin_file import parse_plugin, create_lazy_index, parse_record_at_offset
from esp_viewer.core.localization import StringTables, load_string_tables
from esp_viewer.core.formid_resolver import FormIDResolver
from esp_viewer.core.record_parser import extract_string_field
from esp_viewer.core.search_engine import (
    iter_groups,
    iter_records,
    search_records,
)
from esp_viewer.formatting.group_formatter import format_group_label, format_record_identity, group_type_label
from esp_viewer.formatting.record_formatter import DetailNode, StructuredSubrecordParser
from esp_viewer.formatting.value_formatter import format_file_size
from esp_viewer.ui.export.export_dialog import ExportDialog
from esp_viewer.ui.export.export_thread import ExportThread, ExportWorker
from esp_viewer.ui.loader_thread import PluginLoaderThread, RecordStructureLoaderThread
from esp_viewer.ui.search_widget import SearchWidget
from esp_viewer.ui.tools_panel import ToolsPanel

logger = logging.getLogger(__name__)

NODE_DATA_ROLE = Qt.ItemDataRole.UserRole + 1
DETAIL_REF_ROLE = Qt.ItemDataRole.UserRole + 2
TREE_REF_ROLE = Qt.ItemDataRole.UserRole + 3
LAZY_ROLE = Qt.ItemDataRole.UserRole + 4
STRUCTURE_PATH_ROLE = Qt.ItemDataRole.UserRole + 5

class StructureNode:
    """Internal node for StructureItemModel."""
    def __init__(self, key: Union[str, Tuple, int, None], name: str, parent: Optional['StructureNode'] = None) -> None:
        self.key = key
        self.name = name
        self.parent = parent
        self.children: List['StructureNode'] = []
        self.values: List[str] = []
        self.path: Tuple = parent.path + (key,) if parent else (key,)

    def append_child(self, child: 'StructureNode') -> None:
        self.children.append(child)

    def row(self) -> int:
        if self.parent:
            try:
                return self.parent.children.index(self)
            except ValueError:
                return 0
        return 0

class StructureItemModel(QAbstractItemModel):
    """Кастомная модель для отображения структуры записей из нескольких плагинов."""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._root_node = StructureNode(None, "Root")
        self._headers: List[str] = ["Field"]
        self._winner_index: int = -1

    def set_data(self, merged_tree: List[Dict], value_maps: List[Dict], plugins: List[str], winner_index: int) -> None:
        self.beginResetModel()
        self._root_node = StructureNode(None, "Root")
        self._headers = ["Field"] + plugins
        self._winner_index = winner_index

        def build_internal_tree(source_nodes: List[Dict], parent_node: StructureNode, base_path: Tuple) -> None:
            for node in source_nodes:
                node_key = node.get("key")
                if node_key is None: continue

                name = node.get("name")
                if not name:
                    if isinstance(node_key, tuple) and len(node_key) > 0:
                        name = str(node_key[0])
                    elif node_key:
                        name = str(node_key)

                if not name:
                    name = "Unknown Field"

                internal_node = StructureNode(node_key, str(name), parent_node)
                path = base_path + (node_key,)

                # Заполняем значения из всех плагинов
                for value_map in value_maps:
                    internal_node.values.append(value_map.get(path, ""))

                parent_node.append_child(internal_node)

                children = node.get("children")
                if children:
                    build_internal_tree(children, internal_node, path)

        build_internal_tree(merged_tree, self._root_node, ())
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._root_node.children)
        return len(parent.internalPointer().children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_node = parent.internalPointer() if parent.isValid() else self._root_node
        child_node = parent_node.children[row]
        return self.createIndex(row, column, child_node)

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_node = index.internalPointer()
        parent_node = child_node.parent

        if parent_node == self._root_node or parent_node is None:
            return QModelIndex()

        return self.createIndex(parent_node.row(), 0, parent_node)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> any:
        if not index.isValid():
            return None

        node = index.internalPointer()
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return node.name
            else:
                val_idx = col - 1
                if 0 <= val_idx < len(node.values):
                    return node.values[val_idx]

        if role == Qt.ItemDataRole.BackgroundRole:
            if col > 0:
                val_idx = col - 1
                row_values = node.values
                if not row_values or val_idx >= len(row_values):
                    return None

                distinct = {v for v in row_values if v}
                if len(distinct) > 1:
                    winner_col = self._winner_index if 0 <= self._winner_index < len(row_values) else len(row_values) - 1
                    winner_value = row_values[winner_col]

                    if val_idx == winner_col:
                        return QColor(0, 255, 0, 128) # Green for winner

                    current_value = row_values[val_idx]
                    if current_value and current_value != winner_value:
                        # Ищем, есть ли кто-то еще с таким же значением
                        is_loser = True
                        for i in range(winner_col - 1, -1, -1):
                            if row_values[i] and row_values[i] != winner_value:
                                if i == val_idx:
                                    return QColor(255, 0, 0, 128) # Red for direct loser
                                break
                        return QColor(255, 170, 0, 128) # Orange for other conflicts
                elif len(distinct) == 1:
                    # Если все значения одинаковы, но это оверрайд (есть в нескольких плагинах),
                    # подсвечиваем всех участников зеленым для наглядности (как в xEdit)
                    if sum(1 for v in row_values if v) > 1:
                        if val_idx < len(row_values) and row_values[val_idx]:
                            return QColor(0, 255, 0, 128) # Green for participants of same value override

        if role == STRUCTURE_PATH_ROLE:
            return node.path

        return None

class StructureHighlightDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background is not None:
            option.palette.setBrush(QPalette.ColorRole.Highlight, QBrush(background))
            option.palette.setColor(
                QPalette.ColorRole.HighlightedText,
                option.palette.color(QPalette.ColorRole.Text),
            )

class StructureHeaderView(QHeaderView):
    """Кастомный заголовок для подсветки текущего плагина."""
    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._highlight_col = -1
        self._highlight_bg = QBrush(QColor(0, 120, 215)) # Blue
        self._highlight_fg = QColor(Qt.GlobalColor.white)
        self._bold_font = QFont()
        self._bold_font.setBold(True)

    def set_highlight_column(self, col: int) -> None:
        self._highlight_col = col
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex) -> None:
        if logicalIndex == self._highlight_col:
            painter.save()
            # Рисуем фон
            painter.fillRect(rect, self._highlight_bg)

            # Рисуем текст
            painter.setFont(self._bold_font)
            painter.setPen(self._highlight_fg)

            text = self.model().headerData(logicalIndex, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            if text:
                # Центрируем текст с учетом отступов
                painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, str(text))

            # Рисуем границы, чтобы секция выделялась
            painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

            painter.restore()
        else:
            super().paintSection(painter, rect, logicalIndex)

class HeaderHighlightDelegate(QStyledItemDelegate):
    """Делегат для заголовков, поддерживающий фоновый цвет и жирный шрифт."""
    def paint(self, painter, option, index) -> None:
        model = index.model()
        col = index.column()

        # Получаем данные напрямую из модели через headerData
        bg_brush = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.BackgroundRole)
        fg_brush = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.ForegroundRole)
        font_data = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.FontRole)

        # Обработка QVariant для PyQt6
        if hasattr(bg_brush, "value"): bg_brush = bg_brush.value()
        if hasattr(fg_brush, "value"): fg_brush = fg_brush.value()
        if hasattr(font_data, "value"): font_data = font_data.value()

        if isinstance(bg_brush, QBrush) or isinstance(font_data, QFont):
            painter.save()

            # Рисуем фон
            if isinstance(bg_brush, QBrush):
                painter.fillRect(option.rect, bg_brush)
            else:
                # Рисуем стандартный фон, если нет кастомного
                option.state |= QStyle.StateFlag.State_Enabled
                option.rect = option.rect
                painter.setOpacity(1.0)
                # CE_Header uses CE_HeaderSection
                # But since we want to be safe, we can just let super().paint do its job if no bg
                pass

            # Настройка шрифта
            if isinstance(font_data, QFont):
                painter.setFont(font_data)
            else:
                painter.setFont(option.font)

            # Настройка цвета текста
            if isinstance(fg_brush, QBrush):
                painter.setPen(fg_brush.color())
            else:
                painter.setPen(option.palette.color(QPalette.ColorRole.ButtonText))

            # Получаем текст
            text = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            if text is None:
                text = index.data(Qt.ItemDataRole.DisplayRole)

            if text:
                # Рисуем текст по центру с небольшим отступом
                rect = option.rect.adjusted(4, 0, -4, 0)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, str(text))

            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index) -> QSize:
        return super().sizeHint(option, index)

class FlyoutPopup(QWidget):
    closed = Signal()

    def __init__(self, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._content = content
        self._content.setParent(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._content)

    def open_at(self, anchor: QWidget) -> None:
        self._position_near_anchor(anchor)
        self.show()
        self.raise_()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        return super().closeEvent(event)

    def _position_near_anchor(self, anchor: QWidget) -> None:
        hint = self.sizeHint()
        width = max(hint.width(), anchor.width())
        height = hint.height()
        anchor_top_left = anchor.mapToGlobal(QPoint(0, 0))
        anchor_bottom_left = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = QGuiApplication.screenAt(anchor_top_left) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        x = anchor_bottom_left.x()
        y = anchor_bottom_left.y()
        if x + width > available.right():
            x = max(available.right() - width, available.left())
        if y + height > available.bottom():
            y = anchor_top_left.y() - height
        if y < available.top():
            y = available.top()
        self.setGeometry(x, y, width, height)

class PluginViewerWidget(QWidget):
    """Виджет для просмотра плагина, который можно встроить в любое окно или панель."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._settings = QSettings("esp_viewer", "esp_viewer")
        self._active_flyout: Optional[FlyoutPopup] = None

        self.current_plugin: Optional[PluginFile] = None
        self._record_index: Dict[Tuple[str, int], QStandardItem] = {}
        self._group_index: Dict[int, QStandardItem] = {}
        self._record_paths: Dict[Tuple[str, int], List[Group]] = {}
        self._conflict_statuses: Dict[Tuple[str, int], ConflictStatus] = {}
        self._conflict_details: Dict[Tuple[str, int], object] = {}
        self._load_order: List[str] = []
        self._conflict_pending = False
        self._conflict_filter_only = False
        self._conflict_filter_hide_identical = False
        self._conflict_filter_mode: str = "all"
        self._conflict_only_box: Optional[QCheckBox] = None
        self._conflict_hide_identical_box: Optional[QCheckBox] = None
        self._conflict_mode_combo: Optional[QComboBox] = None
        self._plugin_cache: Dict[str, PluginFile] = {}
        self._lazy_index_cache: Dict[str, LazyPluginIndex] = {}
        self._history: List[Tuple[Optional[str], int]] = []
        self._history_index = -1
        self._detail_matches: List[QStandardItem] = []
        self._detail_match_index = -1
        self._loader_thread: Optional[PluginLoaderThread] = None
        self._structure_thread: Optional[RecordStructureLoaderThread] = None
        self._quick_filter_text: Optional[str] = None
        self._quick_filter_mode = "Signature"
        self._tree_signature_filter: Optional[str] = None
        self._allowed_record_keys: Optional[Set[Tuple[str, int]]] = None
        self._allowed_group_ids: Optional[Set[int]] = None
        self._last_search_records: List[Record] = []
        self._export_thread: Optional[ExportThread] = None
        self._export_worker: Optional[ExportWorker] = None
        self._export_progress: Optional[QProgressDialog] = None

        self._setup_models()
        self._setup_views()
        self._setup_actions()
        self._setup_tools_panel()
        self._setup_layout()
        self._setup_connections()
        self._restore_ui_state()

    def _setup_models(self) -> None:
        self.tree_model = QStandardItemModel(self)
        self.tree_model.setHorizontalHeaderLabels(["Node", "Type", "EDID", "Winner", "Losers", "Plugins"])
        self.detail_model = QStandardItemModel(self)
        self.detail_model.setHorizontalHeaderLabels(["Field", "Value"])
        self.structure_model = StructureItemModel(self)
        self.conflict_model = QStandardItemModel(self)
        self.conflict_model.setHorizontalHeaderLabels(["Record", "Winners", "Losers"])

    def _setup_views(self) -> None:
        self.tree_view = QTreeView(self)
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree_view.setAnimated(False)
        self.tree_view.setItemDelegate(StructureHighlightDelegate(self.tree_view))
        tree_header = self.tree_view.header()
        tree_header.setStretchLastSection(False)
        tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.detail_view = QTreeView(self)
        self.detail_view.setModel(self.detail_model)
        self.detail_view.setUniformRowHeights(True)
        self.detail_view.setAlternatingRowColors(True)
        self.detail_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.detail_view.setAnimated(False)
        self.detail_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.detail_view.customContextMenuRequested.connect(self._detail_context_menu)
        detail_header = self.detail_view.header()
        detail_header.setStretchLastSection(False)
        detail_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        detail_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)

    def _setup_actions(self) -> None:
        self.action_open = QAction("Open", self)
        self.action_open.setShortcut("Ctrl+O")
        self.action_open.triggered.connect(self._open_file)
        self.action_back = QAction("Back", self)
        self.action_back.setShortcut("Alt+Left")
        self.action_back.triggered.connect(self._navigate_back)
        self.action_forward = QAction("Forward", self)
        self.action_forward.setShortcut("Alt+Right")
        self.action_forward.triggered.connect(self._navigate_forward)
        self.action_find = QAction("Search", self)
        self.action_find.setShortcut("Ctrl+F")
        self.action_find.triggered.connect(self._focus_search)
        self.action_goto = QAction("Go to FormID", self)
        self.action_goto.setShortcut("Ctrl+G")
        self.action_goto.triggered.connect(self._goto_formid)
        self.action_copy = QAction("Copy", self)
        self.action_copy.setShortcut("Ctrl+C")
        self.action_copy.triggered.connect(self._copy_selected_value)
        self.action_next = QAction("Next", self)
        self.action_next.setShortcut("F3")
        self.action_next.triggered.connect(self._detail_search_next)
        self.action_prev = QAction("Prev", self)
        self.action_prev.setShortcut("Shift+F3")
        self.action_prev.triggered.connect(self._detail_search_prev)
        self.action_expand_all = QAction("Expand details", self)
        self.action_expand_all.setShortcut("Ctrl+Shift+E")
        self.action_expand_all.triggered.connect(self._expand_all_details)
        self.action_collapse_all = QAction("Collapse details", self)
        self.action_collapse_all.setShortcut("Ctrl+Shift+C")
        self.action_collapse_all.triggered.connect(self._collapse_all_details)
        self.action_export = QAction("Export", self)
        self.action_export.triggered.connect(self._open_export_dialog)
        self.action_export_all = QAction("Export all data", self)
        self.action_export_all.triggered.connect(self._export_all_data)
        self.action_tools_panel = QAction("Search", self)
        self.action_tools_panel.triggered.connect(self._show_tools_flyout)
        self.action_adv_search = QAction("Advanced search", self)
        self.action_adv_search.triggered.connect(self._focus_advanced_search)
        self.action_quick_filter = QAction("Quick filter", self)
        self.action_quick_filter.triggered.connect(self._focus_quick_filter)

    def _setup_tools_panel(self) -> None:
        self.tools_panel = ToolsPanel(self)
        self.tools_panel.search_requested.connect(self._on_advanced_search_requested)
        self.tools_panel.record_selected.connect(self._on_search_result_selected)
        self.tools_panel.conflict_filter_changed.connect(self._on_conflict_filter_changed)
        self.search_flyout = FlyoutPopup(self.tools_panel, self)
        self.search_flyout.closed.connect(self._on_flyout_closed)

    def _setup_layout(self) -> None:
        # Основной лейаут виджета
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Статус-бар (добавляем первым, чтобы MainWindow мог его использовать)
        self.status_bar = QStatusBar(self)
        self.status_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.status_bar.setFixedHeight(22) # Тонкий статус-бар

        # Тулбар
        self.search_widget = SearchWidget(self)
        self.search_widget.search_requested.connect(self._on_search_requested)
        self.search_widget.result_selected.connect(self._on_search_result_selected)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.addWidget(self.search_widget)
        self.toolbar.addAction(self.action_open)
        self.toolbar.addAction(self.action_back)
        self.toolbar.addAction(self.action_forward)
        self.toolbar.addAction(self.action_export)
        self.toolbar.addSeparator()

        self._conflict_only_box = QCheckBox("Conflicts only", self)
        self._conflict_hide_identical_box = QCheckBox("Hide identical", self)
        self._conflict_mode_combo = QComboBox(self)
        self._conflict_mode_combo.addItem("All", "all")
        self._conflict_mode_combo.addItem("Winners", "winning")
        self._conflict_mode_combo.addItem("Losers", "losing")
        self._conflict_mode_combo.currentIndexChanged.connect(self._on_conflict_mode_changed)
        self._conflict_only_box.toggled.connect(
            lambda checked: self._on_conflict_filter_changed(
                checked, bool(self._conflict_hide_identical_box.isChecked())
            )
        )
        self._conflict_hide_identical_box.toggled.connect(
            lambda checked: self._on_conflict_filter_changed(
                bool(self._conflict_only_box.isChecked()), checked
            )
        )
        self.toolbar.addWidget(self._conflict_only_box)
        self.toolbar.addWidget(self._conflict_hide_identical_box)
        self.toolbar.addWidget(self._conflict_mode_combo)

        self.tools_button = QToolButton(self)
        self.tools_button.setText("Search")
        self.tools_button.clicked.connect(lambda: self._toggle_flyout(self.search_flyout, self.tools_button))
        self.toolbar.addWidget(self.tools_button)

        self.main_layout.addWidget(self.toolbar)

        # Контент (сплиттеры и фильтры)
        detail_container = QWidget(self)
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        self.structure_view = QTreeView(self)
        self.structure_view.setModel(self.structure_model)
        self.structure_view.setUniformRowHeights(True)
        self.structure_view.setAlternatingRowColors(True)
        self.structure_view.setRootIsDecorated(True)
        self.structure_view.setItemDelegate(StructureHighlightDelegate(self.structure_view))
        structure_header = StructureHeaderView(Qt.Orientation.Horizontal, self.structure_view)
        self.structure_view.setHeader(structure_header)

        self.detail_tabs = QTabWidget(self)
        self.detail_tabs.addTab(self.detail_view, "Current plugin")
        self.detail_tabs.addTab(self.structure_view, "All plugins")

        self.conflict_view = QTreeView(self)
        self.conflict_view.setModel(self.conflict_model)
        self.conflict_view.setRootIsDecorated(False)
        self.conflict_view.setAlternatingRowColors(True)
        self.conflict_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.conflict_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.conflict_view.setVisible(False)

        self.bottom_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.bottom_splitter.addWidget(self.detail_tabs)
        self.bottom_splitter.addWidget(self.conflict_view)
        self.bottom_splitter.setStretchFactor(0, 1)
        self.bottom_splitter.setStretchFactor(1, 0)
        self.bottom_splitter.setChildrenCollapsible(False)
        detail_layout.addWidget(self.bottom_splitter)

        self.left_filter_box = QLineEdit(self)
        self.left_filter_box.setPlaceholderText("Filter left panel")
        self.right_filter_box = QLineEdit(self)
        self.right_filter_box.setPlaceholderText("Filter right panel")
        filter_panel = QWidget(self)
        filter_layout = QHBoxLayout(filter_panel)
        filter_layout.setContentsMargins(8, 6, 8, 6)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(self.left_filter_box, 1)
        filter_layout.addWidget(self.right_filter_box, 1)
        filter_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        filter_panel.setMaximumHeight(40)

        self.splitter = QSplitter(self)
        self.splitter.addWidget(self.tree_view)
        self.splitter.addWidget(detail_container)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)

        self.main_layout.addWidget(self.splitter)
        self.main_layout.addWidget(filter_panel)
        self.main_layout.addWidget(self.status_bar)

    def _setup_connections(self) -> None:
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(300)
        self._filter_timer.timeout.connect(self._apply_filter)
        self.left_filter_box.textChanged.connect(self._on_filter_text_changed)
        self._detail_filter_timer = QTimer(self)
        self._detail_filter_timer.setSingleShot(True)
        self._detail_filter_timer.setInterval(300)
        self._detail_filter_timer.timeout.connect(self._apply_detail_filter)
        self.right_filter_box.textChanged.connect(self._on_detail_filter_text_changed)
        self.tree_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.tree_view.clicked.connect(self._on_tree_activated)
        self.tree_view.expanded.connect(self._on_tree_expanded)
        self.detail_view.clicked.connect(self._on_detail_activated)
        self.conflict_view.clicked.connect(self._on_conflict_view_activated)

    def _apply_default_column_sizes(self) -> None:
        tree_header = self.tree_view.header()
        self.tree_view.resizeColumnToContents(1)
        self.tree_view.resizeColumnToContents(2)
        self.tree_view.setColumnWidth(0, max(280, tree_header.sectionSizeHint(0)))
        self.tree_view.resizeColumnToContents(3)
        self.tree_view.resizeColumnToContents(4)
        self.tree_view.setColumnWidth(5, 220)
        detail_header = self.detail_view.header()
        self.detail_view.resizeColumnToContents(0)
        self.detail_view.setColumnWidth(1, max(460, detail_header.sectionSizeHint(1)))
        self.structure_view.resizeColumnToContents(0)
        self.structure_view.setColumnWidth(0, max(300, self.structure_view.header().sectionSizeHint(0)))
        self.tools_panel.apply_search_default_sizes()

    def _restore_ui_state(self) -> None:
        self._settings.beginGroup("ui")
        splitter_state = self._settings.value("splitter", type=QByteArray)
        if splitter_state and not splitter_state.isEmpty():
            self.splitter.restoreState(splitter_state)
        for key, view in [
            ("tree_header", self.tree_view),
            ("detail_header", self.detail_view),
            ("structure_header", self.structure_view),
            ("conflict_header", self.conflict_view),
        ]:
            state = self._settings.value(key, type=QByteArray)
            if state and not state.isEmpty():
                view.header().restoreState(state)
        self._settings.endGroup()

    def _save_ui_state(self) -> None:
        self._settings.beginGroup("ui")
        self._settings.setValue("splitter", self.splitter.saveState())
        for key, view in [
            ("tree_header", self.tree_view),
            ("detail_header", self.detail_view),
            ("structure_header", self.structure_view),
            ("conflict_header", self.conflict_view),
        ]:
            self._settings.setValue(key, view.header().saveState())
        self._settings.endGroup()

    def _detail_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self.detail_view)
        index = self.detail_view.indexAt(pos)
        copy_cell = QAction("Copy cell", self)
        copy_cell.triggered.connect(lambda: self._detail_copy_cell(index))
        copy_cell.setEnabled(index.isValid())
        menu.addAction(copy_cell)
        copy_row = QAction("Copy row", self)
        copy_row.triggered.connect(lambda: self._detail_copy_row(index))
        copy_row.setEnabled(index.isValid())
        menu.addAction(copy_row)
        menu.addSeparator()
        copy_all = QAction("Copy all", self)
        copy_all.triggered.connect(self._detail_copy_all)
        copy_all.setEnabled(self.detail_model.rowCount() > 0)
        menu.addAction(copy_all)
        menu.exec(self.detail_view.viewport().mapToGlobal(pos))

    def _detail_copy_cell(self, index) -> None:
        if not index.isValid():
            return
        text = index.data()
        if text is not None:
            QApplication.clipboard().setText(str(text))

    def _detail_copy_row(self, index) -> None:
        if not index.isValid():
            return
        row_index = index.siblingAtColumn(0)
        name_item = self.detail_model.itemFromIndex(row_index)
        value_item = self.detail_model.itemFromIndex(index.siblingAtColumn(1))
        if name_item is None:
            return
        name = name_item.text() if name_item else ""
        value = value_item.text() if value_item else ""
        text = name + "\t" + value if value else name
        if text:
            QApplication.clipboard().setText(text)

    def _detail_copy_all(self) -> None:
        lines: List[str] = []
        def collect(item: QStandardItem, indent: int) -> None:
            if item is None:
                return
            row = item.row()
            parent = item.parent()
            if parent is None:
                name_item = self.detail_model.item(row, 0)
                value_item = self.detail_model.item(row, 1)
            else:
                name_item = parent.child(row, 0)
                value_item = parent.child(row, 1)
            prefix = "  " * indent
            name = name_item.text() if name_item else ""
            value = value_item.text() if value_item else ""
            if value:
                lines.append(prefix + name + "\t" + value)
            else:
                lines.append(prefix + name)
            if name_item and name_item.rowCount() > 0:
                for i in range(name_item.rowCount()):
                    collect(name_item.child(i, 0), indent + 1)
        root = self.detail_model.invisibleRootItem()
        for row in range(root.rowCount()):
            collect(root.child(row, 0), 0)
        if lines:
            QApplication.clipboard().setText("\n".join(lines))

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open plugin", "", "Plugins (*.esp *.esm *.esl)")
        if not path:
            return
        self.load_plugin(path)

    def _navigate_back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        sig, form_id = self._history[self._history_index]
        self._navigate_to_formid(sig, form_id, add_history=False)

    def _navigate_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        sig, form_id = self._history[self._history_index]
        self._navigate_to_formid(sig, form_id, add_history=False)

    def _focus_search(self) -> None:
        if self.detail_view.hasFocus():
            self._show_detail_search()
        else:
            self.search_widget.focus_input()

    def _show_detail_search(self) -> None:
        self.right_filter_box.setFocus()
        self.right_filter_box.selectAll()

    def _goto_formid(self) -> None:
        text, ok = QInputDialog.getText(self, "Go to FormID", "FormID (hex):")
        if not ok or not text:
            return
        value = text.strip().lower().replace("0x", "")
        try:
            form_id = int(value, 16)
        except ValueError:
            QMessageBox.warning(self, "Invalid FormID", "Invalid hex value")
            return
        self._navigate_to_formid(None, form_id)

    def _copy_selected_value(self) -> None:
        indexes = self.detail_view.selectedIndexes()
        if not indexes:
            return
        index = indexes[0]
        text = index.data()
        if text:
            QApplication.clipboard().setText(str(text))

    def _detail_search_next(self) -> None:
        if not self._detail_matches:
            return
        self._detail_match_index = (self._detail_match_index + 1) % len(self._detail_matches)
        item = self._detail_matches[self._detail_match_index]
        self._reveal_detail_item(item)

    def _detail_search_prev(self) -> None:
        if not self._detail_matches:
            return
        self._detail_match_index = (self._detail_match_index - 1) % len(self._detail_matches)
        item = self._detail_matches[self._detail_match_index]
        self._reveal_detail_item(item)

    def _reveal_detail_item(self, item: QStandardItem) -> None:
        index = item.index()
        if not index.isValid():
            return
        parent = index.parent()
        while parent.isValid():
            self.detail_view.expand(parent)
            parent = parent.parent()
        self.detail_view.setCurrentIndex(index)
        self.detail_view.scrollTo(index)

    def _expand_all_details(self) -> None:
        self.detail_view.expandAll()

    def _collapse_all_details(self) -> None:
        self.detail_view.collapseAll()

    def _open_export_dialog(self) -> None:
        if not self.current_plugin:
            QMessageBox.information(self, "Export", "Open a plugin first")
            return
        base_name = os.path.splitext(os.path.basename(self.current_plugin.path))[0]
        default_dir = os.path.dirname(self.current_plugin.path)
        dialog = ExportDialog(
            plugin=self.current_plugin,
            default_output_dir=default_dir,
            base_filename=base_name,
            resolve_full_name=self._resolve_full_name,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        config = dialog.build_config()
        if config is None:
            QMessageBox.warning(self, "Export", "Nothing to export: select formats and fields")
            return
        selected_records: Optional[List[Record]] = None
        selected_groups: Optional[List[Group]] = None
        if config.scope == "current_selection":
            selected_records, selected_groups = self._collect_records_from_selection()
        elif config.scope == "filtered":
            selected_records, selected_groups = self._collect_records_from_filters()
        elif config.scope == "search":
            selected_records = list(self._last_search_records)
            selected_groups = []
        if config.scope == "current_selection" and not (selected_records or selected_groups):
            QMessageBox.warning(self, "Export", "No selected records to export")
            return
        if config.scope == "filtered" and not (selected_records or selected_groups):
            QMessageBox.warning(self, "Export", "No filtered records to export")
            return
        if config.scope == "search" and not selected_records:
            QMessageBox.warning(self, "Export", "No search results to export")
            return
        config.selected_records = selected_records
        config.selected_groups = selected_groups
        self._start_export_thread(config)

    def _export_all_data(self) -> None:
        if not self.current_plugin:
            QMessageBox.information(self, "Export", "Open a plugin first")
            return
        base_name = os.path.splitext(os.path.basename(self.current_plugin.path))[0]
        default_dir = os.path.dirname(self.current_plugin.path)
        output_dir = QFileDialog.getExistingDirectory(self, "Export folder", default_dir)
        if not output_dir:
            return
        from esp_viewer.core.exporter2.formatters.json_formatter import JSONExportFormatter
        formatter = JSONExportFormatter()
        filename = f"{base_name}_all.{formatter.file_extension()}"
        path = os.path.join(output_dir, filename)
        formatter.export_full_plugin(path, self.current_plugin, self._resolve_full_name)
        QMessageBox.information(self, "Export", "Export completed")

    def _start_export_thread(self, config) -> None:
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.warning(self, "Export", "Export already running")
            return
        self._export_worker = ExportWorker(self.current_plugin, config, self._resolve_full_name)
        self._export_thread = ExportThread(self._export_worker)
        self._export_progress = QProgressDialog("Exporting...", "Cancel", 0, 0, self)
        self._export_progress.setWindowTitle("Export")
        self._export_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._export_progress.canceled.connect(self._cancel_export)
        def on_progress(current: int, total: int) -> None:
            if not self._export_progress:
                return
            if total > 0:
                if self._export_progress.maximum() != total:
                    self._export_progress.setMaximum(total)
                self._export_progress.setValue(current)
        def on_finished(result) -> None:
            if self._export_progress:
                self._export_progress.close()
            self._export_thread = None
            self._export_worker = None
            self._export_progress = None
            self._handle_export_result(result)
        self._export_worker.progress.connect(on_progress)
        self._export_worker.finished.connect(on_finished)
        self._export_thread.start()

    def _cancel_export(self) -> None:
        if self._export_worker:
            self._export_worker.cancel()

    def _handle_export_result(self, result) -> None:
        if result.clipboard_text:
            QApplication.clipboard().setText(result.clipboard_text)
        if not result.success:
            QMessageBox.critical(self, "Export", "Export finished with errors")
            return
        QMessageBox.information(self, "Export", "Export completed")

    def _collect_all_records(self) -> List[Record]:
        if not self.current_plugin:
            return []
        return list(iter_records(self.current_plugin.children))

    def _collect_all_groups(self) -> List[Group]:
        if not self.current_plugin:
            return []
        return list(iter_groups(self.current_plugin.children))

    def _collect_records_from_selection(self) -> Tuple[List[Record], List[Group]]:
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            return [], []
        index = indexes[0].siblingAtColumn(0)
        item = self.tree_model.itemFromIndex(index)
        if item is None:
            return [], []
        node = item.data(NODE_DATA_ROLE)
        if isinstance(node, Record):
            return [node], []
        if isinstance(node, Group):
            records = list(iter_records(node.children))
            groups = [node]
            groups.extend(list(iter_groups(node.children)))
            return records, groups
        if isinstance(node, PluginFile):
            return self._collect_all_records(), self._collect_all_groups()
        return [], []

    def _collect_records_from_filters(self) -> Tuple[List[Record], List[Group]]:
        if not self.current_plugin:
            return [], []
        signature_filter = self._tree_signature_filter
        allowed_keys = self._allowed_record_keys
        allowed_groups = self._allowed_group_ids
        records: List[Record] = []
        groups: List[Group] = []
        for record in iter_records(self.current_plugin.children):
            if signature_filter and record.signature != signature_filter:
                continue
            if allowed_keys and (record.signature, record.form_id) not in allowed_keys:
                continue
            records.append(record)
        for group in iter_groups(self.current_plugin.children):
            if signature_filter and not self._group_has_signature(group, signature_filter):
                continue
            if allowed_groups and id(group) not in allowed_groups:
                continue
            groups.append(group)
        return records, groups

    def _on_conflict_mode_changed(self, index: int) -> None:
        mode = self._conflict_mode_combo.itemData(index)
        self._on_conflict_filter_changed(self._conflict_filter_only, self._conflict_filter_hide_identical, mode)

    def _on_conflict_filter_changed(self, only_conflicts: bool, hide_identical: bool, mode: str = None) -> None:
        self._conflict_filter_only = only_conflicts
        self._conflict_filter_hide_identical = hide_identical
        if mode:
            self._conflict_filter_mode = mode
        self._apply_filters()

    def _on_filter_text_changed(self, text: str) -> None:
        self._filter_timer.start()

    def _apply_filter(self) -> None:
        self._apply_filters()

    def _on_detail_filter_text_changed(self, text: str) -> None:
        self._detail_filter_timer.start()

    def _apply_detail_filter(self) -> None:
        text = self.right_filter_box.text().strip().lower()
        self._detail_matches = []
        self._detail_match_index = -1
        if not text:
            self._set_detail_rows_visible(self.detail_model.invisibleRootItem())
            return
        self._filter_detail_rows(self.detail_model.invisibleRootItem(), text)
        if self._detail_matches:
            self._detail_search_next()

    def _set_detail_rows_visible(self, parent_item: QStandardItem) -> None:
        parent_index = parent_item.index()
        if not parent_index.isValid():
            parent_index = QModelIndex()
        for row in range(parent_item.rowCount()):
            self.detail_view.setRowHidden(row, parent_index, False)
            name_item = parent_item.child(row, 0)
            if name_item and name_item.hasChildren():
                self._set_detail_rows_visible(name_item)

    def _filter_detail_rows(self, parent_item: QStandardItem, needle: str) -> bool:
        parent_index = parent_item.index()
        if not parent_index.isValid():
            parent_index = QModelIndex()
        any_match = False
        for row in range(parent_item.rowCount()):
            name_item = parent_item.child(row, 0)
            value_item = parent_item.child(row, 1)
            row_match = False
            if name_item and needle in name_item.text().lower():
                row_match = True
                self._detail_matches.append(name_item)
            if value_item and needle in value_item.text().lower():
                row_match = True
                self._detail_matches.append(value_item)
            child_match = False
            if name_item and name_item.hasChildren():
                child_match = self._filter_detail_rows(name_item, needle)
            visible = row_match or child_match
            self.detail_view.setRowHidden(row, parent_index, not visible)
            if visible:
                any_match = True
        return any_match

    def _show_record(self, record: Record) -> None:
        self.detail_model.clear()
        self.detail_model.setHorizontalHeaderLabels(["Field", "Value"])
        parser = StructuredSubrecordParser(self.current_plugin, record)
        nodes = parser.parse()
        for node in nodes:
            self._add_detail_node(self.detail_model.invisibleRootItem(), node)
        self.detail_view.expandAll()
        self.detail_view.resizeColumnToContents(0)
        if self._structure_thread and self._structure_thread.isRunning():
            self._structure_thread.quit()
            self._structure_thread.wait()
        self._structure_thread = RecordStructureLoaderThread(
            record.signature, record.form_id, self._load_order, self._plugin_cache
        )
        def on_structure_loaded(model_data, headers):
            self.structure_model.set_data(model_data, headers)
            self.structure_view.expandAll()
            self.structure_view.resizeColumnToContents(0)
        self._structure_thread.finished.connect(on_structure_loaded)
        self._structure_thread.start()

    def _add_detail_node(self, parent_item: QStandardItem, node: DetailNode) -> None:
        name_item = QStandardItem(node.name)
        name_item.setEditable(False)
        value_item = QStandardItem(node.value if node.value is not None else "")
        value_item.setEditable(False)
        if node.form_id is not None:
            name_item.setData((node.signature, node.form_id), DETAIL_REF_ROLE)
            value_item.setForeground(QBrush(QColor("#3498db")))
        parent_item.appendRow([name_item, value_item])
        for child in node.children:
            self._add_detail_node(name_item, child)

    def _populate_group(self, parent_item: QStandardItem, group: Group) -> None:
        for child in group.children:
            if isinstance(child, Group):
                child_item = QStandardItem(format_group_label(child))
                child_item.setData(child, NODE_DATA_ROLE)
                child_item.setData(True, LAZY_ROLE)
                parent_item.appendRow([child_item, QStandardItem(group_type_label(child))])
                self._group_index[id(child)] = child_item
            elif isinstance(child, Record):
                self._add_record_row(parent_item, child)

    def _add_record_row(self, parent_item: QStandardItem, record: Record) -> None:
        label = format_record_identity(record, self.current_plugin, self._resolve_full_name)
        item = QStandardItem(label)
        item.setData(record, NODE_DATA_ROLE)
        sig_item = QStandardItem(record.signature)
        edid = extract_string_field(record, b"EDID")
        edid_item = QStandardItem(edid if edid else "")
        status = self._conflict_statuses.get((record.signature, record.form_id), ConflictStatus.NoConflict)
        winner_item = QStandardItem()
        losers_item = QStandardItem()
        plugins_item = QStandardItem()
        if status != ConflictStatus.NoConflict:
            details = self._conflict_details.get((record.signature, record.form_id))
            if details:
                winner_item.setText(details.winner if hasattr(details, "winner") else "")
                losers_item.setText(", ".join(details.losers) if hasattr(details, "losers") else "")
                plugins_item.setText(", ".join(details.plugins) if hasattr(details, "plugins") else "")
        parent_item.appendRow([item, sig_item, edid_item, winner_item, losers_item, plugins_item])
        self._record_index[(record.signature, record.form_id)] = item

    def _apply_filters(self) -> None:
        if not self.current_plugin:
            return
        signature_filter: Optional[str] = None
        left_text = self.left_filter_box.text().strip()
        allowed_keys: Optional[Set[Tuple[str, int]]] = None
        allowed_groups: Optional[Set[int]] = None
        if left_text:
            allowed_keys, allowed_groups = self._collect_left_filter_matches(
                self.current_plugin,
                left_text,
            )
        if self._quick_filter_text:
            if self._quick_filter_mode == "Signature":
                signature_filter = self._quick_filter_text.upper()
            else:
                quick_keys, quick_groups = self._collect_left_filter_matches(
                    self.current_plugin,
                    self._quick_filter_text,
                )
                if allowed_keys is None:
                    allowed_keys = quick_keys
                else:
                    allowed_keys &= quick_keys
                if allowed_groups is None:
                    allowed_groups = quick_groups
                else:
                    allowed_groups &= quick_groups
        self._tree_signature_filter = signature_filter
        if self._conflict_filter_only or self._conflict_filter_hide_identical:
            conflict_keys = self._collect_conflict_keys()
            if self._conflict_filter_only:
                filtered_conflict_keys: Set[Tuple[str, int]] = set()
                for key in conflict_keys:
                    status = self._conflict_statuses.get(key, ConflictStatus.NOT_DEFINED)
                    if not is_conflict_status(status):
                        continue

                    if self._conflict_filter_mode == "winning":
                        if not is_winning_status(status):
                            continue
                    elif self._conflict_filter_mode == "losing":
                        if not is_losing_status(status):
                            continue

                    filtered_conflict_keys.add(key)
                conflict_keys = filtered_conflict_keys
            if self._conflict_filter_hide_identical:
                conflict_keys = {
                    key for key in conflict_keys
                    if self._conflict_statuses.get(key) != ConflictStatus.IDENTICAL_TO_MASTER
                }
            if allowed_keys is None:
                allowed_keys = conflict_keys
            else:
                allowed_keys &= conflict_keys
        if allowed_keys is not None:
            conflict_groups = self._collect_group_ids_for_records(self.current_plugin, allowed_keys)
            if allowed_groups is None:
                allowed_groups = conflict_groups
            else:
                allowed_groups &= conflict_groups
        self._populate_tree(self.current_plugin, signature_filter, allowed_keys, allowed_groups)

    def _collect_conflict_keys(self) -> Set[Tuple[str, int]]:
        if not self._conflict_statuses:
            return set()
        return set(self._conflict_statuses.keys())

    def _collect_group_ids_for_records(
        self,
        plugin: PluginFile,
        allowed_records: Set[Tuple[str, int]],
    ) -> Set[int]:
        group_ids: Set[int] = set()

        def visit(node: Union[Group, Record]) -> bool:
            if isinstance(node, Record):
                return (node.signature, node.form_id) in allowed_records
            if isinstance(node, Group):
                has_match = False
                for child in node.children:
                    if visit(child):
                        has_match = True
                if has_match:
                    group_ids.add(id(node))
                return has_match
            return False

        for child in plugin.children:
            visit(child)
        return group_ids

    def _sync_conflict_controls(self, only_conflicts: bool, hide_identical: bool) -> None:
        if self._conflict_only_box and self._conflict_only_box.isChecked() != only_conflicts:
            self._conflict_only_box.blockSignals(True)
            self._conflict_only_box.setChecked(only_conflicts)
            self._conflict_only_box.blockSignals(False)
        if self._conflict_hide_identical_box and self._conflict_hide_identical_box.isChecked() != hide_identical:
            self._conflict_hide_identical_box.blockSignals(True)
            self._conflict_hide_identical_box.setChecked(hide_identical)
            self._conflict_hide_identical_box.blockSignals(False)
        if self.tools_panel:
            self.tools_panel.set_conflict_filters(only_conflicts, hide_identical)

    def _update_conflict_summary(self) -> None:
        self.conflict_model.removeRows(0, self.conflict_model.rowCount())
        if not self.current_plugin or not self._conflict_details:
            self.conflict_view.setVisible(False)
            return

        current_name = os.path.basename(self.current_plugin.path)
        rows: List[List[QStandardItem]] = []

        for (signature, form_id), info in self._conflict_details.items():
            status = info.status
            if not is_conflict_status(status):
                continue

            record_label = f"{signature} 0x{form_id:08X}"
            chain_plugins = [name for name in info.chain_plugins if name]
            other_plugins = [name for name in chain_plugins if name != current_name]

            winners_text = "-"
            losers_text = "-"

            if is_winning_status(status) and other_plugins:
                losers_text = ", ".join(other_plugins)

            if is_losing_status(status) and info.winning_plugin:
                winners_text = info.winning_plugin

            # Добавляем в модель только если есть реальные конфликты
            if winners_text != "-" or losers_text != "-":
                record_item = QStandardItem(record_label)
                record_item.setData((signature, form_id), Qt.ItemDataRole.UserRole)

                rows.append([
                    record_item,
                    QStandardItem(winners_text),
                    QStandardItem(losers_text),
                ])

        for row in rows:
            self.conflict_model.appendRow(row)

        has_any = bool(rows)
        self.conflict_view.setVisible(has_any)
        if has_any:
            # Only resize if no saved state exists
            self._settings.beginGroup("ui")
            has_state = self._settings.contains("conflict_header") or self._settings.contains("conflict_header_widths")

            if not has_state:
                self.conflict_view.resizeColumnToContents(0)
                self.conflict_view.resizeColumnToContents(1)
            else:
                # Restore saved state
                state = self._settings.value("conflict_header", type=QByteArray)
                if state and not state.isEmpty():
                    self.conflict_view.header().restoreState(state)
                widths = self._settings.value("conflict_header_widths")
                if widths:
                    for i, w in enumerate(widths):
                        try:
                            self.conflict_view.setColumnWidth(i, int(w))
                        except: continue
            self._settings.endGroup()

    def _collect_left_filter_matches(
        self,
        plugin: PluginFile,
        text: str,
    ) -> Tuple[Set[Tuple[str, int]], Set[int]]:
        needle = text.strip().lower()
        allowed_records: Set[Tuple[str, int]] = set()
        allowed_groups: Set[int] = set()
        if not needle:
            return allowed_records, allowed_groups
        for record in iter_records(plugin.children):
            if self._left_filter_matches_record(record, plugin, needle):
                allowed_records.add((record.signature, record.form_id))
        for group in iter_groups(plugin.children):
            if self._left_filter_matches_group(group, plugin, needle):
                allowed_groups.add(id(group))
        return allowed_records, allowed_groups

    def _left_filter_matches_record(
        self,
        record: Record,
        plugin: Optional[PluginFile],
        needle: str,
    ) -> bool:
        values: List[str] = [record.signature]
        if record.editor_id:
            values.append(record.editor_id)
        full = self._resolve_full_name(record)
        if full:
            values.append(full)
        values.append(f"{record.form_id:08X}")
        values.append(f"0x{record.form_id:08X}")
        if plugin and plugin.formid_resolver:
            values.append(plugin.formid_resolver.format_formid(record.form_id, record.signature))
        type_text = RECORD_SIGNATURE_TYPES.get(record.signature, record.signature)
        if type_text != record.signature:
            values.append(f"{record.signature} - {type_text}")
        else:
            values.append(type_text)
        values.append(format_record_identity(record, plugin, self._resolve_full_name))
        for value in values:
            if needle in value.lower():
                return True
        return False

    def _left_filter_matches_group(
        self,
        group: Group,
        plugin: Optional[PluginFile],
        needle: str,
    ) -> bool:
        values: List[str] = [format_group_label(group, plugin), group_type_label(group)]
        if group.group_type == 0:
            sig = group.label_raw.decode("ascii", errors="replace").rstrip("\x00")
            values.append(sig)
        for value in values:
            if needle in value.lower():
                return True
        return False

    def load_plugin(self, path: str) -> None:
        progress = QProgressDialog("Loading plugin...", None, 0, 0, self)
        progress.setWindowTitle("Loading")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        if self._loader_thread and self._loader_thread.isRunning():
            self._loader_thread.quit()
            self._loader_thread.wait()

        self._conflict_pending = True
        self._loader_thread = PluginLoaderThread(path, self)

        def finish(
            plugin: PluginFile,
            record_paths: Dict[Tuple[str, int], List[Group]],
            conflicts: Optional[ConflictAnalysisResult],
        ) -> None:
            progress.close()
            self.current_plugin = plugin
            self._record_paths = record_paths
            self._conflict_pending = False
            self._conflict_statuses = conflicts.statuses if conflicts else {}
            self._conflict_details = conflicts.details if conflicts else {}
            self._load_order = conflicts.load_order if conflicts else []
            self._update_conflict_summary()
            self._apply_filters()
            if conflicts:
                self.status_bar.showMessage(
                    f"Loaded {os.path.basename(path)} (conflicts analyzed)")
            else:
                self.status_bar.showMessage(f"Loaded {os.path.basename(path)}")

        def fail(message: str) -> None:
            progress.close()
            self._conflict_pending = False
            QMessageBox.critical(self, "Load error", message)

        self._loader_thread.finished.connect(finish)
        self._loader_thread.error.connect(fail)
        self._loader_thread.start()

    def _populate_tree(
        self,
        plugin: PluginFile,
        signature_filter: Optional[str],
        allowed_keys: Optional[Set[Tuple[str, int]]],
        allowed_groups: Optional[Set[int]],
    ) -> None:
        # Save current state before clearing, so user's manual adjustments are preserved
        self._save_ui_state()

        self.tree_model.removeRows(0, self.tree_model.rowCount())
        self.detail_model.removeRows(0, self.detail_model.rowCount())
        self._record_index.clear()
        self._group_index.clear()
        self._record_paths = self._record_paths or {}
        self._history.clear()
        self._history_index = -1
        self._allowed_record_keys = allowed_keys
        self._allowed_group_ids = allowed_groups

        file_label = os.path.basename(plugin.path)
        if plugin.is_esl:
            file_label = "🧩 " + file_label
        file_item = self._make_item(file_label, plugin)
        type_item = self._make_readonly("File")
        size_item = self._make_readonly(format_file_size(plugin.file_size))
        winner_item = self._make_readonly("")
        losers_item = self._make_readonly("")
        chain_item = self._make_readonly("")
        self.tree_model.appendRow([file_item, type_item, size_item, winner_item, losers_item, chain_item])

        def top_sort_key(node: Union[Group, Record]) -> Tuple[int, int, str]:
            if isinstance(node, Group):
                if node.group_type == 0:
                    sig = node.label_raw.decode("ascii", errors="replace").rstrip("\x00")
                    return (0, 0, sig)
                label = format_group_label(node, plugin)
                return (0, 1, label)
            if isinstance(node, Record):
                if node.signature == "TES4" and node.form_id == 0:
                    return (2, 0, "")
                return (1, node.form_id, (node.editor_id or "").lower())
            return (3, 0, "")

        for child in sorted(plugin.children, key=top_sort_key):
            if isinstance(child, Record) and child.signature == "TES4" and child.form_id == 0:
                continue
            if signature_filter and isinstance(child, Group):
                if not self._group_has_signature(child, signature_filter):
                    continue
            if (allowed_keys or allowed_groups) and isinstance(child, Group):
                if not self._group_has_matches(child, allowed_keys, allowed_groups):
                    continue
            self._add_node(file_item, child, plugin, signature_filter, allowed_keys, allowed_groups)

        if not self._record_paths:
            self._build_record_paths(plugin)
        self.tree_view.expandToDepth(0)

        # Restore tree header state/widths after population
        self._settings.beginGroup("ui")
        tree_state = self._settings.value("tree_header", type=QByteArray)
        if tree_state and not tree_state.isEmpty():
            self.tree_view.header().restoreState(tree_state)
        tree_widths = self._settings.value("tree_header_widths")
        if tree_widths:
            for i, w in enumerate(tree_widths):
                try:
                    self.tree_view.setColumnWidth(i, int(w))
                except (ValueError, TypeError):
                    continue
        self._settings.endGroup()

    def _group_has_signature(self, group: Group, signature: str) -> bool:
        for child in group.children:
            if isinstance(child, Record) and child.signature == signature:
                return True
            if isinstance(child, Group) and self._group_has_signature(child, signature):
                return True
        return False

    def _group_has_matches(
        self,
        group: Group,
        allowed_records: Optional[Set[Tuple[str, int]]],
        allowed_groups: Optional[Set[int]],
    ) -> bool:
        if allowed_groups and id(group) in allowed_groups:
            return True
        for child in group.children:
            if isinstance(child, Record):
                if allowed_records and (child.signature, child.form_id) in allowed_records:
                    return True
            elif isinstance(child, Group):
                if self._group_has_matches(child, allowed_records, allowed_groups):
                    return True
        return False

    def _add_node(
        self,
        parent: QStandardItem,
        node: Union[Group, Record],
        plugin: Optional[PluginFile],
        signature_filter: Optional[str],
        allowed_keys: Optional[Set[Tuple[str, int]]],
        allowed_groups: Optional[Set[int]],
    ) -> None:
        if isinstance(node, Group):
            label = format_group_label(node, plugin)
            item0 = self._make_item(label, node)
            type_item = self._make_readonly(group_type_label(node))
            id_item = self._make_readonly("")
            self._group_index[id(node)] = item0
            parent.appendRow([
                item0,
                type_item,
                id_item,
                self._make_readonly(""),
                self._make_readonly(""),
                self._make_readonly("")
            ])
            if node.children:
                if node.group_type in {2, 3, 4, 5, 6}:
                    for child in sorted(node.children, key=self._child_sort_key):
                        if signature_filter and isinstance(child, Group):
                            if not self._group_has_signature(child, signature_filter):
                                continue
                        if (allowed_keys or allowed_groups) and isinstance(child, Group):
                            if not self._group_has_matches(child, allowed_keys, allowed_groups):
                                continue
                        self._add_node(
                            item0,
                            child,
                            plugin,
                            signature_filter,
                            allowed_keys,
                            allowed_groups,
                        )
                else:
                    item0.setData(True, LAZY_ROLE)
                    placeholder = self._make_readonly("Loading...")
                    item0.appendRow([
                        placeholder,
                        self._make_readonly(""),
                        self._make_readonly(""),
                        self._make_readonly(""),
                        self._make_readonly(""),
                        self._make_readonly("")
                    ])
            return

        if isinstance(node, Record):
            sig = node.signature
            if signature_filter and sig != signature_filter:
                return
            if allowed_keys and (node.signature, node.form_id) not in allowed_keys:
                return
            display_text = sig
            if sig in {"WRLD", "CELL"}:
                name_parts: List[str] = []
                if node.editor_id:
                    name_parts.append(node.editor_id)
                full = self._resolve_full_name(node)
                if full:
                    name_parts.append(f'"{full}"')
                suffix = " ".join(name_parts)
                formid_str = ""
                if plugin and plugin.formid_resolver:
                    formid_str = f" {plugin.formid_resolver.format_formid(node.form_id, sig)}"
                label = "Worldspace" if sig == "WRLD" else "Cell"
                display_text = f"{label}: {suffix}{formid_str}" if suffix else f"{label}{formid_str}"
            else:
                display_text = format_record_identity(node, plugin, self._resolve_full_name)

            flags = node.flags
            state_prefix = ""
            if flags & 0x00000020:
                state_prefix = "DELETED "
            elif flags & 0x00001000:
                state_prefix = "IGNORED "
            display_text = f"{state_prefix}{display_text}" if state_prefix else display_text

            item0 = self._make_item(display_text, node)
            key = (node.signature, node.form_id)
            self._record_index[key] = item0

            if node.is_compressed:
                item0.setText("🗜 " + item0.text())
            if node.signature == "TES4" and node.form_id == 0:
                type_text = "TES4 - File Header"
            else:
                type_text = RECORD_SIGNATURE_TYPES.get(node.signature, node.signature)
                if type_text != node.signature:
                    type_text = f"{node.signature} - {type_text}"
            type_item = self._make_readonly(type_text)
            edid_text = node.editor_id if node.editor_id else ""
            id_item = self._make_readonly(edid_text)
            info = self._conflict_details.get(key)
            if info is not None:
                winner_text = info.winning_plugin or ""
                chain_plugins = [name for name in info.chain_plugins if name]
                losers = [p for p in chain_plugins if p != info.winning_plugin]
                losers_text = ", ".join(losers)
                chain_text = " \u00bb ".join(chain_plugins) if chain_plugins else ""
            else:
                winner_text = ""
                losers_text = ""
                chain_text = ""
            winner_item = self._make_readonly(winner_text)
            losers_item = self._make_readonly(losers_text)
            chain_item = self._make_readonly(chain_text)
            status = self._conflict_statuses.get(key)
            if status is not None:
                self._apply_conflict_color(item0, type_item, id_item, status)
            parent.appendRow([item0, type_item, id_item, winner_item, losers_item, chain_item])

    def _apply_conflict_color(
        self,
        item0: QStandardItem,
        type_item: QStandardItem,
        id_item: QStandardItem,
        status: ConflictStatus,
    ) -> None:
        brush = self._status_brush(status)
        if brush is None:
            return
        item0.setBackground(brush)
        type_item.setBackground(brush)
        id_item.setBackground(brush)
        if status in (ConflictStatus.HIDDEN_BY_MOD_GROUP, ConflictStatus.MASTER):
            text_color = QBrush(QColor(255, 255, 255))
            item0.setForeground(text_color)
            type_item.setForeground(text_color)
            id_item.setForeground(text_color)

    def _status_brush(self, status: ConflictStatus) -> Optional[QBrush]:
        gray = QColor(64, 64, 64)
        green = QColor(0, 140, 0)
        red = QColor(180, 32, 32)
        orange = QColor(200, 120, 32)
        colors: Dict[ConflictStatus, QColor] = {
            ConflictStatus.IDENTICAL_TO_MASTER: None,
            ConflictStatus.ONLY_ONE: None,
            ConflictStatus.HIDDEN_BY_MOD_GROUP: gray,
            ConflictStatus.MASTER: gray,
            ConflictStatus.CONFLICT_BENIGN: orange,
            ConflictStatus.OVERRIDE: green,
            ConflictStatus.IDENTICAL_TO_MASTER_WINS_CONFLICT: green,
            ConflictStatus.CONFLICT_LOSES: red,
            ConflictStatus.CONFLICT_CRITICAL: red,
        }
        color = colors.get(status)
        if color is None:
            return None
        return QBrush(color)

    def _on_tree_expanded(self, index) -> None:
        item = self.tree_model.itemFromIndex(index.siblingAtColumn(0))
        if item is None:
            return
        if not item.data(LAZY_ROLE):
            return
        node = item.data(NODE_DATA_ROLE)
        if not isinstance(node, Group):
            return
        item.setData(False, LAZY_ROLE)
        item.removeRows(0, item.rowCount())

        signature_filter = self._tree_signature_filter
        for child in sorted(node.children, key=self._child_sort_key):
            if signature_filter and isinstance(child, Group):
                if not self._group_has_signature(child, signature_filter):
                    continue
            if (self._allowed_record_keys or self._allowed_group_ids) and isinstance(child, Group):
                if not self._group_has_matches(child, self._allowed_record_keys, self._allowed_group_ids):
                    continue
            self._add_node(
                item,
                child,
                self.current_plugin,
                signature_filter,
                self._allowed_record_keys,
                self._allowed_group_ids,
            )

    def _build_record_paths(self, plugin: PluginFile) -> None:
        def visit(nodes: List[Union[Group, Record]], path: List[Group]) -> None:
            for node in nodes:
                if isinstance(node, Group):
                    visit(node.children, path + [node])
                elif isinstance(node, Record):
                    self._record_paths[(node.signature, node.form_id)] = path

        visit(plugin.children, [])

    def _make_readonly(self, text: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        return item

    def _make_item(self, text: str, node: Union[Group, Record, PluginFile]) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        item.setData(node, NODE_DATA_ROLE)
        if isinstance(node, Record):
            item.setData([(node.signature, node.form_id)], TREE_REF_ROLE)
        return item

    def _child_sort_key(self, child: Union[Group, Record]) -> Tuple[int, int, str]:
        if isinstance(child, Record):
            editor = (child.editor_id or "").lower()
            return (0, child.form_id, editor)
        if child.group_type == 0:
            sig = child.label_raw.decode("ascii", errors="replace").rstrip("\x00")
            return (1, 0, sig)
        label = format_group_label(child, self.current_plugin)
        return (1, child.group_type, label)

    def _build_structure_tree(self, nodes: List[DetailNode]) -> List[Dict[str, object]]:
        def visit_list(source_nodes: List[DetailNode]) -> List[Dict[str, object]]:
            result: List[Dict[str, object]] = []
            counts: Dict[str, int] = {}
            for node in source_nodes:
                index = counts.get(node.name, 0)
                counts[node.name] = index + 1
                key = (node.name, index)
                result.append(
                    {
                        "key": key,
                        "name": node.name,
                        "children": visit_list(node.children),
                    }
                )
            return result

        return visit_list(nodes)

    def _merge_structure_tree(self, base: List[Dict[str, object]], extra: List[Dict[str, object]]) -> None:
        if not extra:
            return

        # Создаем карту существующих узлов для быстрого поиска O(1)
        base_map = {node["key"]: node for node in base if "key" in node}

        for node in extra:
            node_key = node.get("key")
            if node_key is None: continue

            match = base_map.get(node_key)
            if match is None:
                # Копируем узел, чтобы не модифицировать оригинал в кэше
                new_node = {
                    "key": node["key"],
                    "name": node["name"],
                    "children": list(node.get("children", []))
                }
                base.append(new_node)
                base_map[node_key] = new_node
            else:
                extra_children = node.get("children")
                if extra_children:
                    if "children" not in match or not isinstance(match["children"], list):
                        match["children"] = []
                    self._merge_structure_tree(
                        match["children"],
                        extra_children,
                    )

    def _build_structure_value_map(self, nodes: List[DetailNode]) -> Dict[Tuple[Tuple[str, int], ...], str]:
        value_map: Dict[Tuple[Tuple[str, int], ...], str] = {}

        def visit_list(source_nodes: List[DetailNode], path: Tuple[Tuple[str, int], ...]) -> None:
            counts: Dict[str, int] = {}
            for node in source_nodes:
                index = counts.get(node.name, 0)
                counts[node.name] = index + 1
                key = (node.name, index)
                node_path = path + (key,)
                value_map[node_path] = node.value
                visit_list(node.children, node_path)

        visit_list(nodes, ())
        return value_map

    def _load_chain_plugin(self, path: str) -> Optional[PluginFile]:
        if not self.current_plugin:
            return None

        # Если это текущий плагин (по пути или по имени), возвращаем его
        current_path = os.path.normpath(self.current_plugin.path).lower()
        norm_path = os.path.normpath(path).lower()
        if norm_path == current_path or os.path.basename(norm_path) == os.path.basename(current_path):
            if not hasattr(self.current_plugin, 'record_map') or not self.current_plugin.record_map:
                self._ensure_record_map(self.current_plugin)
            return self.current_plugin

        cached = self._plugin_cache.get(path)
        if cached is not None:
            return cached

        # Пытаемся найти файл, если путь не абсолютный или не существует
        actual_path = path
        if not os.path.isabs(path) or not os.path.exists(path):
            plugin_name = os.path.basename(path)
            alt_path = os.path.join(os.path.dirname(self.current_plugin.path), plugin_name)
            if os.path.exists(alt_path):
                actual_path = alt_path
            else:
                found_in_cache = False
                for p in self._plugin_cache.values():
                    if os.path.basename(p.path).lower() == plugin_name.lower():
                        actual_path = p.path
                        found_in_cache = True
                        break

                if not found_in_cache:
                    logger.warning(f"Could not find plugin file: {path}")
                    return None

        # Проверяем кэш индексов
        lazy_index = self._lazy_index_cache.get(actual_path)
        if not lazy_index:
            try:
                lazy_index = create_lazy_index(actual_path)
                self._lazy_index_cache[actual_path] = lazy_index
            except Exception:
                logger.exception(f"Failed to create lazy index for: {actual_path}")
                return None

        # Создаем скелет PluginFile
        strings = StringTables()
        if lazy_index.localized:
            try:
                strings = load_string_tables(actual_path)
            except Exception:
                logger.warning(f"Failed to load strings for: {actual_path}")

        plugin = PluginFile(
            path=actual_path,
            file_size=lazy_index.file_size,
            header_size=lazy_index.header_size,
            localized=lazy_index.localized,
            strings=strings,
            children=[],
            masters=lazy_index.masters,
            lazy_index=lazy_index
        )
        plugin.formid_resolver = FormIDResolver(plugin)

        self._plugin_cache[path] = plugin
        if actual_path != path:
            self._plugin_cache[actual_path] = plugin
        return plugin

    def _ensure_record_map(self, plugin: PluginFile) -> None:
        """Гарантирует наличие record_map у плагина для быстрого поиска."""
        record_map = {}

        def iter_records_local(nodes):
            for node in nodes:
                if isinstance(node, Record):
                    record_map[(node.signature, node.form_id)] = node
                elif isinstance(node, Group):
                    iter_records_local(node.children)

        iter_records_local(plugin.children)
        plugin.record_map = record_map

    def _show_record_structure(self, record: Record) -> None:
        if self.current_plugin is None:
            self.structure_model.set_data([], [], [], -1)
            return

        key = (record.signature, record.form_id)
        info = self._conflict_details.get(key)
        chain_plugins = list(info.chain_plugins) if info and info.chain_plugins else []
        chain_paths = list(info.chain_paths) if info and hasattr(info, 'chain_paths') and info.chain_paths else []

        if not chain_plugins:
            # Если нет цепочки конфликтов, показываем только текущий плагин
            # Это можно сделать синхронно, так как это быстро
            current_name = os.path.basename(self.current_plugin.path)

            parser = StructuredSubrecordParser(record, self.current_plugin)
            nodes = list(parser.iter_nodes())
            tree = self._build_structure_tree(nodes)
            val_map = self._build_structure_value_map(nodes)

            self._display_structure_data([tree], [val_map], [current_name], 0)
            return

        # Если есть цепочка, загружаем асинхронно
        if self._structure_thread and self._structure_thread.isRunning():
            self._structure_thread.cancel()
            self._structure_thread.wait()

        self.status_bar.showMessage(f"Loading structure for {record.signature} {record.form_id:08X}...")

        self._structure_thread = RecordStructureLoaderThread(
            record, chain_plugins, chain_paths, 
            self._plugin_cache, self._lazy_index_cache, self.current_plugin,
            self._load_order
        )
        self._structure_thread.finished.connect(lambda trees, maps, plugins, winner: self._on_structure_loaded(trees, maps, plugins, winner, info))
        self._structure_thread.error.connect(self._on_structure_error)
        self._structure_thread.start()

    def _on_structure_loaded(self, structure_trees, value_maps, plugins, winner_index, info) -> None:
        self.status_bar.clearMessage()

        # Пересчитываем winner_index на основе info.winning_plugin, если он есть
        actual_winner_index = winner_index
        if info and info.winning_plugin:
            winning_name_lower = info.winning_plugin.lower()
            try:
                # plugins содержит базовые имена файлов
                for i, p in enumerate(plugins):
                    if p.lower() == winning_name_lower:
                        actual_winner_index = i
                        break
            except Exception:
                pass

        self._display_structure_data(structure_trees, value_maps, plugins, actual_winner_index)

    def _on_structure_error(self, message: str) -> None:
        self.status_bar.showMessage(f"Error loading structure: {message}", 5000)

    def _display_structure_data(self, structure_trees, value_maps, plugins, winner_index) -> None:
        self.structure_view.setUpdatesEnabled(False)
        try:
            # Слияние деревьев
            merged_tree: List[Dict[str, object]] = []
            for tree in structure_trees:
                if not tree: continue
                self._merge_structure_tree(merged_tree, tree)

            # Установка данных в кастомную модель
            self.structure_model.set_data(merged_tree, value_maps, plugins, winner_index)

            # Подсвечиваем заголовок текущего плагина
            header = self.structure_view.header()
            if isinstance(header, StructureHeaderView) and self.current_plugin:
                current_name = os.path.basename(self.current_plugin.path).lower()
                try:
                    current_col = [p.lower() for p in plugins].index(current_name)
                    # +1 потому что первая колонка это "Field"
                    header.set_highlight_column(current_col + 1)
                except ValueError:
                    header.set_highlight_column(-1)

            self.structure_view.expandToDepth(1)
        finally:
            self.structure_view.setUpdatesEnabled(True)
            self.structure_view.viewport().update()

    def _on_selection_changed(self) -> None:
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            return

        # Save state before clearing models
        self._save_ui_state()

        index = indexes[0].siblingAtColumn(0)
        item = self.tree_model.itemFromIndex(index)
        if item is None:
            return
        node = item.data(NODE_DATA_ROLE)
        self.detail_model.removeRows(0, self.detail_model.rowCount())
        self.structure_model.removeRows(0, self.structure_model.rowCount())

        if isinstance(node, PluginFile):
            self._show_plugin_details(node)
        elif isinstance(node, Group):
            self._show_group_details(node)
        elif isinstance(node, Record):
            self._show_record_details(node)
            self._show_record_structure(node)
        self.detail_view.expandToDepth(1)
        self._apply_detail_filter()

        # Restore header states after population
        self._settings.beginGroup("ui")
        for key, view in [
            ("detail_header", self.detail_view),
            ("structure_header", self.structure_view),
        ]:
            state = self._settings.value(key, type=QByteArray)
            if state and not state.isEmpty():
                view.header().restoreState(state)
            widths = self._settings.value(f"{key}_widths")
            if widths:
                for i, w in enumerate(widths):
                    try: view.setColumnWidth(i, int(w))
                    except: continue
        self._settings.endGroup()

    def _detail_tooltip(self, refs: List[Tuple[Optional[str], int]]) -> Optional[str]:
        if not refs:
            return None
        sig, form_id = refs[0]
        resolver = self.current_plugin.formid_resolver if self.current_plugin else None
        if resolver:
            return resolver.describe(form_id, sig)
        return f"0x{form_id:08X}"

    def _add_detail(
        self,
        name: str,
        value: str,
        refs: Optional[List[Tuple[str, int]]] = None,
        parent: Optional[QStandardItem] = None,
    ) -> QStandardItem:
        name_item = QStandardItem(name)
        name_item.setEditable(False)
        value_item = QStandardItem(value)
        value_item.setEditable(False)
        if refs:
            value_item.setData(refs, DETAIL_REF_ROLE)
            palette = self.detail_view.palette()
            value_item.setForeground(palette.color(QPalette.ColorRole.Link))
            font = value_item.font()
            font.setUnderline(True)
            value_item.setFont(font)
            tooltip = self._detail_tooltip(refs)
            if tooltip:
                value_item.setToolTip(tooltip)
        if parent is None:
            self.detail_model.appendRow([name_item, value_item])
        else:
            parent.appendRow([name_item, value_item])
        return name_item

    def _append_detail_node(self, node: DetailNode, parent: Optional[QStandardItem] = None) -> None:
        name_item = self._add_detail(node.name, node.value, node.refs, parent)
        for child in node.children:
            self._append_detail_node(child, name_item)

    def _add_onam_details(self, fields: List) -> None:
        resolver = self.current_plugin.formid_resolver if self.current_plugin else None
        for field_obj in fields:
            if field_obj.signature != "ONAM":
                continue
            raw = field_obj.raw
            if len(raw) % 4 != 0:
                continue
            count = len(raw) // 4
            if count == 0:
                continue
            for i in range(count):
                form_id = int.from_bytes(raw[i * 4 : (i + 1) * 4], "little")
                if resolver:
                    value = resolver.describe(form_id)
                else:
                    value = f"0x{form_id:08X}"
                self._add_detail("ONAM", value, [(None, form_id)])

    def _show_plugin_details(self, plugin: PluginFile) -> None:
        self._add_detail("Path", plugin.path)
        self._add_detail("File Size", format_file_size(plugin.file_size))
        self._add_detail("Record Header Size", str(plugin.header_size))
        self._add_detail("Localized", "Yes" if plugin.localized else "No")
        self._add_detail("Strings Loaded", str(plugin.strings.total_count))

        if plugin.masters:
            self._add_detail("Master Files", str(len(plugin.masters)))
            for master in plugin.masters:
                self._add_detail("Master File", master)

        tes4 = next(
            (
                c
                for c in plugin.children
                if isinstance(c, Record) and c.signature == "TES4" and c.form_id == 0
            ),
            None,
        )
        if tes4:
            self._add_onam_details(tes4.fields)

        groups = sum(1 for c in plugin.children if isinstance(c, Group))
        records = sum(1 for c in plugin.children if isinstance(c, Record))
        self._add_detail("Top-Level Groups", str(groups))
        self._add_detail("Top-Level Records", str(records))

    def _show_group_details(self, group: Group) -> None:
        self._add_detail("Group Type", f"{group.group_type} ({group_type_label(group)})")
        self._add_detail("Label", format_group_label(group, self.current_plugin))
        self._add_detail("Group Size", f"{group.group_size} bytes")
        self._add_detail("Stamp", f"0x{group.stamp:08X}")
        self._add_detail("File Offset", f"0x{group.raw_offset:X}")

        if group.unknown1 is not None:
            self._add_detail("Unknown1", f"0x{group.unknown1:04X}")
        if group.unknown2 is not None:
            self._add_detail("Unknown2", f"0x{group.unknown2:04X}")

        groups = sum(1 for c in group.children if isinstance(c, Group))
        records = sum(1 for c in group.children if isinstance(c, Record))
        self._add_detail("Child Groups", str(groups))
        self._add_detail("Child Records", str(records))
        self._add_detail("Max Recursion Depth", str(MAX_RECURSION_DEPTH))

    def _show_record_details(self, record: Record) -> None:
        parser = StructuredSubrecordParser(record, self.current_plugin)
        nodes = parser.iter_nodes()
        if nodes:
            self._append_detail_node(nodes[0])

        if record.signature == "TES4" and record.form_id == 0:
            author = extract_string_field(record.fields, ("CNAM",), self.current_plugin)
            description = extract_string_field(record.fields, ("SNAM", "DESC"), self.current_plugin)
            if author:
                self._add_detail("Author", author)
            if description:
                self._add_detail("Description", description)
            self._add_onam_details(record.fields)

        for node in nodes[1:]:
            self._append_detail_node(node)

    def _on_conflict_view_activated(self, index: QModelIndex) -> None:
        """Handler for conflict view item activation."""
        if not index.isValid():
            return

        # Always get the first column (Record) where we stored the data
        if index.column() != 0:
            index = index.sibling(index.row(), 0)

        item = self.conflict_model.itemFromIndex(index)
        if item is None:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        if data and isinstance(data, tuple) and len(data) == 2:
            signature, form_id = data
            self._navigate_to_formid(signature, form_id)

    def _on_detail_activated(self, index) -> None:
        if not index.isValid():
            return
        if index.column() != 1:
            index = index.sibling(index.row(), 1)
        item = self.detail_model.itemFromIndex(index)
        if item is None:
            return
        refs = item.data(DETAIL_REF_ROLE)
        if not refs:
            return
        sig, form_id = refs[0]
        self._navigate_to_formid(sig, form_id)

    def _on_tree_activated(self, index) -> None:
        if not index.isValid():
            return
        item = self.tree_model.itemFromIndex(index.siblingAtColumn(0))
        if item is None:
            return
        refs = item.data(TREE_REF_ROLE)
        if not refs:
            return
        sig, form_id = refs[0]
        self._navigate_to_formid(sig, form_id)

    def _ensure_path_loaded(self, path: List[Group]) -> Optional[QStandardItem]:
        parent_item = self.tree_model.item(0, 0)
        if parent_item is None:
            return None
        for group in path:
            if parent_item.data(LAZY_ROLE):
                self._on_tree_expanded(parent_item.index())
            item = self._group_index.get(id(group))
            if item is None:
                return None
            parent_item = item
        return parent_item

    def _navigate_to_formid(self, signature: Optional[str], form_id: int, add_history: bool = True) -> None:
        if not self._record_index and not self._record_paths:
            return
        target = None
        if signature is not None:
            target = self._record_index.get((signature, form_id))
        if target is None and signature is None:
            for (sig, fid), item in self._record_index.items():
                if fid == form_id:
                    target = item
                    signature = sig
                    break
        if target is None and signature is not None:
            path = self._record_paths.get((signature, form_id))
            if path is not None:
                parent_item = self._ensure_path_loaded(path)
                if parent_item is not None and parent_item.data(LAZY_ROLE):
                    self._on_tree_expanded(parent_item.index())
                target = self._record_index.get((signature, form_id))

        if target is None:
            return
        idx = target.index()
        if not idx.isValid():
            return
        self.tree_view.setCurrentIndex(idx)
        self.tree_view.scrollTo(idx)

        if add_history:
            if self._history_index < len(self._history) - 1:
                self._history = self._history[: self._history_index + 1]
            self._history.append((signature, form_id))
            self._history_index = min(len(self._history) - 1, 100)
            if len(self._history) > 100:
                self._history.pop(0)
                self._history_index = len(self._history) - 1

    def _on_search_requested(self, text: str) -> None:
        if not self.current_plugin:
            self.search_widget.set_results([])
            return
        records = search_records(
            self.current_plugin,
            text,
            None,
            self._resolve_full_name,
            limit=50,
        )
        results = [(self._build_record_label(record), record) for record in records]
        self._last_search_records = list(records)
        self.search_widget.set_results(results)

    def _on_search_result_selected(self, record: Record) -> None:
        self._navigate_to_formid(record.signature, record.form_id)

    def _on_advanced_search_requested(self, text: str, fields: List[str]) -> None:
        if not self.current_plugin:
            self.tools_panel.set_search_results([])
            return
        search_fields = None if "all" in fields else fields
        records = search_records(
            self.current_plugin,
            text,
            search_fields,
            self._resolve_full_name,
            limit=200,
        )
        results = []
        for record in records:
            results.append(
                (
                    self._build_record_label(record),
                    self._record_type_text(record),
                    record,
                )
            )
        self._last_search_records = list(records)
        self.tools_panel.set_search_results(results)

    def _show_tools_flyout(self) -> None:
        if self.tools_button.isVisible():
            self._toggle_flyout(self.search_flyout, self.tools_button)
            return
        self.search_flyout.open_at(self)

    def _toggle_flyout(self, flyout: FlyoutPopup, anchor: QWidget) -> None:
        if self._active_flyout and self._active_flyout is not flyout:
            self._active_flyout.close()
        if flyout.isVisible():
            flyout.close()
            return
        self._active_flyout = flyout
        flyout.open_at(anchor)

    def _on_flyout_closed(self) -> None:
        self._active_flyout = None

    def _focus_advanced_search(self) -> None:
        self._show_tools_flyout()
        self.tools_panel.focus_search()

    def _focus_quick_filter(self) -> None:
        self.left_filter_box.setFocus()
        self.left_filter_box.selectAll()

    def _build_record_label(self, record: Record) -> str:
        return format_record_identity(record, self.current_plugin, self._resolve_full_name)

    def _record_type_text(self, record: Record) -> str:
        if record.signature == "TES4" and record.form_id == 0:
            return "TES4 - File Header"
        type_text = RECORD_SIGNATURE_TYPES.get(record.signature, record.signature)
        if type_text != record.signature:
            type_text = f"{record.signature} - {type_text}"
        return type_text

    def _resolve_full_name(self, form_id: Union[int, Record]) -> Optional[str]:
        if not self.current_plugin:
            return None

        if isinstance(form_id, Record):
            return form_id.full_name

        # Если это FormID, пробуем найти запись в текущем плагине
        if self.current_plugin.formid_resolver:
            record = self.current_plugin.formid_resolver.get(form_id)
            return record.full_name if record else None
        
        return None

class MainWindow(QMainWindow):
    """Главное окно приложения, теперь просто обертка над PluginViewerWidget."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skyrim ESP Viewer")
        self.setMinimumSize(1200, 800)

        self.viewer = PluginViewerWidget(self)
        self.setCentralWidget(self.viewer)

    def load_plugin(self, path: str) -> None:
        self.viewer.load_plugin(path)

    def closeEvent(self, event) -> None:
        self.viewer._save_ui_state()
        super().closeEvent(event)
