import traceback
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, Set
import json
from pathlib import Path

from PyQt6.QtCore import (
	Qt, QPoint, QEvent, QTimer, pyqtSignal, QObject, QItemSelectionModel,
	QSettings
)
from PyQt6.QtGui import (
	QIcon, QColor, QBrush, QKeySequence, QShortcut,
	QAction, QPainter, QPolygon, QCursor, QFont, QPalette
)
from PyQt6.QtWidgets import (
	QDockWidget, QVBoxLayout, QHBoxLayout, QSplitter,
	QTreeWidget, QTreeWidgetItem, QAbstractItemView,
	QPushButton, QLabel, QFrame, QToolBar,
	QHeaderView, QWidget, QApplication, QLineEdit, QTreeView, QMainWindow,
	QMenu
)

import mobase

try:
    from PyQt6 import sip
except ImportError:
    try:
        import sip
    except ImportError:
        sip = None

def safe_log(msg, *a):
    return None


def safe_log_err(msg, *a):
    return None


def _is_alive(obj) -> bool:
    if obj is None:
        return False
    try:
        if sip is not None:
            return not sip.isdeleted(obj)
    except Exception:
        pass
    try:
        obj.objectName()
        return True
    except (RuntimeError, AttributeError):
        return False


# ============================================================
#  Constants
# ============================================================

SEPARATOR_SUFFIX = "_separator"
COL_NAME = 0
COL_PRI = 1


# ============================================================
#  Safe MO2 API Wrapper
# ============================================================

class SafeModList:
    def __init__(self, ml):
        self._ml = ml

    def all_mods(self) -> List[str]:
        try:
            return [str(m) for m in self._ml.allMods()]
        except Exception as e:
            safe_log_err("all_mods FAILED: %s", e)
            return []

    def priority(self, name: str) -> int:
        try:
            return int(self._ml.priority(name))
        except Exception:
            return -1

    def is_active(self, name: str) -> bool:
        try:
            s = int(self._ml.state(name))
            try:
                return bool(s & int(mobase.ModState.ACTIVE))
            except (AttributeError, TypeError):
                return bool(s & 0x2)
        except Exception:
            return True

    def set_priority(self, name: str, pri: int) -> bool:
        try:
            self._ml.setPriority(name, int(pri))
            return True
        except Exception as e:
            safe_log_err("set_priority('%s', %d) FAILED: %s", name, pri, e)
            return False


# ============================================================
#  Data Structures
# ============================================================

@dataclass
class ModInfo:
    name: str
    priority: int
    enabled: bool
    is_separator: bool
    display_name: str


@dataclass
class MoveOperation:
    mod_names: List[str]
    old_order: List[str]
    new_order: List[str]
    description: str


class HistoryManager:
    def __init__(self, max_size: int = 50):
        self._undo: List[MoveOperation] = []
        self._redo: List[MoveOperation] = []
        self._max = max_size

    def push(self, op: MoveOperation):
        self._undo.append(op)
        self._redo.clear()
        if len(self._undo) > self._max:
            self._undo.pop(0)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Optional[MoveOperation]:
        if not self._undo:
            return None
        op = self._undo.pop()
        self._redo.append(op)
        return op

    def redo(self) -> Optional[MoveOperation]:
        if not self._redo:
            return None
        op = self._redo.pop()
        self._undo.append(op)
        return op

    def get_undo_desc(self) -> str:
        return self._undo[-1].description if self._undo else ""

    def get_redo_desc(self) -> str:
        return self._redo[-1].description if self._redo else ""

    def clear(self):
        self._undo.clear()
        self._redo.clear()


# ============================================================
#  Mod Data Cache
# ============================================================

class ModDataCache:
    def __init__(self, sml: SafeModList):
        self._ml = sml
        self._mods: List[ModInfo] = []
        self._by_name: Dict[str, ModInfo] = {}

    def refresh(self) -> bool:
        try:
            self._mods.clear()
            self._by_name.clear()
            for name in self._ml.all_mods():
                try:
                    pri = self._ml.priority(name)
                    ena = self._ml.is_active(name)
                    sep = name.endswith(SEPARATOR_SUFFIX)
                    dn = name[:-len(SEPARATOR_SUFFIX)] if sep else name
                    info = ModInfo(name, pri, ena, sep, dn)
                    self._mods.append(info)
                    self._by_name[name] = info
                except Exception:
                    continue
            self._mods.sort(key=lambda x: x.priority)
            return True
        except Exception as e:
            safe_log_err("Cache refresh FAILED: %s", e)
            return False

    def get_sorted(self) -> List[ModInfo]:
        return list(self._mods)

    def get_order(self) -> List[str]:
        return [m.name for m in self._mods]

    def get(self, name: str) -> Optional[ModInfo]:
        return self._by_name.get(name)

    def exists(self, name: str) -> bool:
        return name in self._by_name

    def is_separator(self, name: str) -> bool:
        i = self._by_name.get(name)
        return i.is_separator if i else False


# ============================================================
#  Mod Mover
# ============================================================

class ModMover:
    def __init__(self, sml: SafeModList, cache: ModDataCache):
        self._ml = sml
        self._cache = cache
        self._history = HistoryManager()
        self._initial_order: List[str] = list(cache.get_order())

    @property
    def history(self) -> HistoryManager:
        return self._history

    @property
    def has_changes(self) -> bool:
        return self._cache.get_order() != self._initial_order

    def move(self, mod_names: List[str], target: str, after: bool) -> bool:
        if not mod_names or not target:
            return False
        try:
            old_order = self._cache.get_order()
            to_move_raw = self._expand(mod_names)

            pri_map: Dict[str, int] = {}
            for m in self._cache.get_sorted():
                pri_map[m.name] = m.priority

            to_move = sorted(to_move_raw, key=lambda n: pri_map.get(n, 0))
            move_set = set(to_move)

            if target in move_set:
                safe_log("Target '%s' is in move set, abort", target)
                return False
            if not self._cache.exists(target):
                safe_log_err("Target '%s' not found", target)
                return False

            remaining = [n for n in old_order if n not in move_set]

            try:
                target_idx = remaining.index(target)
            except ValueError:
                safe_log_err("Target '%s' not in remaining list", target)
                return False

            insert_idx = target_idx + (1 if after else 0)
            new_order = (
                remaining[:insert_idx] + to_move + remaining[insert_idx:]
            )

            safe_log(
                "Moving %d mods, insert at index %d (after=%s)",
                len(to_move), insert_idx, after
            )

            if not self._apply_order(new_order):
                return False

            self._history.push(MoveOperation(
                to_move, old_order, new_order,
                f"Move {len(to_move)} mod(s)"
            ))
            return True
        except Exception as e:
            safe_log_err("Move FAILED: %s\n%s", e, traceback.format_exc())
            self._cache.refresh()
            return False

    def _expand(self, names: List[str]) -> List[str]:
        result: List[str] = []
        seen: Set[str] = set()
        for n in names:
            if n not in seen:
                seen.add(n)
                result.append(n)
            if self._cache.is_separator(n):
                for c in self._sep_contents(n):
                    if c not in seen:
                        seen.add(c)
                        result.append(c)
        return result

    def _sep_contents(self, sep: str) -> List[str]:
        out: List[str] = []
        inside = False
        for m in self._cache.get_sorted():
            if m.name == sep:
                inside = True
                continue
            if inside:
                if m.is_separator:
                    break
                out.append(m.name)
        return out

    def undo(self) -> bool:
        op = self._history.undo()
        if not op:
            return False
        return self._apply_order(op.old_order)

    def redo(self) -> bool:
        op = self._history.redo()
        if not op:
            return False
        return self._apply_order(op.new_order)

    def _apply_order(self, order: List[str]) -> bool:
        """FIX: только изменённые приоритеты."""
        try:
            # ── Построить карту текущих приоритетов ──
            current_pri: Dict[str, int] = {}
            for m in self._cache.get_sorted():
                current_pri[m.name] = m.priority

            # ── Установить приоритет ТОЛЬКО для изменившихся ──
            changed = 0
            total = len(order)
            for new_pri, name in enumerate(order):
                old_pri = current_pri.get(name, -1)
                if old_pri != new_pri:
                    self._ml.set_priority(name, new_pri)
                    changed += 1

            self._cache.refresh()
            safe_log("Apply order: %d/%d changed", changed, total)
            return True
        except Exception as e:
            safe_log_err("Apply order FAILED: %s", e)
            self._cache.refresh()
            return False


# ============================================================
#  ModTreeWidget
# ============================================================

class ModTreeWidget(QTreeWidget):

    modsDropped = pyqtSignal(list, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setDragEnabled(False)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.DropAction.IgnoreAction)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self._ind_name: Optional[str] = None
        self._ind_after: bool = True
        self._item_map: Dict[str, QTreeWidgetItem] = {}
        self._ext_sel_provider = None

    def set_item_map(self, m: Dict[str, QTreeWidgetItem]):
        self._item_map = m

    def enable_external_drop(self, provider):
        self._ext_sel_provider = provider

    def show_indicator(self, mod_name: str, after: bool):
        if self._ind_name != mod_name or self._ind_after != after:
            self._ind_name = mod_name
            self._ind_after = after
            self.viewport().update()

    def hide_indicator(self):
        if self._ind_name is not None:
            self._ind_name = None
            self.viewport().update()

    @property
    def indicator_name(self) -> Optional[str]:
        return self._ind_name

    @property
    def indicator_after(self) -> bool:
        return self._ind_after

    def mod_at_pos(self, pos: QPoint) -> Optional[Tuple[str, bool]]:
        item = self.itemAt(pos)
        if item is None:
            return None
        name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if not name:
            return None
        rect = self.visualItemRect(item)
        after = pos.y() > rect.center().y()
        return name, after

    def get_selected_mod_names(self) -> List[str]:
        items = self.selectedItems()
        if not items:
            return []

        item_order: List[Tuple[Tuple[int, int], str]] = []
        for item in items:
            n = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if not n:
                continue
            parent = item.parent()
            if parent:
                top_row = self.indexOfTopLevelItem(parent)
                child_row = parent.indexOfChild(item)
                order_key = (top_row, child_row + 1)
            else:
                top_row = self.indexOfTopLevelItem(item)
                order_key = (top_row, 0)
            item_order.append((order_key, n))

        item_order.sort(key=lambda x: x[0])

        result: List[str] = []
        seen: Set[str] = set()
        for _, name in item_order:
            if name not in seen:
                result.append(name)
                seen.add(name)
            item = self._item_map.get(name)
            try:
                if item is not None and item.parent() is None and item.childCount() > 0:
                    for j in range(item.childCount()):
                        ch = item.child(j)
                        if ch is None:
                            continue
                        cname = ch.data(COL_NAME, Qt.ItemDataRole.UserRole)
                        if isinstance(cname, str) and cname and cname not in seen:
                            result.append(cname)
                            seen.add(cname)
            except Exception:
                pass
        return result

    def scroll_to_mod(self, mod_name: str, select: bool = True):
        item = self._item_map.get(mod_name)
        if item is None:
            return
        parent = item.parent()
        if parent and not parent.isExpanded():
            parent.setExpanded(True)
        self.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
        if select:
            self.setCurrentItem(item)

    def find_mod_by_text(
        self, text: str, start_after: Optional[str] = None
    ) -> Tuple[Optional[str], bool]:
        if not text:
            return None, False

        text_lower = text.lower()
        found_start = (start_after is None)

        all_items = self._collect_all_items()

        for name, display in all_items:
            if not found_start:
                if name == start_after:
                    found_start = True
                continue
            if text_lower in name.lower():
                return name, False
            if display and text_lower in display.lower():
                return name, False

        if start_after is not None:
            for name, display in all_items:
                if name == start_after:
                    break
                if text_lower in name.lower():
                    return name, True
                if display and text_lower in display.lower():
                    return name, True

        return None, False

    def _collect_all_items(self) -> List[Tuple[str, str]]:
        result: List[Tuple[str, str]] = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            if top is None:
                continue
            name = top.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if name:
                result.append((name, top.text(COL_NAME)))
            for j in range(top.childCount()):
                child = top.child(j)
                if child is None:
                    continue
                cname = child.data(COL_NAME, Qt.ItemDataRole.UserRole)
                if cname:
                    result.append((cname, child.text(COL_NAME)))
        return result

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._ind_name:
            try:
                self._draw_indicator()
            except Exception:
                pass

    def _draw_indicator(self):
        item = self._item_map.get(self._ind_name)
        if item is None:
            return
        rect = self.visualItemRect(item)
        if not rect.isValid():
            return

        vp = self.viewport()
        painter = QPainter(vp)
        try:
            y = rect.bottom() + 1 if self._ind_after else rect.top()
            w = vp.width()

            color = self.palette().color(QPalette.ColorRole.Highlight)
            pen = painter.pen()
            pen.setColor(color)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawLine(0, y, w, y)

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            s = 6
            painter.drawPolygon(QPolygon([
                QPoint(0, y - s), QPoint(s * 2, y), QPoint(0, y + s)
            ]))
            painter.drawPolygon(QPolygon([
                QPoint(w, y - s), QPoint(w - s * 2, y), QPoint(w, y + s)
            ]))
        finally:
            painter.end()

    def dragEnterEvent(self, event):
        try:
            event.acceptProposedAction()
        except Exception:
            event.ignore()

    def dragMoveEvent(self, event):
        try:
            info = self.mod_at_pos(event.position().toPoint())
            if info:
                self.show_indicator(info[0], info[1])
            else:
                self.hide_indicator()
            event.acceptProposedAction()
        except Exception:
            event.ignore()

    def dropEvent(self, event):
        try:
            info = self.mod_at_pos(event.position().toPoint())
            if not info:
                self.hide_indicator()
                event.ignore()
                return
            target, after = info
            mods = []
            if callable(self._ext_sel_provider):
                try:
                    mods = list(self._ext_sel_provider()) or []
                except Exception:
                    mods = []
            if not mods:
                mods = self.get_selected_mod_names()
            if not mods:
                event.ignore()
                return
            self.modsDropped.emit(mods, target, after)
            event.acceptProposedAction()
        finally:
            self.hide_indicator()


# ============================================================
#  DragDropManager
# ============================================================

class DragDropManager(QObject):

    modsDropped = pyqtSignal(list, str, bool)

    SCROLL_MARGIN = 30
    SCROLL_STEP = 3

    def __init__(self, left: ModTreeWidget, right: ModTreeWidget,
                 parent=None):
        super().__init__(parent)
        uniq: List[ModTreeWidget] = []
        for t in (left, right):
            if t is not None and all(t is not x for x in uniq):
                uniq.append(t)
        self._trees: List[ModTreeWidget] = uniq
        self._viewports: List[QWidget] = []
        self._dragging = False
        self._source: Optional[ModTreeWidget] = None
        self._start_gpos: Optional[QPoint] = None
        self._cursor_set = False
        self._destroyed = False
        self._sel_snapshot: Optional[List[str]] = None

        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(50)
        self._scroll_timer.timeout.connect(self._on_scroll_tick)
        self._scroll_target: Optional[ModTreeWidget] = None
        self._scroll_dir = 0

        for t in self._trees:
            vp = t.viewport()
            self._viewports.append(vp)
            vp.installEventFilter(self)
            t.destroyed.connect(self._on_tree_destroyed)

    def cleanup(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._scroll_timer.stop()
        self._set_cursor(False)
        for vp in self._viewports:
            try:
                if _is_alive(vp):
                    vp.removeEventFilter(self)
            except Exception:
                pass
        self._trees.clear()
        self._viewports.clear()
        self._source = None
        self._dragging = False

    def _on_tree_destroyed(self):
        self.cleanup()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self._destroyed:
            return False
        try:
            tree = self._viewport_to_tree(obj)
            if tree is None:
                return False
            return self._handle(tree, event)
        except RuntimeError:
            safe_log_err("eventFilter: C++ object deleted")
            self.cleanup()
            return False
        except Exception:
            safe_log_err("eventFilter error:\n%s", traceback.format_exc())
            self._abort()
            return False

    def _handle(self, tree: ModTreeWidget, event: QEvent) -> bool:
        t = event.type()

        if t == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._start_gpos = _gpos(event)
                self._source = tree
                try:
                    item = tree.itemAt(event.pos())
                    if item is not None and item.isSelected():
                        self._sel_snapshot = tree.get_selected_mod_names()
                    else:
                        self._sel_snapshot = None
                except Exception:
                    self._sel_snapshot = None
            return False

        if t == QEvent.Type.MouseMove:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return False
            if self._source is None or self._start_gpos is None:
                return False

            if not self._dragging:
                gp = _gpos(event)
                dist = (gp - self._start_gpos).manhattanLength()
                if dist < QApplication.startDragDistance():
                    return False
                sel = self._sel_snapshot or self._source.get_selected_mod_names()
                if not sel:
                    return False
                self._dragging = True
                self._set_cursor(True)
                safe_log("Drag started: %d mods selected", len(sel))

            self._update(_gpos(event))
            return True

        if t == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._dragging:
                try:
                    self._drop()
                finally:
                    self._abort()
                return True
            self._start_gpos = None
            self._source = None
            return False

        if t == QEvent.Type.KeyPress:
            if self._dragging and event.key() == Qt.Key.Key_Escape:
                self._abort()
                return True

        return False

    def _update(self, gpos: QPoint):
        if self._destroyed:
            return
        for t in self._trees:
            try:
                if _is_alive(t):
                    t.hide_indicator()
            except RuntimeError:
                self.cleanup()
                return

        self._scroll_dir = 0
        self._scroll_target = None

        target_tree, local = self._tree_at(gpos)
        if target_tree is None:
            self._scroll_timer.stop()
            return

        try:
            info = target_tree.mod_at_pos(local)
            if info:
                target_tree.show_indicator(info[0], info[1])

            vp_h = target_tree.viewport().height()
            if local.y() < self.SCROLL_MARGIN:
                self._scroll_target = target_tree
                self._scroll_dir = -1
                if not self._scroll_timer.isActive():
                    self._scroll_timer.start()
            elif local.y() > vp_h - self.SCROLL_MARGIN:
                self._scroll_target = target_tree
                self._scroll_dir = 1
                if not self._scroll_timer.isActive():
                    self._scroll_timer.start()
            else:
                self._scroll_timer.stop()
        except RuntimeError:
            self.cleanup()

    def _on_scroll_tick(self):
        if self._destroyed:
            self._scroll_timer.stop()
            return
        try:
            if (self._scroll_target and self._scroll_dir
                    and _is_alive(self._scroll_target)):
                sb = self._scroll_target.verticalScrollBar()
                sb.setValue(
                    sb.value() + self._scroll_dir * self.SCROLL_STEP
                )
                gp = QCursor.pos()
                target, local = self._tree_at(gp)
                if target is self._scroll_target:
                    info = target.mod_at_pos(local)
                    if info:
                        target.show_indicator(info[0], info[1])
        except RuntimeError:
            self._scroll_timer.stop()
            self.cleanup()
        except Exception:
            self._scroll_timer.stop()

    def _drop(self):
        if self._destroyed or self._source is None:
            return

        target_name: Optional[str] = None
        after = True

        try:
            for t in self._trees:
                if _is_alive(t) and t.indicator_name:
                    target_name = t.indicator_name
                    after = t.indicator_after
                    break
        except RuntimeError:
            self.cleanup()
            return

        if not target_name:
            return

        try:
            mod_names = self._sel_snapshot or self._source.get_selected_mod_names()
        except RuntimeError:
            self.cleanup()
            return

        if not mod_names:
            return

        safe_log("Drop: %d mods -> '%s' (after=%s)",
                 len(mod_names), target_name, after)
        self.modsDropped.emit(mod_names, target_name, after)

    def _abort(self):
        self._scroll_timer.stop()
        self._scroll_target = None
        self._scroll_dir = 0
        if not self._destroyed:
            for t in self._trees:
                try:
                    if _is_alive(t):
                        t.hide_indicator()
                except RuntimeError:
                    pass
        self._set_cursor(False)
        self._dragging = False
        self._source = None
        self._start_gpos = None
        self._sel_snapshot = None

    def _set_cursor(self, on: bool):
        try:
            if on and not self._cursor_set:
                QApplication.setOverrideCursor(
                    Qt.CursorShape.ClosedHandCursor
                )
                self._cursor_set = True
            elif not on and self._cursor_set:
                QApplication.restoreOverrideCursor()
                self._cursor_set = False
        except Exception:
            self._cursor_set = False

    def _viewport_to_tree(self, obj) -> Optional[ModTreeWidget]:
        if self._destroyed:
            return None
        for i, vp in enumerate(self._viewports):
            try:
                if obj is vp and _is_alive(self._trees[i]):
                    return self._trees[i]
            except (RuntimeError, IndexError):
                pass
        return None

    def _tree_at(self, gpos: QPoint) -> Tuple[
        Optional[ModTreeWidget], QPoint
    ]:
        if self._destroyed:
            return None, QPoint()
        for t in self._trees:
            try:
                if not _is_alive(t):
                    continue
                vp = t.viewport()
                local = vp.mapFromGlobal(gpos)
                if vp.rect().contains(local):
                    return t, local
            except RuntimeError:
                continue
        return None, QPoint()


def _gpos(event) -> QPoint:
    try:
        return event.globalPosition().toPoint()
    except AttributeError:
        pass
    try:
        return event.globalPos()
    except AttributeError:
        pass
    return QCursor.pos()
    
    
# ============================================================
#  Panel Widget (with search)
# ============================================================

class PanelWidget(QFrame):

    def __init__(self, cache: ModDataCache, title: str,
                 parent=None, dock_ref=None):  # FIX: добавлен dock_ref
        super().__init__(parent)
        self._cache = cache
        self._title = title
        self._dock_ref = dock_ref  # FIX: ссылка на dock для доступа к _ml_view
        self._last_search: Optional[str] = None
        self._last_found: Optional[str] = None
        self._persist_expanded: Optional[Set[str]] = None
        self._persist_select: Optional[str] = None
        self._highlight: Set[str] = set()
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        self._label = QLabel(self._title)
        layout.addWidget(self._label)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Quick search... (Enter=find, F3=next)"
        )
        self._search.setClearButtonEnabled(True)
        self._search.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search)

        btn_next = QPushButton(">>")
        btn_next.setFixedWidth(32)
        btn_next.setToolTip("Find next (F3)")
        btn_next.clicked.connect(self._on_search_next)
        search_layout.addWidget(btn_next)

        layout.addLayout(search_layout)

        # F3 shortcut — ограничен контекстом этого виджета
        self._shortcut_f3 = QShortcut(QKeySequence(Qt.Key.Key_F3), self)
        self._shortcut_f3.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )  # FIX: ограничен контекстом
        self._shortcut_f3.activated.connect(self._on_search_next)

        # Tree
        self._tree = ModTreeWidget(self)
        self._tree.setHeaderLabels(["Name", "Pri"])
        self._tree.setColumnCount(2)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setAnimated(False)

        h = self._tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(1, 55)

        layout.addWidget(self._tree)
        try:
            self._tree.enable_external_drop(self._external_selected_mods)
        except Exception:
            pass

        # Info
        self._info = QLabel("")
        layout.addWidget(self._info)

    def _on_search(self):
        text = self._search.text().strip()
        if not text:
            return

        self._last_search = text
        found, wrapped = self._tree.find_mod_by_text(text, None)
        if found:
            self._last_found = found
            self._tree.scroll_to_mod(found)
        else:
            self._last_found = None

    def _on_search_next(self):
        text = self._search.text().strip()
        if not text:
            return

        self._last_search = text
        found, wrapped = self._tree.find_mod_by_text(text, self._last_found)
        if found:
            self._last_found = found
            self._tree.scroll_to_mod(found)
        else:
            self._last_found = None

    @staticmethod
    def _make_item(text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(COL_NAME, text)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        return item

    def populate(self):
        tree = self._tree
        try:
            tree.setUpdatesEnabled(False)
        except Exception:
            tree = None
        try:
            expanded = (
                self._persist_expanded
                if self._persist_expanded is not None
                else self._get_expanded()
            )
            self._tree.hide_indicator()
            self._tree.set_item_map({})
            self._tree.clear()

            item_map: Dict[str, QTreeWidgetItem] = {}
            cur_sep: Optional[QTreeWidgetItem] = None
            mc = sc = 0

            for m in self._cache.get_sorted():
                try:
                    if m.is_separator:
                        item = self._make_item("[S] " + m.display_name)
                        item.setText(COL_PRI, str(m.priority))
                        item.setData(
                            COL_NAME, Qt.ItemDataRole.UserRole, m.name
                        )
                        self._tree.addTopLevelItem(item)
                        item_map[m.name] = item
                        cur_sep = item
                        sc += 1
                    else:
                        item = self._make_item(m.display_name)
                        item.setText(COL_PRI, str(m.priority))
                        item.setData(
                            COL_NAME, Qt.ItemDataRole.UserRole, m.name
                        )
                        if m.name in self._highlight:
                            f = item.font(COL_NAME)
                            f.setBold(True)
                            item.setFont(COL_NAME, f)
                            item.setFont(COL_PRI, f)
                        if cur_sep is not None:
                            cur_sep.addChild(item)
                        else:
                            self._tree.addTopLevelItem(item)
                        item_map[m.name] = item
                        mc += 1
                except Exception:
                    continue

            self._tree.set_item_map(item_map)
            self._restore_expanded(expanded)
            self._persist_expanded = None
            if self._persist_select:
                try:
                    self._tree.scroll_to_mod(self._persist_select)
                except Exception:
                    pass
                self._persist_select = None
            self._info.setText(f"{mc} mods, {sc} separators")
        except Exception as e:
            safe_log_err("populate FAILED: %s\n%s",
                         e, traceback.format_exc())
        finally:
            if tree is not None:
                try:
                    tree.setUpdatesEnabled(True)
                except Exception:
                    pass

    def _external_selected_mods(self) -> List[str]:
        # FIX: используем dock_ref вместо self.parent()
        try:
            owner = self._dock_ref
            if owner is None:
                return []
            mlv = getattr(owner, "_ml_view", None)
            if mlv is None or mlv.selectionModel() is None:
                return []
            sel = mlv.selectionModel().selectedRows()
            out: List[str] = []
            name_exists = self._cache.exists
            display_to_real: Dict[str, str] = {}
            try:
                for m in self._cache.get_sorted():
                    display_to_real[m.display_name] = m.name
            except Exception:
                pass
            for idx in sel:
                try:
                    text = str(idx.data())
                    name = None
                    if text:
                        if name_exists(text):
                            name = text
                        elif name_exists(text + SEPARATOR_SUFFIX):
                            name = text + SEPARATOR_SUFFIX
                        else:
                            name = display_to_real.get(text)
                    if name:
                        out.append(name)
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def _get_expanded(self) -> Set[str]:
        result: Set[str] = set()
        try:
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                if item and item.isExpanded():
                    n = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
                    if n:
                        result.add(n)
        except Exception:
            pass
        return result

    def _restore_expanded(self, names: Set[str]):
        try:
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                if item:
                    n = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
                    if n and n in names:
                        item.setExpanded(True)
        except Exception:
            pass

    def tree(self) -> ModTreeWidget:
        return self._tree

    def set_persisted_expanded(self, names: Set[str]):
        self._persist_expanded = set(names) if names else set()

    def set_persisted_select(self, name: Optional[str]):
        self._persist_select = name if name else None

    def get_expanded_names(self) -> Set[str]:
        return self._get_expanded()

    def set_highlighted(self, names: Set[str]):
        try:
            self._highlight = set(names) if names else set()
        except Exception:
            self._highlight = set()

    def expand_all(self):
        try:
            self._tree.expandAll()
        except Exception:
            pass

    def collapse_all(self):
        try:
            self._tree.collapseAll()
        except Exception:
            pass

    def focus(self):
        try:
            self._tree.setFocus()
        except Exception:
            pass


# ============================================================
#  Main Dock
# ============================================================

class DualPanelDock(QDockWidget):

    _DOCK_STATE_VERSION = 42

    def __init__(self, organizer, main_window,
                 plugin_name: str = "Mod migration"):
        super().__init__("Mod migration", main_window)
        self.setObjectName("holyModMigrationDock")
        safe_log("=== Dock init START ===")

        try:
            self._org = organizer
            self._pname = plugin_name
            self._sml = SafeModList(organizer.modList())
            self._cache = ModDataCache(self._sml)
            self._cache.refresh()
            self._mover = ModMover(self._sml, self._cache)
            self._ddm: Optional[DragDropManager] = None
            self._ml_view: Optional[QTreeView] = None
            self._persist_expanded: Set[str] = set()
            self._persist_select: Optional[str] = None
            self._moved_highlight: Set[str] = set()
            self._poll_timer: Optional[QTimer] = None
            self._ml_fingerprint: int = 0
            self._suppress_next_poll: bool = False
            self._initialized = False

            self._in_operation = False
            self._pending_refresh = False
            self._refresh_timer: Optional[QTimer] = None

            self._expanded = False
            self._target_width = 480
            self._collapsed_width = 24
            self._save_width_timer: Optional[QTimer] = None
            self._save_geom_timer: Optional[QTimer] = None
            self._target_geometry = None
            self._persisted_geometry = None
            self._suppress_resize_save = False
            self._suppress_resize_timer: Optional[QTimer] = None
            self._expanding = False
            self._expand_fix_timer: Optional[QTimer] = None
            self._expand_release_timer: Optional[QTimer] = None
            self._expand_restore_min = None
            self._settings = QSettings("ModOrganizer2", "HolyModMigration")
            self._save_state_timer = QTimer(self)
            self._save_state_timer.setSingleShot(True)
            self._save_state_timer.setInterval(2000)
            self._save_state_timer.timeout.connect(self._do_save_dock_state)
            self._programmatic_float = False

            self._root = QWidget()
            self._content = QWidget(self._root)
            self._slider = QPushButton(self._root)
            self._slider.setText("<")
            self._slider.setFixedWidth(16)
            self._slider.setFlat(True)

            h = QHBoxLayout(self._root)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            h.addWidget(self._content)
            h.addWidget(self._slider)

            self._setup_ui(self._content)
            self.setWidget(self._root)

            self._content.hide()

            self.setMinimumWidth(self._collapsed_width)
            self.setMaximumWidth(self._collapsed_width)

            self._slider.clicked.connect(self.toggle_panel)
            self.visibilityChanged.connect(self._on_visibility_changed)
            try:
                self.topLevelChanged.connect(self._on_top_level_changed)
            except Exception:
                pass
            try:
                app = QApplication.instance()
                if app is not None:
                    app.aboutToQuit.connect(self._on_app_about_to_quit)
            except Exception:
                pass
            self._setup_shortcuts()
            self._load_persisted_state()

        except Exception as e:
            safe_log_err("Dock init FAILED: %s\n%s",
                         e, traceback.format_exc())

        safe_log("=== Dock init END ===")

    def _find_main_window(self) -> Optional[QMainWindow]:
        try:
            w = self.parent()
            while w is not None:
                if isinstance(w, QMainWindow):
                    return w
                w = w.parent()
        except Exception:
            pass
        try:
            app = QApplication.instance()
            if app is not None:
                for tw in app.topLevelWidgets():
                    if isinstance(tw, QMainWindow) and tw.isVisible():
                        return tw
        except Exception:
            pass
        return None

    def _do_save_dock_state(self):
        try:
            mw = self._find_main_window()
            if mw is None:
                return
            try:
                state = mw.saveState(self._DOCK_STATE_VERSION)
            except Exception:
                return
            try:
                self._settings.setValue("DockState/mainWindowState", state)
                self._settings.setValue("DockState/wasExpanded", bool(self._expanded))
                self._settings.setValue("DockState/targetWidth", int(self._target_width))
                self._settings.sync()
            except Exception:
                pass
        except Exception:
            pass

    def _restore_dock_state_late(self):
        try:
            mw = self._find_main_window()
            if mw is None:
                return
            state = self._settings.value("DockState/mainWindowState", None)
            if state is None:
                return
            try:
                old_min = self.minimumWidth()
            except Exception:
                old_min = None
            try:
                old_max = self.maximumWidth()
            except Exception:
                old_max = None
            try:
                self.setMinimumWidth(0)
                self.setMaximumWidth(16777215)
            except Exception:
                pass
            try:
                mw.restoreState(state, self._DOCK_STATE_VERSION)
            except Exception:
                pass
            try:
                if old_min is not None:
                    self.setMinimumWidth(old_min)
                if old_max is not None:
                    self.setMaximumWidth(old_max)
            except Exception:
                pass
            try:
                was_expanded = self._settings.value(
                    "DockState/wasExpanded", False, type=bool
                )
            except Exception:
                was_expanded = False
            try:
                tw = self._settings.value(
                    "DockState/targetWidth", 0, type=int
                )
            except Exception:
                tw = 0
            if isinstance(tw, int) and tw > 0:
                self._target_width = tw
            try:
                if was_expanded:
                    self.toggle_panel()
            except Exception:
                pass
        except Exception:
            pass

    # ── Visibility management ──

    def _on_visibility_changed(self, visible: bool):
        try:
            # FIX: не вмешиваться во время операций
            if self._in_operation:
                safe_log("visibility changed during operation — ignored")
                return

            if not visible:
                if not self._initialized:
                    return
                safe_log("Hidden — saving state, stopping poll")
                if self._poll_timer and self._poll_timer.isActive():
                    self._poll_timer.stop()
                self._save_persisted_state()
                if self._mover.has_changes:
                    self._refresh_mo2()
        except Exception as e:
            safe_log_err("_on_visibility_changed FAILED: %s", e)

    def _on_app_about_to_quit(self):
        try:
            safe_log("app quit — saving state")
            if self._expanded:
                w_now = self.width()
                if w_now > self._collapsed_width * 2:
                    self._target_width = w_now
            if self.isFloating():
                try:
                    self._target_geometry = self.geometry()
                except Exception:
                    pass
            self._save_persisted_state()
            self._do_save_width()
            self._do_save_geometry()
            self._do_save_dock_state()
        except Exception as e:
            safe_log_err("_on_app_about_to_quit FAILED: %s", e)

    def _ensure_initialized(self):
        if self._initialized:
            return
        self._initialized = True
        safe_log("First expand — initializing")
        try:
            self._hook_modlist_selection()
            self._left.set_persisted_expanded(self._persist_expanded)
            if self._persist_select:
                self._left.set_persisted_select(self._persist_select)
            self._left.populate()
            self._start_polling()
        except Exception as e:
            safe_log_err("init on expand FAILED: %s", e)

    def toggle_panel(self):
        try:
            safe_log(
                "toggle_panel: expanded=%s width=%s target=%s",
                self._expanded, self.width(), self._target_width
            )
            if self._expanded:
                self._collapse_panel()
            else:
                self._begin_expand()
                self._expand_panel()
        except Exception as e:
            safe_log_err("toggle_panel FAILED: %s", e)

    def _expand_panel(self):
        self._ensure_initialized()
        self._expanded = True
        self._slider.setText(">>")
        self._content.setMaximumWidth(16777215)
        self._content.show()
        min_w = max(200, self._collapsed_width * 2)
        self.setMinimumWidth(min_w)
        self._expand_restore_min = min_w
        w = max(self._target_width, min_w)
        safe_log(
            "expand: min_w=%s target=%s width_before=%s",
            min_w, self._target_width, self.width()
        )
        try:
            if self.width() < w:
                self.resize(w, self.height())
        except Exception:
            pass
        self.setMaximumWidth(16777215)
        safe_log("expand: width_after=%s", self.width())
        self._schedule_expand_resize(w)

    def _collapse_panel(self):
        self._expanded = False
        self._slider.setText("<")
        try:
            w_real = self.width()
            w = max(w_real, self._target_width, self._collapsed_width * 2)
            self._target_width = w
            safe_log(
                "collapse: width_before=%s new_target=%s",
                w_real, self._target_width
            )
        except Exception:
            pass
        try:
            self._content.hide()
            self.setMinimumWidth(self._collapsed_width)
            self.setMaximumWidth(self._collapsed_width)
            self._suppress_resize_saving()
            if self.width() != self._collapsed_width:
                self.resize(self._collapsed_width, self.height())
        except Exception:
            pass
        safe_log("collapse: width_after=%s", self.width())

    def resizeEvent(self, event):
        try:
            try:
                super().resizeEvent(event)
            except Exception:
                QDockWidget.resizeEvent(self, event)
        except Exception:
            pass
        try:
            if self._expanded:
                if not self._suppress_resize_save and not self._expanding:
                    w = self.width()
                    if w > self._collapsed_width * 2:
                        if w != self._target_width:
                            self._target_width = w
                            safe_log("resizeEvent: new_target=%s", w)
                        self._schedule_save_width()
            if self.isFloating():
                try:
                    self._target_geometry = self.geometry()
                except Exception:
                    pass
                self._schedule_save_geometry()
            if not self._expanding and self._save_state_timer is not None:
                self._save_state_timer.start()
        except Exception:
            pass

    def moveEvent(self, event):
        try:
            try:
                super().moveEvent(event)
            except Exception:
                QDockWidget.moveEvent(self, event)
        except Exception:
            pass
        try:
            if self.isFloating():
                try:
                    self._target_geometry = self.geometry()
                except Exception:
                    pass
                self._schedule_save_geometry()
            if self._save_state_timer is not None:
                self._save_state_timer.start()
        except Exception:
            pass

    def _suppress_resize_saving(self, ms: int = 250):
        try:
            self._suppress_resize_save = True
            if self._suppress_resize_timer is None:
                self._suppress_resize_timer = QTimer(self)
                self._suppress_resize_timer.setSingleShot(True)
                self._suppress_resize_timer.timeout.connect(
                    self._clear_resize_suppress
                )
            self._suppress_resize_timer.start(ms)
        except Exception:
            pass

    def _begin_expand(self):
        try:
            self._expanding = True
            self._suppress_resize_saving(400)
            safe_log("begin_expand: target=%s", self._target_width)
        except Exception:
            pass

    def _end_expand(self):
        try:
            if not self._expanding:
                return
            self._expanding = False
            safe_log("end_expand: width=%s target=%s", self.width(), self._target_width)
        except Exception:
            pass

    def _clear_resize_suppress(self):
        try:
            self._suppress_resize_save = False
            safe_log("resize save suppress cleared")
        except Exception:
            pass

    def _schedule_expand_resize(self, w: int):
        try:
            if self._expand_fix_timer is None:
                self._expand_fix_timer = QTimer(self)
                self._expand_fix_timer.setSingleShot(True)
                self._expand_fix_timer.timeout.connect(
                    self._apply_expand_resize
                )
            self._expand_fix_timer._target_w = w
            self._expand_fix_timer.start(0)
        except Exception:
            pass

    def _apply_expand_resize(self):
        try:
            w = getattr(self._expand_fix_timer, "_target_w", None)
            if not self._expanded or w is None:
                return
            safe_log(
                "apply_expand_resize: width_before=%s target=%s",
                self.width(), w
            )
            try:
                mw = self.window()
                if isinstance(mw, QMainWindow):
                    mw.resizeDocks([self], [int(w)], Qt.Orientation.Horizontal)
                    safe_log("apply_expand_resize: resizeDocks applied")
            except Exception:
                pass
            try:
                self.setMinimumWidth(w)
            except Exception:
                pass
            if self.width() < w:
                self.resize(w, self.height())
            safe_log("apply_expand_resize: width_after=%s", self.width())
            self._schedule_expand_min_restore()
        except Exception:
            pass

    def _schedule_expand_min_restore(self):
        try:
            if self._expand_release_timer is None:
                self._expand_release_timer = QTimer(self)
                self._expand_release_timer.setSingleShot(True)
                self._expand_release_timer.timeout.connect(
                    self._restore_expand_min
                )
            self._expand_release_timer.start(300)
        except Exception:
            pass

    def _restore_expand_min(self):
        try:
            if self._expand_restore_min is None:
                return
            self.setMinimumWidth(self._expand_restore_min)
            safe_log("restore_expand_min: min=%s", self._expand_restore_min)
            self._end_expand()
        except Exception:
            pass

    def _schedule_save_width(self):
        try:
            if self._save_width_timer is None:
                self._save_width_timer = QTimer(self)
                self._save_width_timer.setSingleShot(True)
                self._save_width_timer.setInterval(500)
                self._save_width_timer.timeout.connect(self._do_save_width)
            self._save_width_timer.start()
            safe_log("schedule_save_width: target=%s", self._target_width)
        except Exception:
            pass

    def _schedule_save_geometry(self):
        try:
            if self._save_geom_timer is None:
                self._save_geom_timer = QTimer(self)
                self._save_geom_timer.setSingleShot(True)
                self._save_geom_timer.setInterval(500)
                self._save_geom_timer.timeout.connect(self._do_save_geometry)
            self._save_geom_timer.start()
            safe_log("schedule_save_geometry: rect=%s", self._target_geometry)
        except Exception:
            pass

    def _do_save_width(self):
        try:
            w = max(self._target_width, self._collapsed_width * 2)
            safe_log("do_save_width: write=%s", w)
            try:
                self._org.setPluginSetting(self._pname, "panel_width_v2", int(w))
            except Exception:
                pass
        except Exception:
            pass

    def _do_save_geometry(self):
        try:
            rect = self._target_geometry
            if rect is None:
                return
            x = rect.x()
            y = rect.y()
            w = rect.width()
            h = rect.height()
            if w <= 0 or h <= 0:
                return
            value = f"{x},{y},{w},{h}"
            safe_log("do_save_geometry: write=%s", value)
            try:
                self._org.setPluginSetting(self._pname, "panel_geom_v1", value)
            except Exception:
                pass
        except Exception:
            pass

    def _on_top_level_changed(self, floating: bool):
        try:
	            safe_log(
	                "top_level_changed: floating=%s persisted=%s",
	                floating, self._persisted_geometry
	            )
	            pf = self._programmatic_float
	            self._programmatic_float = False
	            if not floating or not pf:
	                return
	            if not self._persisted_geometry:
	                return
	            x, y, w, h = self._persisted_geometry
	            if w > 0 and h > 0:
	                self.setGeometry(x, y, w, h)
        except Exception:
            pass

    def closeEvent(self, event):
	        try:
	            if self.isFloating():
	                try:
	                    self._target_geometry = self.geometry()
	                except Exception:
	                    pass
	                self._do_save_geometry()
	        except Exception:
	            pass
	        try:
	            if self._save_state_timer is not None:
	                self._save_state_timer.stop()
	        except Exception:
	            pass
	        try:
	            self._do_save_dock_state()
	        except Exception:
	            pass
	        try:
	            self._save_persisted_state()
	        except Exception:
	            pass
	        try:
	            self._do_save_width()
	        except Exception:
	            pass
	        try:
	            self.hide()
	            event.ignore()
	        except Exception:
	            pass

    # ── MO2 refresh (debounced) ──

    def _refresh_mo2(self):
        try:
            used = False

            ml_func = getattr(self._org, "modList", None)
            if callable(ml_func):
                try:
                    ml = ml_func()
                    update = getattr(ml, "update", None)
                    if callable(update):
                        update()
                        safe_log("modList.update() called")
                        used = True
                except Exception as e:
                    safe_log_err("modList.update FAILED: %s", e)

            if not used:
                refresh = getattr(self._org, "refresh", None)
                if callable(refresh):
                    try:
                        refresh()
                        safe_log("organizer.refresh() called")
                    except Exception as e:
                        safe_log_err("organizer.refresh FAILED: %s", e)
        except Exception as e:
            safe_log_err("MO2 refresh failed: %s", e)

    def _schedule_refresh_panels(self, delay_ms: int = 80):
        """FIX: дедупликация — один refresh вместо нескольких."""
        if self._refresh_timer is None:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._do_deferred_refresh)
        # Перезапуск таймера сбрасывает предыдущий
        self._refresh_timer.start(delay_ms)

    def _do_deferred_refresh(self):
        """FIX: выполняется один раз после всех событий."""
        try:
            self._in_operation = False  # снимаем блокировку
            self._left.set_highlighted(self._moved_highlight)
            self._left.populate()
            self._update_actions()
            safe_log("Deferred refresh done")
        except Exception as e:
            safe_log_err("Deferred refresh FAILED: %s", e)
            self._in_operation = False

    # ── UI setup ──

    def _setup_ui(self, container: QWidget):
        self.setMinimumHeight(300)

        root = QVBoxLayout(container)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Toolbar
        tb = QToolBar()
        tb.setMovable(False)

        self._act_undo = QAction("Undo", self)
        self._act_undo.triggered.connect(self._undo)
        tb.addAction(self._act_undo)

        self._act_redo = QAction("Redo", self)
        self._act_redo.triggered.connect(self._redo)
        tb.addAction(self._act_redo)

        tb.addSeparator()
        a = QAction("Refresh", self)
        a.triggered.connect(self._refresh)
        tb.addAction(a)
        tb.addSeparator()
        a = QAction("Expand All", self)
        a.triggered.connect(self._expand)
        tb.addAction(a)
        a = QAction("Collapse All", self)
        a.triggered.connect(self._collapse)
        tb.addAction(a)

        root.addWidget(tb)

        # Hint
        hint = QLabel(
            "Drag mods within the panel to reorder. "
            
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Panel
        self._left = PanelWidget(
            self._cache, "", container, dock_ref=self
        )
        root.addWidget(self._left)

        # Connect drop signal
        self._left.tree().modsDropped.connect(self._on_drop)
        try:
            self._left.tree().itemDoubleClicked.connect(
                self._on_panel_item_double_clicked
            )
        except Exception:
            pass

        try:
            self._ddm = DragDropManager(
                self._left.tree(), self._left.tree(), self
            )
            self._ddm.modsDropped.connect(self._on_drop)
        except Exception:
            self._ddm = None

        # Status
        self._status = QLabel("Ready. Drag & drop mods to reorder.")
        root.addWidget(self._status)

        # Changes label
        bl = QHBoxLayout()
        self._changes_label = QLabel("")
        bl.addWidget(self._changes_label)
        bl.addStretch()
        root.addLayout(bl)

        self._update_actions()

    # ── Shortcuts ──

    def _setup_shortcuts(self):
        try:
            undo_sc = QShortcut(QKeySequence.StandardKey.Undo, self)
            undo_sc.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            undo_sc.activated.connect(self._undo)

            redo_sc = QShortcut(QKeySequence.StandardKey.Redo, self)
            redo_sc.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            redo_sc.activated.connect(self._redo)

            f5_sc = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
            f5_sc.setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
            f5_sc.activated.connect(self._refresh)
        except Exception:
            pass

    # ── Persisted state ──

    def _load_persisted_state(self):
        legacy_names = [
            "Dual Panel Mod Mover",
            "Dual Panel Mod Mover v5.1",
            "Dual-Panel Mod Mover",
        ]

        def get(name: str):
            try:
                return self._org.pluginSetting(self._pname, name)
            except Exception:
                return None

        def get_fallback(name: str):
            v = get(name)
            if v not in (None, "", 0):
                return v
            for pn in legacy_names:
                try:
                    v2 = self._org.pluginSetting(pn, name)
                    if v2 not in (None, "", 0):
                        return v2
                except Exception:
                    continue
            return v

        try:
            raw = get_fallback("expanded_separators")
            names: Set[str] = set()
            if isinstance(raw, str) and raw:
                try:
                    arr = json.loads(raw)
                    if isinstance(arr, list):
                        for v in arr:
                            if isinstance(v, str) and v:
                                names.add(v)
                except Exception:
                    pass
            self._persist_expanded = names
        except Exception:
            self._persist_expanded = set()

        try:
            last_name = get_fallback("last_focus_name")
            last_parent = get_fallback("last_focus_parent")
            sel: Optional[str] = None
            if (isinstance(last_name, str) and last_name
                    and self._cache.exists(last_name)):
                sel = last_name
            elif (isinstance(last_parent, str) and last_parent
                  and self._cache.exists(last_parent)):
                sel = last_parent
            self._persist_select = sel
        except Exception:
            self._persist_select = None

        try:
            # Новая настройка, не пересекающаяся с устаревшей panel_width,
            # которую может менять другой код
            w = get("panel_width_v2")
            if w in (None, "", 0):
                w = self._org.pluginSetting(self._pname, "panel_width")
            val = None
            if isinstance(w, int):
                val = w
            elif isinstance(w, str):
                try:
                    val = int(w)
                except Exception:
                    val = None
            if isinstance(val, int) and val > self._collapsed_width * 2:
                self._target_width = val
            safe_log(
                "load_state: panel_width_v2=%s panel_width=%s target=%s",
                w, self._org.pluginSetting(self._pname, "panel_width"),
                self._target_width
            )
        except Exception:
            pass

        try:
            raw = get("panel_geom_v1")
            if isinstance(raw, (bytes, bytearray)):
                try:
                    raw = raw.decode("utf-8")
                except Exception:
                    raw = None
            if isinstance(raw, str) and raw:
                parts = [p.strip() for p in raw.split(",")]
                if len(parts) == 4:
                    x, y, w, h = [int(p) for p in parts]
                    if w > 0 and h > 0:
                        self._persisted_geometry = (x, y, w, h)
            safe_log("load_state: panel_geom_v1=%s", raw)
        except Exception:
            pass

    def _save_persisted_state(self):
        try:
            try:
                names = list(self._left.get_expanded_names())
            except Exception:
                names = []
            try:
                raw = json.dumps(names)
            except Exception:
                raw = "[]"
            self._org.setPluginSetting(
                self._pname, "expanded_separators", raw
            )
        except Exception:
            pass

        try:
            name = None
            parent_name = None
            try:
                item = self._left.tree().currentItem()
                if item is not None:
                    name = item.data(
                        COL_NAME, Qt.ItemDataRole.UserRole
                    )
                    pr = item.parent()
                    if pr is not None:
                        pn = pr.data(
                            COL_NAME, Qt.ItemDataRole.UserRole
                        )
                        if isinstance(pn, str) and pn:
                            parent_name = pn
                    if (parent_name is None
                            and isinstance(name, str) and name
                            and name.endswith(SEPARATOR_SUFFIX)):
                        parent_name = name
            except Exception:
                pass
            self._org.setPluginSetting(
                self._pname, "last_focus_name",
                name if name else ""
            )
            self._org.setPluginSetting(
                self._pname, "last_focus_parent",
                parent_name if parent_name else ""
            )
        except Exception:
            pass

        try:
            w_candidate = None
            if self._expanded:
                w_now = self.width()
                if w_now > self._collapsed_width * 2:
                    w_candidate = w_now
            w = max(self._target_width, w_candidate or 0, self._collapsed_width * 2)
            safe_log("save_state: width_write=%s target=%s", w, self._target_width)
            try:
                self._org.setPluginSetting(self._pname, "panel_width_v2", int(w))
            except Exception:
                pass
        except Exception:
            pass

    # ── Drop handling ──

    def _on_drop(self, mods: List[str], target: str, after: bool):
        try:
            safe_log("on_drop: %d mods -> '%s' (after=%s)",
                     len(mods), target, after)

            try:
                expanded = self._expand_names(mods)
            except Exception:
                expanded = set(mods)
            if target in expanded:
                return

            # FIX: блокируем visibilityChanged на время операции
            self._in_operation = True
            self._suppress_next_poll = True

            if self._mover.move(mods, target, after):
                self._msg(f"Moved {len(mods)} mod(s)")
                try:
                    for n in expanded:
                        self._moved_highlight.add(n)
                except Exception:
                    pass

                self._schedule_refresh_panels(100)
                try:
                    QTimer.singleShot(0, self._refresh_mo2)
                except Exception:
                    pass
            else:
                self._msg("Move failed", err=True)
                self._in_operation = False
                self._update_actions()

        except Exception as e:
            safe_log_err("on_drop FAILED: %s", e)
            self._in_operation = False

    def _refresh_panels(self):
        """Прямой refresh (для вызова из polling и visibility)."""
        try:
            try:
                self._left.set_highlighted(self._moved_highlight)
            except Exception:
                pass
            self._left.populate()
        except Exception as e:
            safe_log_err("refresh_panels FAILED: %s", e)

    def _refresh(self):
        try:
            self._cache.refresh()
            self._left.populate()
            self._msg("Refreshed")
        except Exception as e:
            safe_log_err("Refresh FAILED: %s", e)

    def _on_panel_item_double_clicked(self, item: QTreeWidgetItem,
                                       col: int = 0):
        try:
            name = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if isinstance(name, str) and name:
                try:
                    if self._cache.is_separator(name):
                        return
                except Exception:
                    if name.endswith(SEPARATOR_SUFFIX):
                        return
                self._scroll_mo2_to_mod(name)
        except Exception:
            pass

    # ── Undo / Redo ──

    def _undo(self):
        try:
            desc = self._mover.history.get_undo_desc()

            # FIX: блокируем каскадные обновления
            self._in_operation = True
            self._suppress_next_poll = True

            if self._mover.undo():
                self._msg(f"Undo: {desc}")
                self._schedule_refresh_panels(100)
                try:
                    QTimer.singleShot(0, self._refresh_mo2)
                except Exception:
                    pass
            else:
                self._msg("Nothing to undo", err=True)
                self._in_operation = False
                self._update_actions()
        except Exception:
            self._in_operation = False

    def _redo(self):
        try:
            desc = self._mover.history.get_redo_desc()

            # FIX: блокируем каскадные обновления
            self._in_operation = True
            self._suppress_next_poll = True

            if self._mover.redo():
                self._msg(f"Redo: {desc}")
                self._schedule_refresh_panels(100)
                try:
                    QTimer.singleShot(0, self._refresh_mo2)
                except Exception:
                    pass
            else:
                self._msg("Nothing to redo", err=True)
                self._in_operation = False
                self._update_actions()
        except Exception:
            self._in_operation = False

    def _expand_names(self, names: List[str]) -> Set[str]:
        out: Set[str] = set()
        try:
            all_sorted = self._cache.get_sorted()
            for n in names:
                if n not in out:
                    out.add(n)
                mi = self._cache.get(n)
                if mi and mi.is_separator:
                    inside = False
                    for m in all_sorted:
                        if m.name == n:
                            inside = True
                            continue
                        if inside:
                            if m.is_separator:
                                break
                            out.add(m.name)
        except Exception:
            pass
        return out

    # ── Polling ──

    def _start_polling(self):
        try:
            if self._poll_timer is None:
                self._poll_timer = QTimer(self)
                self._poll_timer.setInterval(1500)
                self._poll_timer.timeout.connect(self._on_poll_tick)
            if not self._poll_timer.isActive():
                self._ml_fingerprint = self._compute_ml_fingerprint()
                self._poll_timer.start()
        except Exception:
            self._poll_timer = None

    def _compute_ml_fingerprint(self) -> int:
        try:
            ml = self._org.modList()
            arr = []
            for name in ml.allMods():
                try:
                    arr.append((str(name), int(ml.priority(name))))
                except Exception:
                    continue
            arr.sort(key=lambda x: x[1])
            return hash(tuple(arr))
        except Exception:
            return 0

    def _on_poll_tick(self):
        # FIX: не поллить во время операций
        if self._in_operation:
            return
        try:
            new_fp = self._compute_ml_fingerprint()
            if new_fp == 0:
                return
            if self._suppress_next_poll:
                self._ml_fingerprint = new_fp
                self._suppress_next_poll = False
                return
            if new_fp == self._ml_fingerprint and not self._moved_highlight:
                return
            if new_fp != self._ml_fingerprint:
                self._ml_fingerprint = new_fp
                try:
                    expanded = self._left.get_expanded_names()
                except Exception:
                    expanded = set()
                try:
                    sel_item = self._left.tree().currentItem()
                    sel_name = (
                        sel_item.data(COL_NAME, Qt.ItemDataRole.UserRole)
                        if sel_item else None
                    )
                except Exception:
                    sel_name = None
                self._cache.refresh()
                try:
                    self._left.set_persisted_expanded(expanded)
                    if sel_name and self._cache.exists(sel_name):
                        self._left.set_persisted_select(sel_name)
                    self._left.set_highlighted(self._moved_highlight)
                except Exception:
                    pass
                self._left.populate()
        except Exception:
            pass

    # ── UI helpers ──

    def _expand(self):
        self._left.expand_all()

    def _collapse(self):
        self._left.collapse_all()

    def _update_actions(self):
        try:
            self._act_undo.setEnabled(
                self._mover.history.can_undo()
            )
            self._act_redo.setEnabled(
                self._mover.history.can_redo()
            )
            if self._mover.has_changes:
                self._changes_label.setText(
                    "* unsaved — MO2 will refresh on hide"
                )
            else:
                self._changes_label.setText("")
        except Exception:
            pass

    def _msg(self, text: str, err: bool = False):
        try:
            self._status.setText(text)
        except Exception:
            pass

    # ── MO2 modlist hook ──

    def _hook_modlist_selection(self):
        try:
            main_window = self.parent()
            if main_window is None:
                app = QApplication.instance()
                if app is not None:
                    for w in app.topLevelWidgets():
                        if isinstance(w, QMainWindow):
                            main_window = w
                            break
            if main_window is None:
                safe_log("_hook_modlist_selection: no main_window")
                return
            self._ml_view = self._find_mod_list_view(main_window)
            if (self._ml_view is not None
                    and self._ml_view.selectionModel() is not None):
                self._ml_view.selectionModel().currentChanged.connect(
                    self._on_mo2_mod_current_changed
                )
                safe_log("Hooked MO2 mod list selection")
            else:
                safe_log("MO2 mod list view not found")
        except Exception as e:
            safe_log_err("Hook selection FAILED: %s", e)

    def _find_mod_list_view(self, parent: QObject) -> Optional[QTreeView]:
        try:
            known = ["modList", "modListView", "ModList", "leftPane"]
            for name in known:
                v = parent.findChild(QTreeView, name)
                if v is not None:
                    return v
            views = parent.findChildren(QTreeView)
            if not views:
                try:
                    app = QApplication.instance()
                    if app is not None:
                        for w in app.allWidgets():
                            try:
                                for name in known:
                                    v = w.findChild(QTreeView, name)
                                    if v is not None:
                                        return v
                            except Exception:
                                continue
                        cand: List[QTreeView] = []
                        for w in app.allWidgets():
                            if isinstance(w, QTreeView):
                                cand.append(w)
                        views = cand
                except Exception:
                    pass
            if not views:
                return None
            best = None
            best_rows = -1
            for tv in views:
                try:
                    m = tv.model()
                    rows = m.rowCount() if m is not None else -1
                    if rows > best_rows:
                        best = tv
                        best_rows = rows
                except Exception:
                    continue
            return best
        except Exception:
            return None

    def _on_mo2_mod_current_changed(self, current, previous):
        try:
            return
        except Exception:
            pass

    def _scroll_mo2_to_mod(self, real_name: str):
        try:
            if self._ml_view is None:
                self._hook_modlist_selection()
            if self._ml_view is None:
                return
            model = self._ml_view.model()
            if model is None:
                return
            disp = (
                real_name[:-len(SEPARATOR_SUFFIX)]
                if real_name.endswith(SEPARATOR_SUFFIX)
                else real_name
            )
            candidates = [disp, real_name]
            try:
                for flags in (Qt.MatchFlag.MatchFixedString,
                              Qt.MatchFlag.MatchContains):
                    for needle in candidates:
                        match = model.match(
                            model.index(0, 0),
                            Qt.ItemDataRole.DisplayRole,
                            needle, 1, flags
                        )
                        if match:
                            idx = match[0]
                            self._ml_view.scrollTo(
                                idx,
                                QAbstractItemView.ScrollHint.PositionAtCenter
                            )
                            sm = self._ml_view.selectionModel()
                            if sm is not None:
                                sm.setCurrentIndex(
                                    idx,
                                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                                    | QItemSelectionModel.SelectionFlag.Rows
                                )
                            return
            except Exception:
                pass
            try:
                if (hasattr(model, 'sourceModel')
                        and callable(model.sourceModel)):
                    smodel = model.sourceModel()
                    if smodel is not None:
                        for sflags in (Qt.MatchFlag.MatchFixedString,
                                       Qt.MatchFlag.MatchContains):
                            for needle in candidates:
                                smatch = smodel.match(
                                    smodel.index(0, 0),
                                    Qt.ItemDataRole.DisplayRole,
                                    needle, 1, sflags
                                )
                                if smatch:
                                    sidx = smatch[0]
                                    pidx = model.mapFromSource(sidx)
                                    if pidx.isValid():
                                        self._ml_view.scrollTo(
                                            pidx,
                                            QAbstractItemView.ScrollHint.PositionAtCenter
                                        )
                                        sm = self._ml_view.selectionModel()
                                        if sm is not None:
                                            sm.setCurrentIndex(
                                                pidx,
                                                QItemSelectionModel.SelectionFlag.ClearAndSelect
                                                | QItemSelectionModel.SelectionFlag.Rows
                                            )
                                        return
            except Exception:
                pass
            rows_fn = getattr(model, 'rowCount', None)
            if not callable(rows_fn):
                return
            rc = model.rowCount()
            for r in range(rc):
                idx = model.index(r, 0)
                try:
                    text = str(idx.data())
                except Exception:
                    text = ""
                tnorm = text.strip().lower()
                hit = False
                for needle in candidates:
                    if tnorm == needle.strip().lower():
                        hit = True
                        break
                if hit:
                    try:
                        self._ml_view.scrollTo(
                            idx,
                            QAbstractItemView.ScrollHint.PositionAtCenter
                        )
                        sm = self._ml_view.selectionModel()
                        if sm is not None:
                            sm.setCurrentIndex(
                                idx,
                                QItemSelectionModel.SelectionFlag.ClearAndSelect
                                | QItemSelectionModel.SelectionFlag.Rows
                            )
                    except Exception:
                        pass
                    break
        except Exception:
            pass


# ============================================================
#  Plugin
# ============================================================

class DualPanelModMover(mobase.IPluginTool):

    def __init__(self):
        super().__init__()
        self._org = None
        self._pw = None
        self._dock = None
        self._shortcut = None
        self._hotkey = "G"
        self._create_attempts = 0
        self._max_create_attempts = 5

        self._last_display_ts = 0.0

    def init(self, organizer) -> bool:
        self._org = organizer
        try:
            cb = getattr(organizer, "onUserInterfaceInitialized", None)
            if callable(cb):
                cb(self._on_ui_initialized)
            else:
                QTimer.singleShot(2000, self._auto_show_dock)
        except Exception:
            QTimer.singleShot(2000, self._auto_show_dock)
        return True

    def _on_ui_initialized(self, *args, **kwargs):
        try:
            self._auto_show_dock()
        except Exception:
            pass

    def _auto_show_dock(self):
        try:
            if self._dock is None or not _is_alive(self._dock):
                self._create_attempts = 0
                self._create_dock()
            if self._dock is None or not _is_alive(self._dock):
                return
            self._dock.setVisible(True)
            self._dock.raise_()
            self._dock.activateWindow()
        except Exception:
            pass

    def name(self) -> str:
        return "Mod migration"

    def author(self) -> str:
        return "User"

    def description(self) -> str:
        return "Mod migration: reorder mods via drag and drop"

    def version(self):
        return mobase.VersionInfo(6, 0, 0)

    def isActive(self) -> bool:
        return True

    def settings(self):
        return [
            mobase.PluginSetting(
                "hotkey",
                "Hotkey to open the tool (e.g. F6, Ctrl+F6)",
                "G",
            )
        ]

    def displayName(self) -> str:
        return "Mod migration"

    def tooltip(self) -> str:
        return "Open Mod migration"

    def icon(self):
        return QIcon()

    def setParentWidget(self, widget):
        self._pw = widget
        try:
            self._install_hotkey()
        except Exception:
            pass

    def _install_hotkey(self):
        try:
            if self._pw is None:
                return
            if self._org is not None:
                try:
                    val = self._org.pluginSetting(self.name(), "hotkey")
                    if isinstance(val, str) and val:
                        self._hotkey = val
                except Exception:
                    pass
            if self._shortcut is not None:
                try:
                    self._shortcut.activated.disconnect()
                except Exception:
                    pass
                try:
                    self._shortcut.activatedAmbiguously.disconnect()
                except Exception:
                    pass
            self._shortcut = QShortcut(
                QKeySequence(self._hotkey), self._pw
            )
            self._shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )
            self._shortcut.activated.connect(self.display)
            self._shortcut.activatedAmbiguously.connect(self.display)
        except Exception:
            pass

    def _find_main_window(self) -> Optional[QMainWindow]:
        try:
            w = self._pw
            while w is not None:
                if isinstance(w, QMainWindow):
                    return w
                w = w.parent()
        except Exception:
            pass
        try:
            app = QApplication.instance()
            if app is not None:
                for tw in app.topLevelWidgets():
                    if isinstance(tw, QMainWindow) and tw.isVisible():
                        return tw
        except Exception:
            pass
        return None

    def _register_view_menu_action(self):
        """Добавляет пункт в меню View для показа/скрытия панели."""
        try:
            main_window = self._find_main_window()
            if main_window is None:
                return False

            if self._dock is None or not _is_alive(self._dock):
                return False

            toggle_action = self._dock.toggleViewAction()
            toggle_action.setText("Mod Migration")
            toggle_action.setToolTip("Show/Hide Mod Migration panel")

            menubar = main_window.menuBar()
            if menubar is None:
                return False

            view_menu = None
            for action in menubar.actions():
                menu = action.menu()
                if menu is not None:
                    text = action.text().replace("&", "").lower()
                    if text in ("view", "вид", "ansicht", "vue"):
                        view_menu = menu
                        break

            if view_menu is None:
                view_menu = main_window.findChild(QMenu, "viewMenu")

            if view_menu is None:
                return False

            view_menu.addSeparator()
            view_menu.addAction(toggle_action)
            return True

        except Exception:
            return False

    def _create_dock(self):
        try:
            if self._dock is not None and _is_alive(self._dock):
                return

            self._create_attempts += 1
            main_window = self._find_main_window()

            if not main_window:
                if self._create_attempts < self._max_create_attempts:
                    safe_log(
                        "Main window not found, retry %d/%d",
                        self._create_attempts, self._max_create_attempts
                    )
                    QTimer.singleShot(3000, self._create_dock)
                else:
                    safe_log_err(
                        "Main window not found after %d attempts",
                        self._max_create_attempts
                    )
                return

            self._dock = DualPanelDock(
                self._org, main_window, self.name()
            )
            main_window.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea, self._dock
            )
            self._dock.setVisible(False)
            try:
                QTimer.singleShot(300, self._dock._restore_dock_state_late)
            except Exception:
                pass
            try:
                QTimer.singleShot(500, self._register_view_menu_action)
            except Exception:
                pass
            safe_log("✓ Dock created and added to main window")

        except Exception as e:
            safe_log_err(
                "_create_dock FAILED: %s\n%s", e, traceback.format_exc()
            )

    def display(self):
        """Tools menu / hotkey toggles side panel via slider dock."""
        if not self._org:
            return
        try:
            now = time.monotonic()
            try:
                if now - float(self._last_display_ts) < 0.1:
                    return
            except Exception:
                pass
            self._last_display_ts = now

            if self._shortcut is None:
                try:
                    self._install_hotkey()
                except Exception:
                    pass

            if self._dock is None or not _is_alive(self._dock):
                self._create_attempts = 0
                self._create_dock()
                if self._dock is None or not _is_alive(self._dock):
                    return
                self._dock.setVisible(True)
                try:
                    if hasattr(self._dock, "toggle_panel"):
                        self._dock.toggle_panel()
                except Exception:
                    pass
                self._dock.raise_()
                self._dock.activateWindow()
                return

            if not self._dock.isVisible():
                self._dock.setVisible(True)
                self._dock.raise_()
                self._dock.activateWindow()

            try:
                if hasattr(self._dock, "toggle_panel"):
                    self._dock.toggle_panel()
                else:
                    self._dock.setVisible(not self._dock.isVisible())
            except Exception:
                self._dock.setVisible(not self._dock.isVisible())

        except Exception as e:
            safe_log_err(
                "display FAILED: %s\n%s", e, traceback.format_exc()
            )


def createPlugin():
    return DualPanelModMover()
