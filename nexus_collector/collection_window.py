"""
Главное окно плагина — древовидный список модов с drag-and-drop.
"""

import webbrowser
import sys
import os
import re
from typing import TYPE_CHECKING
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QMimeData, QByteArray, QSize, pyqtSlot, QUrl, QThread, pyqtSignal,
    QEvent, QTimer,
)
from PyQt6.QtGui import (
    QIcon, QDrag, QAction, QPixmap, QFont, QColor, QBrush,
    QWheelEvent, QResizeEvent,
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QPushButton, QToolBar, QStatusBar, QMenu,
    QInputDialog, QMessageBox, QTextBrowser,
    QSplitter, QLabel, QAbstractItemView,
    QStyle, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QProgressBar, QApplication,
    QScrollArea, QFrame, QSpinBox, QSizePolicy,
    QSlider, QComboBox, QTextEdit, QSizeGrip,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

if TYPE_CHECKING:
    import mobase
    from .collection_storage import CollectionStorage
    from .sync_server import SyncServer

from .nexus_api import NexusApi, NexusApiError
from .download_manager import DownloadManager


# ═══════════════════════════════════════════════════════════════
#  Утилита: очистка HTML от Nexus
# ═══════════════════════════════════════════════════════════════

def sanitize_nexus_html(raw_html: str) -> str:
    """
    Очищает HTML-описание мода с Nexus для корректного отображения
    в QTextBrowser.

    Проблемы оригинального HTML:
    - inline style с абсолютными размерами шрифтов
    - фиксированные цвета, невидимые на тёмном фоне
    - вложенные div/span с position/float
    - BBCode-остатки [spoiler], [url] и т.д.
    """
    if not raw_html:
        return ""

    text = raw_html

    # 1. Убираем все inline style — они ломают масштабирование
    text = re.sub(r'\s*style\s*=\s*"[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s*style\s*=\s*'[^']*'", '', text, flags=re.IGNORECASE)

    # 2. Убираем class атрибуты (бесполезны без CSS)
    text = re.sub(r'\s*class\s*=\s*"[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s*class\s*=\s*'[^']*'", '', text, flags=re.IGNORECASE)

    # 3. Заменяем div на p для лучшей обработки QTextBrowser
    text = re.sub(r'<div[^>]*>', '<p>', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '</p>', text, flags=re.IGNORECASE)

    # 4. Убираем span (без стилей они бесполезны)
    text = re.sub(r'</?span[^>]*>', '', text, flags=re.IGNORECASE)

    # 5. Убираем font теги с атрибутами размера/цвета
    text = re.sub(r'<font[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</font>', '', text, flags=re.IGNORECASE)

    # 6. Конвертируем BBCode остатки
    # [b]...[/b]
    text = re.sub(r'\[b\](.*?)\[/b\]', r'<b>\1</b>', text, flags=re.IGNORECASE | re.DOTALL)
    # [i]...[/i]
    text = re.sub(r'\[i\](.*?)\[/i\]', r'<i>\1</i>', text, flags=re.IGNORECASE | re.DOTALL)
    # [u]...[/u]
    text = re.sub(r'\[u\](.*?)\[/u\]', r'<u>\1</u>', text, flags=re.IGNORECASE | re.DOTALL)
    # [url=...]...[/url]
    text = re.sub(
        r'\[url=([^\]]+)\](.*?)\[/url\]',
        r'<a href="\1">\2</a>',
        text, flags=re.IGNORECASE | re.DOTALL
    )
    # [url]...[/url]
    text = re.sub(
        r'\[url\](.*?)\[/url\]',
        r'<a href="\1">\1</a>',
        text, flags=re.IGNORECASE | re.DOTALL
    )
    # [img]...[/img]
    text = re.sub(
        r'\[img\](.*?)\[/img\]',
        r'<br><img src="\1" width="100%"><br>',
        text, flags=re.IGNORECASE | re.DOTALL
    )
    # [size=...]...[/size] — убираем, размер контролируем через шрифт виджета
    text = re.sub(r'\[size=[^\]]*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/size\]', '', text, flags=re.IGNORECASE)
    # [color=...]...[/color] — убираем фиксированные цвета
    text = re.sub(r'\[color=[^\]]*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/color\]', '', text, flags=re.IGNORECASE)
    # [spoiler] / [/spoiler]
    text = re.sub(r'\[spoiler\]', '<details><summary>Spoiler</summary>', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/spoiler\]', '</details>', text, flags=re.IGNORECASE)
    # [center]...[/center]
    text = re.sub(r'\[center\](.*?)\[/center\]', r'<center>\1</center>', text, flags=re.IGNORECASE | re.DOTALL)
    # [line] / [hr]
    text = re.sub(r'\[line\]|\[hr\]', '<hr>', text, flags=re.IGNORECASE)
    # [list] / [*] / [/list]
    text = re.sub(r'\[list\]', '<ul>', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/list\]', '</ul>', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\*\]', '<li>', text, flags=re.IGNORECASE)

    # 7. Делаем img адаптивными — убираем фиксированные width/height
    text = re.sub(
        r'<img([^>]*)\s+width\s*=\s*["\']?\d+["\']?',
        r'<img\1',
        text, flags=re.IGNORECASE
    )
    text = re.sub(
        r'<img([^>]*)\s+height\s*=\s*["\']?\d+["\']?',
        r'<img\1',
        text, flags=re.IGNORECASE
    )

    # 8. Убираем пустые параграфы
    text = re.sub(r'<p>\s*</p>', '', text)
    text = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '', text)

    # 9. Убираем множественные переносы строк
    text = re.sub(r'(<br\s*/?>){3,}', '<br><br>', text)

    return text.strip()


# ═══════════════════════════════════════════════════════════════
#  Роли для данных в элементах дерева
# ═══════════════════════════════════════════════════════════════

ROLE_TYPE = Qt.ItemDataRole.UserRole          # "mod" или "folder"
ROLE_DATA = Qt.ItemDataRole.UserRole + 1      # dict с данными мода


# ═══════════════════════════════════════════════════════════════
#  Кастомный QTreeWidget с поддержкой Drag-and-Drop
# ═══════════════════════════════════════════════════════════════

class CollectionTree(QTreeWidget):
    tree_structure_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(4)
        self.setHeaderLabels(["Name", "Game", "Status", "Version"])

        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAnimated(True)
        self.setAlternatingRowColors(True)
        self.setIndentation(20)
        self.setIconSize(QSize(24, 24))

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu_proxy)

        self._context_menu_handler = None

    def _show_context_menu_proxy(self, position):
        if self._context_menu_handler:
            self._context_menu_handler(position)

    def mimeData(self, items):
        mime = super().mimeData(items)
        self._drag_items_data = {}
        for item in items:
            key = item.text(0)
            self._drag_items_data[key] = {
                "type": item.data(0, ROLE_TYPE),
                "data": item.data(0, ROLE_DATA),
            }
        return mime

    def dropEvent(self, event):
        dragged_data = getattr(self, "_drag_items_data", {})
        super().dropEvent(event)
        if dragged_data:
            self._restore_user_data(self.invisibleRootItem(), dragged_data)
        self.tree_structure_changed.emit()

    def _restore_user_data(self, parent, saved_data: dict):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, ROLE_TYPE) is None:
                key = child.text(0)
                if key in saved_data:
                    child.setData(0, ROLE_TYPE, saved_data[key]["type"])
                    child.setData(0, ROLE_DATA, saved_data[key]["data"])
            self._restore_user_data(child, saved_data)


# ═══════════════════════════════════════════════════════════════
#  Масштабируемый QLabel для изображений
# ═══════════════════════════════════════════════════════════════

class ScalableImageLabel(QLabel):
    """QLabel, который автоматически масштабирует pixmap при resize."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(150)
        self.setMaximumHeight(500)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setText("No Image")

    def setSourcePixmap(self, pixmap: QPixmap | None):
        self._source_pixmap = pixmap
        if pixmap and not pixmap.isNull():
            self._rescale()
        else:
            self._source_pixmap = None
            super().setPixmap(QPixmap())
            self.setText("No Image")

    def clearImage(self):
        self._source_pixmap = None
        self.clear()
        self.setText("No Image")

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._source_pixmap and not self._source_pixmap.isNull():
            w = self.width() - 4
            h = self.height() - 4
            if w > 0 and h > 0:
                scaled = self._source_pixmap.scaled(
                    QSize(w, h),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                super().setPixmap(scaled)


# ═══════════════════════════════════════════════════════════════
#  Масштабируемый QTextBrowser для описаний
# ═══════════════════════════════════════════════════════════════

class ScalableTextBrowser(QTextBrowser):
    """
    QTextBrowser с поддержкой:
    - Ctrl+колёсико = масштабирование
    - Двойной клик = открытие в отдельном окне
    """
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom_level = 100  # процент
        self.setOpenExternalLinks(True)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom_level = min(300, self._zoom_level + 10)
            elif delta < 0:
                self._zoom_level = max(50, self._zoom_level - 10)
            self._apply_zoom()
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        anchor = self.anchorAt(event.pos())
        if not anchor:
            self.double_clicked.emit()
        else:
            super().mouseDoubleClickEvent(event)

    def setZoomLevel(self, percent: int):
        self._zoom_level = max(50, min(300, percent))
        self._apply_zoom()

    def zoomLevel(self) -> int:
        return self._zoom_level

    def _apply_zoom(self):
        font = self.font()
        base_size = QApplication.font().pointSize()
        if base_size <= 0:
            base_size = 10
        new_size = max(6, int(base_size * self._zoom_level / 100))
        font.setPointSize(new_size)
        self.setFont(font)


# ═══════════════════════════════════════════════════════════════
#  Диалог выбора файла
# ═══════════════════════════════════════════════════════════════

class FileSelectDialog(QDialog):
    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select File to Download")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select which file to download:"))

        self._list = QListWidget()
        for f in files:
            size_str = self._format_size(f.size_kb)
            text = f"[{f.category_name}] {f.name} v{f.version} ({size_str})"
            if f.description:
                text += f"\n  {f.description[:100]}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, f.file_id)
            if f.is_primary:
                item.setFont(QFont("", -1, QFont.Weight.Bold))
            self._list.addItem(item)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _format_size(kb: int) -> str:
        if kb < 1024:
            return f"{kb} KB"
        elif kb < 1024 * 1024:
            return f"{kb / 1024:.1f} MB"
        else:
            return f"{kb / (1024 * 1024):.2f} GB"

    def selected_file_id(self) -> int | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


# ═══════════════════════════════════════════════════════════════
#  Диалог полного описания
# ═══════════════════════════════════════════════════════════════

class FullDescriptionDialog(QDialog):
    """Отдельное окно с полным описанием мода и масштабированием."""

    def __init__(self, title: str, content_html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Description: {title}")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )

        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.resize(geom.width() * 2 // 3, geom.height() * 2 // 3)
        else:
            self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Панель управления ──
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Zoom:"))

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(50, 300)
        self._zoom_slider.setValue(100)
        self._zoom_slider.setTickInterval(25)
        self._zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._zoom_slider.setFixedWidth(200)
        toolbar.addWidget(self._zoom_slider)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(50)
        toolbar.addWidget(self._zoom_label)

        btn_reset = QPushButton("Reset")
        btn_reset.setFixedWidth(60)
        btn_reset.clicked.connect(lambda: self._zoom_slider.setValue(100))
        toolbar.addWidget(btn_reset)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── Текст ──
        self._browser = ScalableTextBrowser()
        self._browser.setHtml(content_html)
        layout.addWidget(self._browser, 1)

        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)

        # ── Кнопка закрытия ──
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_zoom_changed(self, value: int):
        self._zoom_label.setText(f"{value}%")
        self._browser.setZoomLevel(value)


# ═══════════════════════════════════════════════════════════════
#  Фоновые потоки
# ═══════════════════════════════════════════════════════════════

class FetchModInfoWorker(QThread):
    finished = pyqtSignal(str, dict)
    error = pyqtSignal(str, str)

    def __init__(self, api: NexusApi, unique_id: str, game: str, mod_id: int):
        super().__init__()
        self._api = api
        self._unique_id = unique_id
        self._game = game
        self._mod_id = mod_id

    def run(self):
        try:
            info = self._api.get_mod_info(self._game, self._mod_id)
            self.finished.emit(self._unique_id, {
                "name": info.name,
                "summary": info.summary,
                "description": info.description,
                "version": info.version,
                "author": info.author,
                "category_id": info.category_id,
                "picture_url": info.picture_url,
                "endorsement_count": info.endorsement_count,
                "downloads_count": info.downloads_count,
                "images": info.images,
            })
        except Exception as e:
            self.error.emit(self._unique_id, str(e))


class FetchFilesForNxmWorker(QThread):
    finished = pyqtSignal(str, int, list)
    error = pyqtSignal(str, int, str)

    def __init__(self, api: NexusApi, game: str, mod_id: int):
        super().__init__()
        self._api = api
        self._game = game
        self._mod_id = mod_id

    def run(self):
        try:
            files = self._api.get_mod_files(self._game, self._mod_id)
            files_data = [
                {
                    "file_id": f.file_id,
                    "name": f.name,
                    "version": f.version,
                    "category_name": f.category_name,
                    "size_kb": f.size_kb,
                    "description": f.description,
                    "is_primary": f.is_primary,
                }
                for f in files
            ]
            self.finished.emit(self._game, self._mod_id, files_data)
        except Exception as e:
            self.error.emit(self._game, self._mod_id, str(e))


# ═══════════════════════════════════════════════════════════════
#  Главное окно
# ═══════════════════════════════════════════════════════════════

STATUS_COLORS = {
    "not_installed": QColor("#888888"),
    "downloading":   QColor("#3498db"),
    "downloaded":    QColor("#f39c12"),  # Orange for downloaded but not installed
    "installed":     QColor("#27ae60"),  # Green for installed in MO2
    "error":         QColor("#e74c3c"),
}

STATUS_LABELS = {
    "not_installed": "Not Downloaded",
    "downloading":   "Downloading...",
    "downloaded":    "Downloaded",
    "installed":     "Installed (MO2)",
    "error":         "Error",
}


class CollectionWindow(QDialog):

    def __init__(
        self,
        parent=None,
        storage: "CollectionStorage" = None,
        organizer: "mobase.IOrganizer" = None,
        api_key: str = "",
        sync_server: "SyncServer" = None,
    ):
        super().__init__(parent)
        self._storage = storage
        self._organizer = organizer
        self._api_key = api_key
        self._sync_server = sync_server
        self._nexus_api = NexusApi(api_key) if api_key else None
        self._download_manager: DownloadManager | None = None
        self._network_manager = QNetworkAccessManager(self)
        self._active_workers: list[QThread] = []
        self._tree_mod_ids: set[str] = set()

        # Dragging support
        self._drag_pos = None

        # Карусель изображений
        self._current_images: list[str] = []
        self._current_image_idx: int = 0

        if self._nexus_api and organizer:
            self._download_manager = DownloadManager(
                self._nexus_api, organizer, storage
            )
            self._download_manager.download_finished.connect(
                self._on_download_finished
            )

        self._setup_ui()
        self._load_geometry()
        self._load_tree()
        self._connect_signals()

    # ── Автоскрытие при потере фокуса (Flyout logic) ──

    def event(self, e):
        if e.type() == QEvent.Type.WindowDeactivate:
            QTimer.singleShot(150, self._check_should_hide)
        return super().event(e)

    def _check_should_hide(self):
        if not self.isVisible():
            return

        active = QApplication.activeWindow()
        if active is self:
            return

        if active is not None and active.parent() is self:
            return

        modal = QApplication.activeModalWidget()
        if modal is not None:
            return

        self.hide()

    # ── Перетаскивание безрамочного окна ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Разрешаем тащить только за верхнюю часть (тулбар)
            if event.pos().y() < 50:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── Сохранение и загрузка геометрии ──

    def _load_geometry(self):
        """Загружает геометрию окна из хранилища."""
        if not self._storage:
            return
        geo_hex = self._storage.get_geometry()
        if geo_hex:
            self.restoreGeometry(QByteArray.fromHex(geo_hex.encode()))

    def _save_geometry(self):
        """Сохраняет текущую геометрию окна в хранилище."""
        if not self._storage:
            return
        geo = self.saveGeometry()
        geo_hex = geo.toHex().data().decode()
        self._storage.set_geometry(geo_hex)

    def resizeEvent(self, event: QResizeEvent):
        """Вызывается при изменении размера окна."""
        super().resizeEvent(event)
        
        # Позиционируем QSizeGrip в правом нижнем углу
        if hasattr(self, "_sizegrip"):
            self._sizegrip.move(
                self.width() - self._sizegrip.width(),
                self.height() - self._sizegrip.height()
            )

        # Сохраняем геометрию при каждом ресайзе (с небольшим дебаунсом было бы лучше, но так проще)
        self._save_geometry()

    # ═══════════════════════════════════════════════════════
    #  UI
    # ═══════════════════════════════════════════════════════

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_mo2_statuses()

    def _setup_ui(self):
        self.setWindowTitle("Nexus Mod Collector")
        self.setMinimumSize(1000, 650)
        
        # Flyout Window Flags
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # Style for frameless window

        # ── Central Layout ──
        # Используем QDialog, поэтому вместо setCentralWidget просто layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ── Toolbar (Custom widget instead of addToolBar) ──
        toolbar_container = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(2, 2, 2, 2)
        toolbar_layout.setSpacing(6)
        
        self._act_add_folder_btn = QPushButton("📁 New Folder")
        self._act_add_folder_btn.clicked.connect(self._on_add_folder)
        toolbar_layout.addWidget(self._act_add_folder_btn)

        self._act_refresh_btn = QPushButton("🔄 Refresh")
        self._act_refresh_btn.clicked.connect(self._force_reload_tree)
        toolbar_layout.addWidget(self._act_refresh_btn)

        self._act_expand_all_btn = QPushButton("➕ Expand All")
        self._act_expand_all_btn.clicked.connect(lambda: self._tree.expandAll())
        toolbar_layout.addWidget(self._act_expand_all_btn)

        self._act_collapse_all_btn = QPushButton("➖ Collapse All")
        self._act_collapse_all_btn.clicked.connect(lambda: self._tree.collapseAll())
        toolbar_layout.addWidget(self._act_collapse_all_btn)

        toolbar_layout.addSeparator() if hasattr(toolbar_layout, 'addSeparator') else toolbar_layout.addSpacing(10)

        self._act_settings_btn = QPushButton("⚙ Settings")
        self._act_settings_btn.clicked.connect(self._on_settings_clicked)
        toolbar_layout.addWidget(self._act_settings_btn)

        toolbar_layout.addStretch()

        self._server_label = QLabel()
        self._update_server_status()
        toolbar_layout.addWidget(self._server_label)
        
        main_layout.addWidget(toolbar_container)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # ────────── ЛЕВАЯ ПАНЕЛЬ ──────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._tree = CollectionTree()
        self._tree._context_menu_handler = self._show_context_menu
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.tree_structure_changed.connect(self._save_tree_to_storage)
        left_layout.addWidget(self._tree, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._btn_download = QPushButton("⬇ Download Selected")
        self._btn_download.clicked.connect(self._on_download_selected)
        self._btn_download.setEnabled(False)
        btn_layout.addWidget(self._btn_download)

        self._btn_open_nexus = QPushButton("🌐 Open on Nexus")
        self._btn_open_nexus.clicked.connect(self._on_open_nexus)
        self._btn_open_nexus.setEnabled(False)
        btn_layout.addWidget(self._btn_open_nexus)

        self._btn_delete = QPushButton("🗑 Remove")
        self._btn_delete.clicked.connect(self._on_delete_selected)
        self._btn_delete.setEnabled(False)
        btn_layout.addWidget(self._btn_delete)

        left_layout.addLayout(btn_layout)
        splitter.addWidget(left_widget)

        # ────────── ПРАВАЯ ПАНЕЛЬ ──────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        # Заголовок
        self._detail_title = QLabel("Select a mod to see details")
        self._detail_title.setFont(QFont("", 14, QFont.Weight.Bold))
        self._detail_title.setWordWrap(True)
        self._detail_title.setMaximumHeight(60)
        right_layout.addWidget(self._detail_title)

        # ── Изображение + карусель ──
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(4)

        self._detail_image = ScalableImageLabel()
        image_layout.addWidget(self._detail_image)

        # Кнопки карусели — ВСЕГДА в layout, видимость управляется
        carousel_bar = QHBoxLayout()
        carousel_bar.setContentsMargins(0, 0, 0, 0)
        carousel_bar.setSpacing(6)

        self._btn_prev_img = QPushButton("◀ Prev")
        self._btn_prev_img.setFixedHeight(28)
        self._btn_prev_img.setMinimumWidth(70)
        self._btn_prev_img.clicked.connect(self._on_prev_image)
        carousel_bar.addWidget(self._btn_prev_img)

        self._image_counter = QLabel("0 / 0")
        self._image_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        carousel_bar.addWidget(self._image_counter, 1)

        self._btn_next_img = QPushButton("Next ▶")
        self._btn_next_img.setFixedHeight(28)
        self._btn_next_img.setMinimumWidth(70)
        self._btn_next_img.clicked.connect(self._on_next_image)
        carousel_bar.addWidget(self._btn_next_img)

        # Контейнер для кнопок карусели
        self._carousel_widget = QWidget()
        self._carousel_widget.setLayout(carousel_bar)
        self._carousel_widget.setFixedHeight(34)
        self._carousel_widget.setVisible(False)
        image_layout.addWidget(self._carousel_widget)

        right_layout.addWidget(image_container)

        # ── Информация ──
        self._detail_info = QLabel()
        self._detail_info.setWordWrap(True)
        self._detail_info.setTextFormat(Qt.TextFormat.RichText)
        self._detail_info.setMaximumHeight(100)
        right_layout.addWidget(self._detail_info)

        # ── Описание (масштабируемый) ──
        desc_header = QHBoxLayout()
        desc_header.setSpacing(4)

        desc_label = QLabel("<b>Description</b>")
        desc_header.addWidget(desc_label)

        desc_hint = QLabel("(Ctrl+Scroll = zoom, Double-click = fullscreen)")
        desc_header.addWidget(desc_hint)

        desc_header.addStretch()

        self._btn_fetch_info = QPushButton("📋 Fetch from Nexus")
        self._btn_fetch_info.setFixedHeight(26)
        self._btn_fetch_info.clicked.connect(self._on_fetch_info)
        self._btn_fetch_info.setEnabled(False)
        desc_header.addWidget(self._btn_fetch_info)

        right_layout.addLayout(desc_header)

        self._detail_description = ScalableTextBrowser()
        self._detail_description.setPlaceholderText(
            "No description available.\n"
            "Select a mod and click 'Fetch from Nexus' to load."
        )
        self._detail_description.setMinimumHeight(150)
        self._detail_description.double_clicked.connect(
            self._on_description_fullscreen
        )
        right_layout.addWidget(self._detail_description, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([550, 400])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # ── Status Bar ──
        self._statusbar = QStatusBar()
        self._statusbar.setFixedHeight(26)
        self._statusbar.setSizeGripEnabled(True)
        main_layout.addWidget(self._statusbar)

        # Дополнительный QSizeGrip для правого нижнего угла (если статус-бар не справляется)
        self._sizegrip = QSizeGrip(self)
        self._sizegrip.setFixedSize(self._sizegrip.sizeHint())
        self._sizegrip.raise_()

        self._status_mod_count = QLabel("Mods: 0")
        self._statusbar.addPermanentWidget(self._status_mod_count)

        self._status_api_limit = QLabel("")
        self._status_api_limit.setVisible(False)
        self._statusbar.addPermanentWidget(self._status_api_limit)

        self._status_api_warning = QLabel("⚠️ API Key Missing!")
        self._status_api_warning.setVisible(False)
        self._statusbar.addPermanentWidget(self._status_api_warning)

        self._statusbar.showMessage("Ready")

    def _connect_signals(self):
        if self._storage:
            self._storage.collection_changed.connect(self._force_reload_tree)
            self._storage.mods_added.connect(self._on_mods_added)
            self._storage.mod_updated.connect(self._on_mod_updated)

        if self._sync_server:
            self._sync_server.signal.data_received.connect(self._on_sync_received)

        if self._organizer:
            # Используем mobase API для отслеживания изменений в списке модов
            # В зависимости от версии mobase, это может быть сигнал или колбэк
            try:
                self._organizer.onModInstalled(lambda _: self._refresh_mo2_statuses())
                self._organizer.onModRemoved(lambda _: self._refresh_mo2_statuses())
                self._organizer.onModMoved(lambda _: self._refresh_mo2_statuses())
            except (AttributeError, TypeError):
                # Если сигналы не поддерживаются напрямую в этой версии
                pass

    # ═══════════════════════════════════════════════════════
    #  Загрузка / сохранение дерева
    # ═══════════════════════════════════════════════════════

    def _load_tree(self):
        self._tree.blockSignals(True)
        self._tree.clear()
        self._tree_mod_ids.clear()

        tree_data = self._storage.get_tree() if self._storage else []
        self._populate_tree(self._tree.invisibleRootItem(), tree_data)

        self._tree.blockSignals(False)
        self._refresh_mo2_statuses()
        self._update_status_count()

    @pyqtSlot()
    def _force_reload_tree(self):
        expanded = self._save_expanded_state()
        sel_id = self._get_selected_mod_id()

        self._load_tree()

        self._restore_expanded_state(expanded)
        if sel_id:
            self._select_mod_by_id(sel_id)

    @pyqtSlot(list)
    def _on_mods_added(self, new_nodes: list[dict]):
        self._tree.blockSignals(True)
        for node in new_nodes:
            uid = node.get("uniqueId", "")
            if uid in self._tree_mod_ids:
                continue
            self._add_mod_item(self._tree.invisibleRootItem(), node)
        self._tree.blockSignals(False)
        self._update_status_count()

    @pyqtSlot(str, dict)
    def _on_mod_updated(self, unique_id: str, updated_data: dict):
        item = self._find_tree_item_by_id(unique_id)
        if not item:
            return

        item.setData(0, ROLE_DATA, updated_data)
        item.setText(0, updated_data.get("title", item.text(0)))
        item.setText(1, updated_data.get("game", item.text(1)))

        status = updated_data.get("status", "not_installed")
        item.setText(2, STATUS_LABELS.get(status, status))
        item.setForeground(2, QBrush(STATUS_COLORS.get(status, QColor("#888"))))
        item.setText(3, updated_data.get("version", item.text(3)))

        sel = self._tree.selectedItems()
        if sel and sel[0] is item:
            self._show_mod_details(updated_data)

    def _populate_tree(self, parent_item, nodes: list[dict]):
        for node in nodes:
            ntype = node.get("type")
            if ntype == "folder":
                item = QTreeWidgetItem(parent_item)
                item.setText(0, node["name"])
                item.setData(0, ROLE_TYPE, "folder")
                item.setData(0, ROLE_DATA, node)
                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsDropEnabled
                    | Qt.ItemFlag.ItemIsDragEnabled
                )
                item.setIcon(
                    0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
                )
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)

                self._populate_tree(item, node.get("children", []))
                if node.get("expanded", True):
                    item.setExpanded(True)

            elif ntype == "mod":
                self._add_mod_item(parent_item, node)

    def _add_mod_item(self, parent_item, node: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent_item)
        item.setText(0, node.get("title", "Unknown"))
        item.setText(1, node.get("game", ""))
        status = node.get("status", "not_installed")
        item.setText(2, STATUS_LABELS.get(status, status))
        item.setText(3, node.get("version", ""))

        item.setData(0, ROLE_TYPE, "mod")
        item.setData(0, ROLE_DATA, node)
        item.setFlags(
            (item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            & ~Qt.ItemFlag.ItemIsDropEnabled
        )
        item.setForeground(2, QBrush(STATUS_COLORS.get(status, QColor("#888"))))

        uid = node.get("uniqueId", "")
        if uid:
            self._tree_mod_ids.add(uid)
        return item

    def _save_tree_to_storage(self):
        if not self._storage:
            return
        tree_data = self._serialize_tree(self._tree.invisibleRootItem())
        self._storage.blockSignals(True)
        self._storage.set_tree(tree_data, emit_changed=False)
        self._storage.blockSignals(False)

    def _serialize_tree(self, parent_item) -> list[dict]:
        result = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            node_type = child.data(0, ROLE_TYPE)

            if node_type == "folder":
                result.append({
                    "type": "folder",
                    "name": child.text(0),
                    "expanded": child.isExpanded(),
                    "children": self._serialize_tree(child),
                })
            elif node_type == "mod":
                mod_data = child.data(0, ROLE_DATA)
                if mod_data:
                    mod_data = dict(mod_data)
                    mod_data["title"] = child.text(0)
                    result.append(mod_data)
        return result

    # ── expanded state ──

    def _save_expanded_state(self) -> set[str]:
        result = set()
        self._collect_expanded(self._tree.invisibleRootItem(), "", result)
        return result

    def _collect_expanded(self, parent, path, expanded):
        for i in range(parent.childCount()):
            c = parent.child(i)
            p = f"{path}/{c.text(0)}"
            if c.isExpanded():
                expanded.add(p)
            self._collect_expanded(c, p, expanded)

    def _restore_expanded_state(self, expanded: set[str]):
        self._apply_expanded(self._tree.invisibleRootItem(), "", expanded)

    def _apply_expanded(self, parent, path, expanded):
        for i in range(parent.childCount()):
            c = parent.child(i)
            p = f"{path}/{c.text(0)}"
            if p in expanded:
                c.setExpanded(True)
            self._apply_expanded(c, p, expanded)

    def _update_status_count(self):
        total = len(self._tree_mod_ids)
        self._status_mod_count.setText(f"Mods: {total}")

        # Проверка наличия ключа API
        if not self._api_key:
            self._status_api_warning.setVisible(True)
            self._status_api_limit.setVisible(False)
        else:
            self._status_api_warning.setVisible(False)
            if self._nexus_api:
                remaining = self._nexus_api.rate_limit_remaining
                limit = self._nexus_api.rate_limit_total
                if limit > 0:
                    self._status_api_limit.setText(f"API: {remaining}/{limit}")
                    self._status_api_limit.setVisible(True)
                else:
                    self._status_api_limit.setVisible(False)
            else:
                self._status_api_limit.setVisible(False)

    def _refresh_mo2_statuses(self):
        """Проверяет статусы модов через API MO2."""
        if not self._organizer or not self._storage:
            return

        # Получаем список установленных Nexus ID в MO2
        mo2_nexus_ids = set()
        mod_list = self._organizer.modList()
        for mod_name in mod_list.allMods():
            mod = mod_list.getMod(mod_name)
            if mod:
                # В MO2 nexusId() возвращает int
                nid = mod.nexusId()
                if nid > 0:
                    mo2_nexus_ids.add(str(nid))

        # Итерируем по всем модам в дереве и обновляем их статус, если они в MO2
        all_mods = self._storage.get_all_mods()
        for mod_node in all_mods:
            uid = mod_node.get("uniqueId")
            mid = mod_node.get("modId")
            current_status = mod_node.get("status", "not_installed")

            if mid in mo2_nexus_ids:
                if current_status != "installed":
                    self._storage.update_mod_status(uid, "installed")
            elif current_status == "installed":
                # Если в дереве стоит "installed", но в MO2 его нет, возвращаем на "downloaded"
                # или "not_installed" — решим, что "downloaded"
                self._storage.update_mod_status(uid, "downloaded")

    # ═══════════════════════════════════════════════════════
    #  Поиск
    # ═══════════════════════════════════════════════════════

    def _find_tree_item_by_id(self, uid: str, parent=None) -> QTreeWidgetItem | None:
        if parent is None:
            parent = self._tree.invisibleRootItem()
        for i in range(parent.childCount()):
            c = parent.child(i)
            if c.data(0, ROLE_TYPE) == "mod":
                d = c.data(0, ROLE_DATA)
                if d and d.get("uniqueId") == uid:
                    return c
            elif c.data(0, ROLE_TYPE) == "folder":
                r = self._find_tree_item_by_id(uid, c)
                if r:
                    return r
        return None

    def _get_selected_mod_id(self) -> str | None:
        for item in self._tree.selectedItems():
            if item.data(0, ROLE_TYPE) == "mod":
                d = item.data(0, ROLE_DATA)
                if d:
                    return d.get("uniqueId")
        return None

    def _select_mod_by_id(self, uid: str):
        item = self._find_tree_item_by_id(uid)
        if item:
            self._tree.setCurrentItem(item)

    # ═══════════════════════════════════════════════════════
    #  Контекстное меню
    # ═══════════════════════════════════════════════════════

    def _show_context_menu(self, position):
        item = self._tree.itemAt(position)
        menu = QMenu(self)

        if item:
            ntype = item.data(0, ROLE_TYPE)

            if ntype == "mod":
                mod_data = item.data(0, ROLE_DATA)
                if not mod_data:
                    return

                menu.addAction("🌐 Open on Nexus").triggered.connect(
                    lambda _, d=mod_data: webbrowser.open(d.get("url", ""))
                )
                menu.addAction("⬇ Download Mod").triggered.connect(
                    lambda _, d=mod_data: self._download_mod(d)
                )
                menu.addAction("🌐 Download via Browser").triggered.connect(
                    lambda _, d=mod_data: self._download_via_browser(d)
                )
                menu.addSeparator()

                act = menu.addAction("📋 Fetch Details")
                act.triggered.connect(
                    lambda _, d=mod_data: self._fetch_mod_info(d)
                )
                act.setEnabled(bool(self._nexus_api))

                menu.addSeparator()
                menu.addAction("✏ Rename").triggered.connect(
                    lambda _, it=item: self._rename_item(it)
                )
                menu.addAction("📝 Edit Notes").triggered.connect(
                    lambda _, it=item, d=mod_data: self._edit_notes(it, d)
                )
                menu.addSeparator()
                menu.addAction("🗑 Remove").triggered.connect(
                    lambda _, it=item: self._delete_item(it)
                )

            elif ntype == "folder":
                menu.addAction("✏ Rename Folder").triggered.connect(
                    lambda _, it=item: self._rename_item(it)
                )
                menu.addAction("📁 Add Subfolder").triggered.connect(
                    lambda _, it=item: self._add_subfolder(it)
                )
                menu.addSeparator()
                menu.addAction("🗑 Remove Folder").triggered.connect(
                    lambda _, it=item: self._delete_item(it)
                )
        else:
            menu.addAction("📁 New Folder").triggered.connect(self._on_add_folder)
            menu.addAction("🔄 Refresh").triggered.connect(self._force_reload_tree)

        menu.exec(self._tree.viewport().mapToGlobal(position))

    # ═══════════════════════════════════════════════════════
    #  Обработчики выбора / деталей
    # ═══════════════════════════════════════════════════════

    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        has_selection = len(items) > 0
        has_mod = any(it.data(0, ROLE_TYPE) == "mod" for it in items)

        self._btn_download.setEnabled(has_mod)
        self._btn_open_nexus.setEnabled(has_mod)
        self._btn_delete.setEnabled(has_selection)
        self._btn_fetch_info.setEnabled(has_mod and bool(self._nexus_api))

        if has_mod:
            for it in items:
                if it.data(0, ROLE_TYPE) == "mod":
                    mod_data = it.data(0, ROLE_DATA)
                    if mod_data:
                        self._show_mod_details(mod_data)
                        if self._nexus_api and not mod_data.get("nexus_description"):
                            self._fetch_mod_info(mod_data)
                    break
        else:
            self._clear_details()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        if item.data(0, ROLE_TYPE) == "mod":
            d = item.data(0, ROLE_DATA)
            if d and d.get("url"):
                webbrowser.open(d["url"])

    def _show_mod_details(self, mod_data: dict):
        self._detail_title.setText(mod_data.get("title", "Unknown Mod"))

        # Информация
        parts = []
        if mod_data.get("author"):
            parts.append(f"<b>Author:</b> {mod_data['author']}")
        if mod_data.get("game"):
            parts.append(f"<b>Game:</b> {mod_data['game']}")
        if mod_data.get("version"):
            parts.append(f"<b>Version:</b> {mod_data['version']}")
        status = mod_data.get("status", "not_installed")
        parts.append(f"<b>Status:</b> {STATUS_LABELS.get(status, status)}")
        if mod_data.get("modId"):
            parts.append(f"<b>Mod ID:</b> {mod_data['modId']}")
        self._detail_info.setText(" &nbsp;|&nbsp; ".join(parts))

        # Описание — очищаем HTML
        desc_raw = mod_data.get("nexus_description", "")
        summary = mod_data.get("summary", "")
        notes = mod_data.get("notes", "")

        content = ""
        if notes:
            content += f"<h4>📝 Notes:</h4><p>{notes}</p><hr>"
        if summary:
            content += f"<h4>Summary:</h4><p>{summary}</p>"
        if desc_raw:
            clean_desc = sanitize_nexus_html(desc_raw)
            content += f"<h4>Full Description:</h4>{clean_desc}"

        if content:
            self._detail_description.setHtml(content)
        else:
            self._detail_description.clear()
            self._detail_description.setPlaceholderText(
                "No description. Click 'Fetch from Nexus' to load."
            )

        # Изображения
        self._current_images = []
        self._current_image_idx = 0

        if mod_data.get("images"):
            self._current_images = list(mod_data["images"])
        elif mod_data.get("image"):
            self._current_images = [mod_data["image"]]

        if self._current_images:
            self._load_carousel_image(0)
        else:
            self._detail_image.clearImage()
            self._carousel_widget.setVisible(False)

    def _update_carousel_ui(self):
        count = len(self._current_images)
        if count <= 1:
            self._carousel_widget.setVisible(False)
            return

        self._carousel_widget.setVisible(True)
        self._btn_prev_img.setEnabled(self._current_image_idx > 0)
        self._btn_next_img.setEnabled(self._current_image_idx < count - 1)
        self._image_counter.setText(
            f"{self._current_image_idx + 1} / {count}"
        )

    def _load_carousel_image(self, index: int):
        if 0 <= index < len(self._current_images):
            self._current_image_idx = index
            url = self._current_images[index]
            self._detail_image.setText("Loading...")
            request = QNetworkRequest(QUrl(url))
            reply = self._network_manager.get(request)
            reply.finished.connect(lambda r=reply: self._on_image_loaded(r))
            self._update_carousel_ui()

    def _on_prev_image(self):
        if self._current_image_idx > 0:
            self._load_carousel_image(self._current_image_idx - 1)

    def _on_next_image(self):
        if self._current_image_idx < len(self._current_images) - 1:
            self._load_carousel_image(self._current_image_idx + 1)

    def _on_image_loaded(self, reply: QNetworkReply):
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    self._detail_image.setSourcePixmap(pixmap)
                else:
                    self._detail_image.clearImage()
                    self._detail_image.setText("Invalid image data")
            else:
                self._detail_image.clearImage()
                self._detail_image.setText("Failed to load image")
        finally:
            reply.deleteLater()

    def _on_description_fullscreen(self):
        """Открывает полное описание в отдельном окне."""
        items = self._tree.selectedItems()
        if not items:
            return
        item = items[0]
        if item.data(0, ROLE_TYPE) != "mod":
            return
        mod_data = item.data(0, ROLE_DATA)
        if not mod_data:
            return

        # Собираем контент
        desc_raw = mod_data.get("nexus_description", "")
        summary = mod_data.get("summary", "")
        notes = mod_data.get("notes", "")

        content = ""
        if notes:
            content += f"<h3>📝 Notes</h3><p>{notes}</p><hr>"
        if summary:
            content += f"<h3>Summary</h3><p>{summary}</p>"
        if desc_raw:
            clean = sanitize_nexus_html(desc_raw)
            content += f"<h3>Full Description</h3>{clean}"

        if not content:
            content = "<p>No description available.</p>"

        title = mod_data.get("title", "Mod")
        dialog = FullDescriptionDialog(title, content, self)
        dialog.exec()

    def _clear_details(self):
        self._detail_title.setText("Select a mod to see details")
        self._detail_info.clear()
        self._detail_description.clear()
        self._detail_image.clearImage()
        self._carousel_widget.setVisible(False)
        self._current_images = []
        self._current_image_idx = 0

    # ═══════════════════════════════════════════════════════
    #  Операции с папками / элементами
    # ═══════════════════════════════════════════════════════

    def _on_add_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip() and self._storage:
            self._storage.add_folder(name.strip())

    def _add_subfolder(self, parent_item: QTreeWidgetItem):
        name, ok = QInputDialog.getText(self, "New Subfolder", "Folder name:")
        if ok and name.strip():
            child = QTreeWidgetItem(parent_item)
            child.setText(0, name.strip())
            child.setData(0, ROLE_TYPE, "folder")
            child.setData(0, ROLE_DATA, {
                "type": "folder", "name": name.strip(),
                "expanded": True, "children": [],
            })
            child.setFlags(
                child.flags()
                | Qt.ItemFlag.ItemIsDropEnabled
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            child.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            font = child.font(0)
            font.setBold(True)
            child.setFont(0, font)
            parent_item.setExpanded(True)
            self._save_tree_to_storage()

    def _rename_item(self, item: QTreeWidgetItem):
        old = item.text(0)
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if ok and new.strip():
            item.setText(0, new.strip())
            d = item.data(0, ROLE_DATA)
            if d:
                d = dict(d)
                if d.get("type") == "folder":
                    d["name"] = new.strip()
                else:
                    d["title"] = new.strip()
                item.setData(0, ROLE_DATA, d)
            self._save_tree_to_storage()

    def _edit_notes(self, item: QTreeWidgetItem, mod_data: dict):
        notes, ok = QInputDialog.getMultiLineText(
            self, "Edit Notes", "Notes:", mod_data.get("notes", "")
        )
        if ok:
            mod_data = dict(mod_data)
            mod_data["notes"] = notes
            item.setData(0, ROLE_DATA, mod_data)
            self._save_tree_to_storage()
            if self._storage:
                self._storage.blockSignals(True)
                self._storage.update_mod_notes(mod_data["uniqueId"], notes)
                self._storage.blockSignals(False)
            self._show_mod_details(mod_data)

    def _delete_item(self, item: QTreeWidgetItem):
        ntype = item.data(0, ROLE_TYPE)
        if ntype == "folder" and item.childCount() > 0:
            r = QMessageBox.question(
                self, "Delete Folder",
                f"Folder '{item.text(0)}' has {item.childCount()} items.\n"
                "Delete all?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        if ntype == "mod":
            d = item.data(0, ROLE_DATA)
            self._tree_mod_ids.discard(d.get("uniqueId", "") if d else "")
        elif ntype == "folder":
            self._remove_folder_ids(item)

        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            idx = self._tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self._tree.takeTopLevelItem(idx)

        self._save_tree_to_storage()
        self._update_status_count()

    def _remove_folder_ids(self, folder: QTreeWidgetItem):
        for i in range(folder.childCount()):
            c = folder.child(i)
            if c.data(0, ROLE_TYPE) == "mod":
                d = c.data(0, ROLE_DATA)
                self._tree_mod_ids.discard(d.get("uniqueId", "") if d else "")
            elif c.data(0, ROLE_TYPE) == "folder":
                self._remove_folder_ids(c)

    def _on_delete_selected(self):
        items = self._tree.selectedItems()
        if not items:
            return
        r = QMessageBox.question(
            self, "Remove",
            f"Remove {len(items)} item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        for item in items:
            ntype = item.data(0, ROLE_TYPE)
            if ntype == "mod":
                d = item.data(0, ROLE_DATA)
                self._tree_mod_ids.discard(d.get("uniqueId", "") if d else "")
            elif ntype == "folder":
                self._remove_folder_ids(item)

            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                idx = self._tree.indexOfTopLevelItem(item)
                if idx >= 0:
                    self._tree.takeTopLevelItem(idx)

        self._save_tree_to_storage()
        self._update_status_count()
        self._clear_details()

    # ═══════════════════════════════════════════════════════
    #  Settings
    # ═══════════════════════════════════════════════════════

    def _on_settings_clicked(self):
        old_key = self._storage.get_api_key() if self._storage else ""
        key, ok = QInputDialog.getText(
            self, "Nexus API Settings",
            "Enter your Nexus API Key:", text=old_key,
        )
        if not ok:
            return

        key = key.strip()
        if self._storage:
            self._storage.set_api_key(key)

        self._api_key = key
        if key:
            self._nexus_api = NexusApi(key)
            if self._organizer:
                self._download_manager = DownloadManager(
                    self._nexus_api, self._organizer, self._storage
                )
                self._download_manager.download_finished.connect(
                    self._on_download_finished
                )
        else:
            self._nexus_api = None
            self._download_manager = None

        self._on_selection_changed()
        self._update_status_count()

        if key:
            self._statusbar.showMessage("Validating API key...")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                if self._nexus_api.validate_key():
                    self._update_status_count()
                    self._statusbar.showMessage("API Key valid ✅", 5000)
                    QMessageBox.information(self, "Settings", "API Key saved and validated!")
                else:
                    self._statusbar.showMessage("API Key INVALID ❌", 5000)
                    QMessageBox.warning(self, "Settings", "API Key is invalid.")
            except Exception as e:
                self._statusbar.showMessage(f"Error: {e}", 5000)
            finally:
                QApplication.restoreOverrideCursor()

    # ═══════════════════════════════════════════════════════
    #  Nexus API
    # ═══════════════════════════════════════════════════════

    def _on_open_nexus(self):
        for it in self._tree.selectedItems():
            if it.data(0, ROLE_TYPE) == "mod":
                d = it.data(0, ROLE_DATA)
                if d and d.get("url"):
                    webbrowser.open(d["url"])

    def _on_fetch_info(self):
        for it in self._tree.selectedItems():
            if it.data(0, ROLE_TYPE) == "mod":
                d = it.data(0, ROLE_DATA)
                if d:
                    self._fetch_mod_info(d)
                break

    def _fetch_mod_info(self, mod_data: dict):
        if not self._nexus_api:
            QMessageBox.warning(self, "No API Key", "Set API key in ⚙ Settings.")
            return

        uid = mod_data.get("uniqueId")
        game = mod_data.get("game")
        mid = mod_data.get("modId")
        if not uid or not game or not mid:
            self._statusbar.showMessage("Incomplete mod data", 5000)
            return

        self._statusbar.showMessage(f"Fetching: {mod_data.get('title', uid)}...")
        worker = FetchModInfoWorker(self._nexus_api, uid, game, int(mid))
        worker.finished.connect(self._on_mod_info_fetched)
        worker.error.connect(self._on_mod_info_error)
        worker.finished.connect(lambda *_: self._cleanup_worker(worker))
        worker.error.connect(lambda *_: self._cleanup_worker(worker))
        self._active_workers.append(worker)
        worker.start()

    @pyqtSlot(str, dict)
    def _on_mod_info_fetched(self, uid: str, info: dict):
        if not self._storage:
            return
        fields = {
            "title": info.get("name", ""),
            "version": info.get("version", ""),
            "author": info.get("author", ""),
            "nexus_description": info.get("description", ""),
            "summary": info.get("summary", ""),
            "image": info.get("picture_url", ""),
            "images": info.get("images", []),
        }
        fields = {k: v for k, v in fields.items() if v}
        self._storage.update_mod_field(uid, fields)
        self._update_status_count()
        self._statusbar.showMessage(f"Fetched: {info.get('name', uid)}", 5000)

    @pyqtSlot(str, str)
    def _on_mod_info_error(self, uid: str, msg: str):
        self._update_status_count()
        self._statusbar.showMessage(f"Error: {msg}", 5000)

    def _cleanup_worker(self, worker: QThread):
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        worker.deleteLater()

    # ═══════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════
    #  Download
    # ═══════════════════════════════════════════════════════

    def _on_download_selected(self):
        for it in self._tree.selectedItems():
            if it.data(0, ROLE_TYPE) == "mod":
                d = it.data(0, ROLE_DATA)
                if d:
                    self._download_mod(d)

    def _download_mod(self, mod_data: dict):
        game = mod_data.get("game", "")
        mod_id = mod_data.get("modId", "")
        uid = mod_data.get("uniqueId", "")

        if not game or not mod_id:
            QMessageBox.warning(self, "Error", "Incomplete mod data.")
            return

        # Обновляем статус в дереве на "downloading"
        if self._storage:
            self._storage.update_mod_status(uid, "downloading")

        if self._download_manager and self._nexus_api:
            try:
                files = self._nexus_api.get_mod_files(game, int(mod_id))
                if len(files) > 1:
                    dlg = FileSelectDialog(files, self)
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        fid = dlg.selected_file_id()
                        if fid:
                            self._start_download(uid, game, int(mod_id), fid)
                    return
                elif len(files) == 1:
                    self._start_download(uid, game, int(mod_id), files[0].file_id)
                    return
                else:
                    self._statusbar.showMessage("No files found", 5000)
                    return
            except NexusApiError as e:
                self._update_status_count()
                self._download_via_nxm(game, mod_id)
                return
            except Exception as e:
                self._statusbar.showMessage(f"Error: {e}", 5000)
                self._download_via_nxm(game, mod_id)
                return

        self._download_via_nxm(game, mod_id)

    def _start_download(self, uid, game, mod_id, file_id):
        self._statusbar.showMessage(f"Downloading: {uid}...")
        self._download_manager.download_mod(uid, game, mod_id, file_id)

    def _download_via_nxm(self, game, mod_id):
        if self._nexus_api:
            self._statusbar.showMessage(f"Fetching files for mod {mod_id}...")
            worker = FetchFilesForNxmWorker(self._nexus_api, game, int(mod_id))
            worker.finished.connect(self._on_nxm_files_fetched)
            worker.error.connect(self._on_nxm_files_error)
            worker.finished.connect(lambda *_: self._cleanup_worker(worker))
            worker.error.connect(lambda *_: self._cleanup_worker(worker))
            self._active_workers.append(worker)
            worker.start()
        else:
            self._download_via_browser_url(game, str(mod_id))

    @pyqtSlot(str, int, list)
    def _on_nxm_files_fetched(self, game, mod_id, files):
        if not files:
            self._download_via_browser_url(game, str(mod_id))
            return
        if len(files) > 1:
            from .nexus_api import ModFile
            mf = [ModFile(**f) for f in files]
            dlg = FileSelectDialog(mf, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                fid = dlg.selected_file_id()
                if fid:
                    self._send_nxm(game, mod_id, fid)
            return
        self._send_nxm(game, mod_id, files[0]["file_id"])

    @pyqtSlot(str, int, str)
    def _on_nxm_files_error(self, game, mod_id, msg):
        self._update_status_count()
        self._statusbar.showMessage(f"Error: {msg}", 5000)
        self._download_via_browser_url(game, str(mod_id))

    def _send_nxm(self, game, mod_id, file_id):
        nxm = f"nxm://{game}/mods/{mod_id}/files/{file_id}"
        try:
            if sys.platform == "win32":
                os.startfile(nxm)
            else:
                webbrowser.open(nxm)
            self._statusbar.showMessage(f"Sent nxm:// (mod {mod_id})", 5000)
        except Exception as e:
            self._statusbar.showMessage(f"Failed: {e}", 5000)
            self._download_via_browser_url(game, str(mod_id))

    def _download_via_browser(self, mod_data):
        self._download_via_browser_url(
            mod_data.get("game", ""), str(mod_data.get("modId", ""))
        )

    def _download_via_browser_url(self, game, mod_id):
        webbrowser.open(f"https://www.nexusmods.com/{game}/mods/{mod_id}?tab=files")
        self._statusbar.showMessage(f"Opened browser for mod {mod_id}", 5000)

    @pyqtSlot(str, bool, str)
    def _on_download_finished(self, uid, success, msg):
        if success and self._storage:
            self._storage.update_mod_status(uid, "downloaded")
        self._update_status_count()
        self._statusbar.showMessage(f"{'✅' if success else '❌'} {msg}", 5000)

    # ── Sync ──

    @pyqtSlot(int)
    def _on_sync_received(self, count):
        self._statusbar.showMessage(f"📡 Received {count} mod(s)", 5000)

    def _update_server_status(self):
        if self._sync_server and self._sync_server.is_running():
            self._server_label.setText("  🟢 Server: Running  ")
        else:
            self._server_label.setText("  🔴 Server: Stopped  ")

    # ═══════════════════════════════════════════════════════
    #  Cleanup
    # ═══════════════════════════════════════════════════════

    def closeEvent(self, event):
        self._save_tree_to_storage()
        for w in self._active_workers:
            w.quit()
            w.wait(1000)
        super().closeEvent(event)