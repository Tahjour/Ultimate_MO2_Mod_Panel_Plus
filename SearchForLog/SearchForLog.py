"""
MO2 Log Search — инъекция поиска в панель логов

Установка: <MO2>/plugins/log_search.py
"""

import mobase

try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QMainWindow,
        QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QCheckBox,
        QFrame, QTreeView, QDockWidget,
    )
    from PyQt6.QtCore import Qt, QTimer, QModelIndex, QItemSelectionModel
    from PyQt6.QtGui import QIcon
    PYQT = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QMainWindow,
        QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QCheckBox,
        QFrame, QTreeView, QDockWidget,
    )
    from PyQt5.QtCore import Qt, QTimer, QModelIndex, QItemSelectionModel
    from PyQt5.QtGui import QIcon
    PYQT = 5


def log(msg):
    print(f"[LogSearch] {msg}", flush=True)


class LogSearchBar(QWidget):

    def __init__(self, tree_view: QTreeView, parent=None):
        super().__init__(parent)
        self._tree = tree_view
        self._matches = []
        self._current = -1
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(28)

        h = QHBoxLayout(self)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(4)

        h.addWidget(QLabel("Search:"))

        self._input = QLineEdit()
        self._input.setPlaceholderText("type to search…")
        self._input.setClearButtonEnabled(True)
        self._input.textChanged.connect(self._search)
        self._input.returnPressed.connect(self._next)
        h.addWidget(self._input, 1)

        self._lbl = QLabel("")
        self._lbl.setFixedWidth(60)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self._lbl)

        self._bp = QPushButton("▲")
        self._bp.setFixedWidth(24)
        self._bp.clicked.connect(self._prev)
        h.addWidget(self._bp)

        self._bn = QPushButton("▼")
        self._bn.setFixedWidth(24)
        self._bn.clicked.connect(self._next)
        h.addWidget(self._bn)

        self._cc = QCheckBox("Aa")
        self._cc.setToolTip("Case sensitive")
        self._cc.toggled.connect(self._search)
        h.addWidget(self._cc)

    def _search(self, *_):
        self._clear()
        q = self._input.text().strip()
        if not q:
            self._upd()
            return
        m = self._tree.model()
        if not m:
            return
        cs = self._cc.isChecked()
        if not cs:
            q = q.lower()
        self._walk(m, QModelIndex(), q, cs)
        if self._matches:
            self._current = 0
            self._goto()
        self._upd()

    def _walk(self, m, parent, q, cs):
        for r in range(m.rowCount(parent)):
            hit = False
            for c in range(m.columnCount(parent)):
                idx = m.index(r, c, parent)
                t = m.data(idx, Qt.ItemDataRole.DisplayRole)
                if t is None:
                    continue
                t = str(t)
                cmp = t if cs else t.lower()
                if q in cmp and not hit:
                    self._matches.append(m.index(r, 0, parent))
                    hit = True
            child = m.index(r, 0, parent)
            if m.hasChildren(child):
                self._walk(m, child, q, cs)

    def _next(self):
        if not self._matches:
            return
        self._current = (self._current + 1) % len(self._matches)
        self._goto()
        self._upd()

    def _prev(self):
        if not self._matches:
            return
        self._current = (self._current - 1) % len(self._matches)
        self._goto()
        self._upd()

    def _goto(self):
        if self._current < 0 or self._current >= len(self._matches):
            return
        idx = self._matches[self._current]
        p = idx.parent()
        while p.isValid():
            self._tree.expand(p)
            p = p.parent()
        sm = self._tree.selectionModel()
        if sm:
            sm.setCurrentIndex(
                idx,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        self._tree.scrollTo(idx, QTreeView.ScrollHint.PositionAtCenter)

    def _clear(self):
        self._matches = []
        self._current = -1
        sm = self._tree.selectionModel()
        if sm:
            sm.clearSelection()

    def _upd(self):
        n = len(self._matches)
        if n == 0:
            self._lbl.setText("0" if self._input.text().strip() else "")
        else:
            self._lbl.setText(f"{self._current + 1}/{n}")
        self._bp.setEnabled(n > 0)
        self._bn.setEnabled(n > 0)


def _find_window():
    app = QApplication.instance()
    if not app:
        return None
    for w in app.topLevelWidgets():
        if w.isVisible() and isinstance(w, QMainWindow):
            return w
    return None


def _inject(window):
    tree = window.findChild(QTreeView, "logList")
    if not tree:
        return None

    container = tree.parent()
    if not container:
        return None

    for child in container.children():
        if isinstance(child, LogSearchBar):
            return child

    bar = LogSearchBar(tree, container)

    lay = container.layout()
    if lay:
        idx = lay.indexOf(tree)
        lay.insertWidget(max(idx, 0), bar)
    else:
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(bar)
        lay.addWidget(tree)
        container.setLayout(lay)

    log("✅ SearchBar инжектирован в logDock")
    return bar


class LogSearchPlugin(mobase.IPluginTool):

    def __init__(self):
        super().__init__()
        self._bar = None
        self._n = 0

    def init(self, organizer):
        QTimer.singleShot(3000, self._try)
        return True

    def _try(self):
        self._n += 1
        w = _find_window()
        if w:
            self._bar = _inject(w)
        if not self._bar and self._n < 20:
            QTimer.singleShot(2000, self._try)

    def name(self):        return "LogSearch"
    def author(self):      return "A"
    def description(self): return "Search in log panel"
    def version(self):
        try:    return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)
        except: return mobase.VersionInfo(1, 0, 0)
    def settings(self):    return []
    def displayName(self): return "Log Search"
    def tooltip(self):     return "Search in log panel"
    def icon(self):        return QIcon()
    def display(self):     pass


def createPlugin():
    return LogSearchPlugin()