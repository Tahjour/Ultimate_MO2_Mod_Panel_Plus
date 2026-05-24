"""
Mod Info Tab — MO2 Plugin
Adds a 'Mod Info' tab to MO2's right panel with file size stats and conflict info.
Context menu on conflict trees: hide/delete/rename files on either side.
"""
from __future__ import annotations

import os
import subprocess
import sys
from collections import defaultdict
from typing import Optional

import mobase
from PyQt6.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import (
    QDesktopServices,
    QFont,
    QIcon,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_TAB_LABEL = "Mod Info"
_SKIP_FILES = frozenset({"meta.ini"})

_TEXTURE_EXT = frozenset(
    {".dds", ".tga", ".bmp", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
)
_MESH_EXT = frozenset({".nif", ".kf", ".kfm", ".tri"})
_PLUGIN_EXT = frozenset({".esp", ".esm", ".esl"})
_SCRIPT_EXT = frozenset({".psc", ".pex"})
_ANIM_EXT = frozenset({".hkx"})
_SOUND_EXT = frozenset({".wav", ".xwm", ".fuz", ".mp3", ".ogg"})
_INTERFACE_EXT = frozenset({".swf", ".gfx"})
_ARCHIVE_EXT = frozenset({".bsa", ".ba2"})
_CONFIG_EXT = frozenset({".ini", ".toml", ".json", ".xml", ".cfg", ".txt"})

_LOG_PREFIX = "[ModInfoTab]"


def _log(msg: str) -> None:
    try:
        print(f"{_LOG_PREFIX} {msg}", flush=True)
    except Exception:
        pass


# ── Utility ───────────────────────────────────────────────────────────────────


def _human_size(nbytes: int) -> str:
    val = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(val) < 1024 or unit == "TB":
            return f"{val:.0f} {unit}" if unit == "B" else f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PB"


def _mod_directory(organizer: mobase.IOrganizer, mod_name: str) -> Optional[str]:
    try:
        mod_obj = organizer.modList().getMod(mod_name)
        if mod_obj is not None:
            path = mod_obj.absolutePath()
            if path and os.path.isdir(path):
                return path
    except Exception:
        pass
    try:
        path = os.path.join(organizer.modsPath(), mod_name)
        if os.path.isdir(path):
            return path
    except Exception:
        pass
    return None


def _full_path(organizer: mobase.IOrganizer, mod_name: str, rel: str) -> Optional[str]:
    d = _mod_directory(organizer, mod_name)
    if not d:
        return None
    return os.path.join(d, rel.replace("/", os.sep))


def _open_in_explorer(path: str) -> None:
    norm = os.path.normpath(path)
    if sys.platform == "win32":
        if os.path.isfile(norm):
            subprocess.Popen(["explorer", "/select,", norm])
        else:
            d = norm if os.path.isdir(norm) else os.path.dirname(norm)
            if os.path.isdir(d):
                subprocess.Popen(["explorer", d])
    else:
        target = norm if os.path.isdir(norm) else os.path.dirname(norm)
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))


def _classify_file(relpath: str, ext: str) -> str:
    e = ext.lower()
    rel = relpath.lower()
    if e in {".ini", ".toml", ".txt"} and (
        "baseobjectswapper" in rel or "/bos/" in rel
        or "spell perk item distributor" in rel or "/spid/" in rel
    ):
        return "BOS / SPID"
    if e == ".dll" and "skse" in rel:
        return "SKSE PLUGINS"
    if e in _TEXTURE_EXT:   return "TEXTURES"
    if e in _MESH_EXT:      return "MESHES"
    if e in _PLUGIN_EXT:    return "PLUGINS"
    if e in _SCRIPT_EXT:    return "SCRIPTS"
    if e in _ANIM_EXT:      return "ANIMATIONS"
    if e in _SOUND_EXT:     return "SOUNDS"
    if e in _INTERFACE_EXT: return "INTERFACE"
    if e in _ARCHIVE_EXT:   return "BSA / ARCHIVES"
    if e in _CONFIG_EXT:    return "INI / CONFIG"
    if ext == "(no ext)":   return "NO EXTENSION"
    return "MISC"


def _find_mod_list_view() -> Optional[QTreeView]:
    for w in QApplication.allWidgets():
        if isinstance(w, QTreeView) and w.objectName() == "modList":
            return w
    return None


def _find_right_tab_widget(window) -> Optional[QTabWidget]:
    all_tw = window.findChildren(QTabWidget)
    if not all_tw:
        return None
    expected = {"plugins", "archives", "data", "saves", "downloads"}
    for tw in all_tw:
        if not tw.isVisible() or tw.count() < 2:
            continue
        captions = {tw.tabText(i).lower() for i in range(tw.count())}
        if len(captions & expected) >= 2:
            return tw
    cx = window.geometry().width() // 2
    best, bx = None, -1
    for tw in all_tw:
        if not tw.isVisible() or tw.count() < 2:
            continue
        lx = window.mapFromGlobal(tw.mapToGlobal(tw.rect().topLeft())).x()
        if lx > cx * 0.4 and lx > bx:
            best, bx = tw, lx
    return best


def _cleanup_empty_dirs(dirpath: str, stop_at: str) -> None:
    dirpath = os.path.normpath(dirpath)
    stop_at = os.path.normpath(stop_at)
    while dirpath != stop_at and len(dirpath) > len(stop_at):
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
            else:
                break
        except OSError:
            break
        dirpath = os.path.dirname(dirpath)


# ── Conflict Scanner ─────────────────────────────────────────────────────────


class _ConflictScanner:
    def __init__(self, org: mobase.IOrganizer):
        self._org = org
        self._cache: dict[str, tuple[dict[str, list[str]], dict[str, list[str]]]] = {}
        self._api_tested = False
        self._api_works = False
        self._disk_built = False
        self._disk_wins: dict[str, dict[str, list[str]]] = {}
        self._disk_loses: dict[str, dict[str, list[str]]] = {}
        self._last_error = ""

    def invalidate(self) -> None:
        self._cache.clear()
        self._api_tested = False
        self._disk_built = False
        self._disk_wins.clear()
        self._disk_loses.clear()
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def method_name(self) -> str:
        if not self._api_tested:
            return "not scanned yet"
        return "getFileOrigins API" if self._api_works else "disk scan"

    def overwritten_by(self, mod: str) -> dict[str, list[str]]:
        return self._get(mod)[0]

    def overwrites(self, mod: str) -> dict[str, list[str]]:
        return self._get(mod)[1]

    def _get(self, mod):
        if mod in self._cache:
            return self._cache[mod]
        if not self._api_tested:
            self._api_works = self._test_api()
            self._api_tested = True
        r = self._scan_api(mod) if self._api_works else self._scan_disk(mod)
        self._cache[mod] = r
        return r

    def _test_api(self):
        if not callable(getattr(self._org, "getFileOrigins", None)):
            return False
        try:
            r = self._org.getFileOrigins("__probe__.zzz")
            return isinstance(r, (list, tuple))
        except Exception:
            return False

    def _scan_api(self, mod_name):
        mp = _mod_directory(self._org, mod_name)
        if not mp:
            self._last_error = f"Dir not found: {mod_name}"
            return {}, {}
        ob: dict[str, list[str]] = defaultdict(list)
        ow: dict[str, list[str]] = defaultdict(list)
        for dp, _, fns in os.walk(mp):
            for fn in fns:
                if fn.lower() in _SKIP_FILES:
                    continue
                rel = os.path.relpath(os.path.join(dp, fn), mp).replace("\\", "/")
                try:
                    origins = self._org.getFileOrigins(rel)
                except Exception:
                    continue
                if not origins or len(origins) < 2:
                    continue
                w = origins[0]
                if w == mod_name:
                    for l in origins[1:]:
                        ow[l].append(rel)
                elif mod_name in origins:
                    ob[w].append(rel)
        self._last_error = ""
        return dict(ob), dict(ow)

    def _scan_disk(self, mod_name):
        if not self._disk_built:
            self._build_disk()
        return self._disk_loses.get(mod_name, {}), self._disk_wins.get(mod_name, {})

    def _build_disk(self):
        ml = self._org.modList()
        af = 2
        for a in ("ACTIVE", "active"):
            try:
                af = int(getattr(mobase.ModState, a)); break
            except Exception:
                pass
        fm: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        for mn in ml.allMods():
            try:
                if not (int(ml.state(mn)) & af):
                    continue
                pri = int(ml.priority(mn))
            except Exception:
                continue
            mp = _mod_directory(self._org, mn)
            if not mp:
                continue
            for dp, _, fns in os.walk(mp):
                for fn in fns:
                    if fn.lower() in _SKIP_FILES:
                        continue
                    rel = os.path.relpath(os.path.join(dp, fn), mp).replace("\\", "/")
                    fm[rel.lower()].append((mn, pri, rel))
        wins: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        loses: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for owners in fm.values():
            if len(owners) < 2:
                continue
            owners.sort(key=lambda t: t[1])
            w = owners[-1]
            for l in owners[:-1]:
                wins[w[0]][l[0]].append(w[2])
                loses[l[0]][w[0]].append(w[2])
        self._disk_wins = {k: dict(v) for k, v in wins.items()}
        self._disk_loses = {k: dict(v) for k, v in loses.items()}
        self._disk_built = True


# ── Hover Filter ──────────────────────────────────────────────────────────────


class _HoverFilter(QObject):
    def __init__(self, cb, view: QTreeView):
        super().__init__(view)
        self._cb, self._view = cb, view
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._pending: Optional[QPersistentModelIndex] = None
        self._timer.timeout.connect(self._fire)

    def eventFilter(self, _o, ev):
        if ev.type() == QEvent.Type.MouseMove:
            try:
                try:
                    pos = ev.position().toPoint()
                except AttributeError:
                    pos = ev.pos()
                idx = self._view.indexAt(pos)
                if idx.isValid():
                    self._pending = QPersistentModelIndex(idx)
                    self._timer.start()
            except Exception:
                pass
        return False

    def _fire(self):
        if self._pending and self._pending.isValid():
            self._cb(QModelIndex(self._pending))
        self._pending = None


# ── Main Widget ───────────────────────────────────────────────────────────────


# Tree item data roles
_ROLE_MOD = Qt.ItemDataRole.UserRole + 100     # str: mod name that owns the file
_ROLE_REL = Qt.ItemDataRole.UserRole + 101     # str: relative path inside mod
_ROLE_IS_FILE = Qt.ItemDataRole.UserRole + 102  # bool: True for file items


class ModInfoWidget(QWidget):
    def __init__(self, organizer: mobase.IOrganizer, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._org = organizer
        self._conflicts = _ConflictScanner(organizer)
        self._mod_view: Optional[QTreeView] = None
        self._current: Optional[str] = None
        self._known_mods: Optional[set[str]] = None
        self._hover_filter: Optional[_HoverFilter] = None
        self._build_ui()

    # ── UI Build ──

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(6)

        self._label_name = QLabel("No mod selected")
        f = QFont(); f.setPointSize(11); f.setBold(True)
        self._label_name.setFont(f)
        self._label_name.setWordWrap(True)
        main.addWidget(self._label_name)
        main.addWidget(self._sep())

        ctl = QHBoxLayout()
        self._chk_hover = QCheckBox("Track hover")
        self._btn_rebuild = QPushButton("⟳ Rebuild")
        self._btn_rebuild.setFixedHeight(24)
        ctl.addWidget(self._chk_hover)
        ctl.addStretch()
        ctl.addWidget(self._btn_rebuild)
        main.addLayout(ctl)

        self._label_method = QLabel("")
        self._label_method.setStyleSheet("color:#666;font-size:10px;")
        main.addWidget(self._label_method)
        main.addWidget(self._sep())

        self._tabs = QTabWidget(self)

        # ── Files tab ──
        fp = QWidget()
        fl = QVBoxLayout(fp)
        self._label_size = QLabel()
        self._label_size.setWordWrap(True)
        fl.addWidget(self._label_size)
        self._label_types = QLabel()
        self._label_types.setWordWrap(True)
        self._label_types.setStyleSheet("color:#888;font-size:11px;")
        fl.addWidget(self._label_types)
        self._type_model = QStandardItemModel()
        self._type_tree = QTreeView()
        self._type_tree.setModel(self._type_model)
        self._type_tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._type_tree.setAlternatingRowColors(True)
        fl.addWidget(self._type_tree, 1)
        self._tabs.addTab(fp, "Files")

        # ── Conflicts tab ──
        cp = QWidget()
        cl = QVBoxLayout(cp)

        hdr = QHBoxLayout()
        self._hdr_l = QLabel("Overwritten by")
        self._hdr_r = QLabel("Overwrites")
        bf = QFont(); bf.setBold(True)
        self._hdr_l.setFont(bf); self._hdr_r.setFont(bf)
        hdr.addWidget(self._hdr_l, 1)
        hdr.addWidget(self._hdr_r, 1)
        cl.addLayout(hdr)

        btn = QHBoxLayout()
        self._bcl = QPushButton("▸ Collapse")
        self._bel = QPushButton("▾ Expand")
        self._bcr = QPushButton("▸ Collapse")
        self._ber = QPushButton("▾ Expand")
        for b in (self._bcl, self._bel, self._bcr, self._ber):
            b.setFixedHeight(20)
            b.setStyleSheet("font-size:10px;padding:0 6px;")
        btn.addWidget(self._bcl); btn.addWidget(self._bel)
        btn.addStretch()
        btn.addWidget(self._bcr); btn.addWidget(self._ber)
        cl.addLayout(btn)

        sp = QSplitter(Qt.Orientation.Horizontal)
        self._mdl_l = QStandardItemModel()
        self._mdl_r = QStandardItemModel()
        self._tree_l = self._mktree(self._mdl_l)
        self._tree_r = self._mktree(self._mdl_r)

        for t in (self._tree_l, self._tree_r):
            t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self._tree_l.customContextMenuRequested.connect(
            lambda pos: self._on_ctx(self._tree_l, self._mdl_l, pos, "overwritten_by"))
        self._tree_r.customContextMenuRequested.connect(
            lambda pos: self._on_ctx(self._tree_r, self._mdl_r, pos, "overwrites"))

        sp.addWidget(self._tree_l); sp.addWidget(self._tree_r)
        sp.setStretchFactor(0, 1); sp.setStretchFactor(1, 1)
        cl.addWidget(sp, 1)

        self._label_cerr = QLabel("")
        self._label_cerr.setStyleSheet("color:#c44;font-size:10px;")
        self._label_cerr.setWordWrap(True)
        cl.addWidget(self._label_cerr)

        self._tabs.addTab(cp, "Conflicts")
        main.addWidget(self._tabs, 1)

        self._bcl.clicked.connect(self._tree_l.collapseAll)
        self._bel.clicked.connect(self._tree_l.expandAll)
        self._bcr.clicked.connect(self._tree_r.collapseAll)
        self._ber.clicked.connect(self._tree_r.expandAll)
        self._btn_rebuild.clicked.connect(self._on_rebuild)
        self._chk_hover.toggled.connect(self._on_hover_toggled)

    @staticmethod
    def _sep():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    @staticmethod
    def _mktree(model):
        t = QTreeView()
        t.setModel(model)
        t.setHeaderHidden(True)
        t.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        t.setIndentation(14)
        t.setUniformRowHeights(True)
        t.setAlternatingRowColors(True)
        return t

    def attach_to_mod_list(self, view: QTreeView):
        self._mod_view = view
        sel = view.selectionModel()
        if sel:
            sel.currentChanged.connect(self._on_selection)

    # ── Hover ──

    def _on_hover_toggled(self, on):
        v = self._mod_view
        if not v:
            return
        vp = v.viewport()
        if on:
            if not self._hover_filter:
                self._hover_filter = _HoverFilter(self._on_hover_idx, v)
            vp.setMouseTracking(True)
            vp.installEventFilter(self._hover_filter)
        elif self._hover_filter:
            vp.removeEventFilter(self._hover_filter)

    def _on_hover_idx(self, idx):
        n = self._resolve(idx)
        if n and n != self._current:
            self._show(n)

    def _on_selection(self, cur, _prev):
        self._show(self._resolve(cur))

    def _on_rebuild(self):
        self._conflicts.invalidate()
        self._known_mods = None
        old = self._current
        self._current = None
        if old:
            self._show(old)

    # ── Name resolve ──

    def _resolve(self, idx):
        if not idx.isValid() or not self._mod_view:
            return None
        model = self._mod_view.model()
        if not model:
            return None
        row, par = idx.row(), idx.parent()
        cands = []
        for col in range(min(model.columnCount(par), 10)):
            val = model.index(row, col, par).data(Qt.ItemDataRole.DisplayRole)
            if isinstance(val, str) and val.strip():
                cands.append(val.strip())
        if not cands:
            return None
        known = self._all_mods()
        for c in cands:
            if c in known:
                return c
        return cands[0]

    def _all_mods(self):
        if self._known_mods is None:
            try:
                self._known_mods = set(self._org.modList().allMods())
            except Exception:
                self._known_mods = set()
        return self._known_mods

    # ══════════════════════════════════════════════════════════════════════════
    #  CONTEXT MENU — per-file, shows both sides
    # ══════════════════════════════════════════════════════════════════════════

    def _on_ctx(self, tree: QTreeView, model: QStandardItemModel, pos, side: str):
        """
        Right-click on a single file in a conflict tree.
        
        side = "overwritten_by":
            tree_l clicked. Parent = other_mod that overwrites current.
            The file exists in BOTH current_mod (losing copy) and other_mod (winning copy).
            
        side = "overwrites":
            tree_r clicked. Parent = other_mod that current overwrites.
            The file exists in BOTH current_mod (winning copy) and other_mod (losing copy).
        """
        if not self._current:
            return

        idx = tree.indexAt(pos)
        if not idx.isValid():
            return

        item = model.itemFromIndex(idx)
        if not item:
            return

        # Only file items (children), not mod-group parents
        is_file = item.data(_ROLE_IS_FILE)
        if not is_file:
            return

        rel_path = item.data(_ROLE_REL)
        other_mod = item.data(_ROLE_MOD)
        if not rel_path or not other_mod:
            return

        current_mod = self._current

        # Determine which side is winner / loser
        if side == "overwritten_by":
            winner_mod = other_mod
            loser_mod = current_mod
        else:
            winner_mod = current_mod
            loser_mod = other_mod

        winner_path = _full_path(self._org, winner_mod, rel_path)
        loser_path = _full_path(self._org, loser_mod, rel_path)
        winner_exists = winner_path and os.path.isfile(winner_path)
        loser_exists = loser_path and os.path.isfile(loser_path)

        fname = os.path.basename(rel_path)

        menu = QMenu(tree)

        # ── Header ──
        header = menu.addAction(f"📄 {fname}")
        header.setEnabled(False)
        menu.addSeparator()

        # ── Winner side ──
        w_label = f"Winner: {self._short(winner_mod)}"
        menu.addAction(w_label).setEnabled(False)

        a_w_hide = menu.addAction("   🙈 Hide (.mohidden)")
        a_w_del = menu.addAction("   🗑️ Delete")
        a_w_ren = menu.addAction("   ✏️ Rename")
        a_w_open = menu.addAction("   📂 Open folder")

        if not winner_exists:
            for a in (a_w_hide, a_w_del, a_w_ren, a_w_open):
                a.setEnabled(False)
            a_w_hide.setText("   🙈 Hide (file in BSA — not on disk)")

        menu.addSeparator()

        # ── Loser side ──
        l_label = f"Overridden: {self._short(loser_mod)}"
        menu.addAction(l_label).setEnabled(False)

        a_l_hide = menu.addAction("   🙈 Hide (.mohidden)")
        a_l_del = menu.addAction("   🗑️ Delete")
        a_l_ren = menu.addAction("   ✏️ Rename")
        a_l_open = menu.addAction("   📂 Open folder")

        if not loser_exists:
            for a in (a_l_hide, a_l_del, a_l_ren, a_l_open):
                a.setEnabled(False)
            a_l_hide.setText("   🙈 Hide (file in BSA — not on disk)")

        menu.addSeparator()

        # ── Both sides ──
        a_show_paths = menu.addAction("ℹ️ Show full paths")

        # ── Execute ──
        chosen = menu.exec(tree.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen is a_w_hide:
            self._do_hide(winner_mod, winner_path, rel_path)
        elif chosen is a_w_del:
            self._do_delete(winner_mod, winner_path, rel_path)
        elif chosen is a_w_ren:
            self._do_rename(winner_mod, winner_path, rel_path)
        elif chosen is a_w_open:
            _open_in_explorer(winner_path)
        elif chosen is a_l_hide:
            self._do_hide(loser_mod, loser_path, rel_path)
        elif chosen is a_l_del:
            self._do_delete(loser_mod, loser_path, rel_path)
        elif chosen is a_l_ren:
            self._do_rename(loser_mod, loser_path, rel_path)
        elif chosen is a_l_open:
            _open_in_explorer(loser_path)
        elif chosen is a_show_paths:
            w_disp = winner_path or "(not on disk)"
            l_disp = loser_path or "(not on disk)"
            QMessageBox.information(
                self, "File paths",
                f"Relative: {rel_path}\n\n"
                f"Winner ({winner_mod}):\n{w_disp}\n\n"
                f"Overridden ({loser_mod}):\n{l_disp}"
            )

    # ── File actions ──

    def _do_hide(self, mod_name: str, full: str, rel: str):
        target = full + ".mohidden"
        reply = QMessageBox.question(
            self, "Hide file",
            f"Hide file in «{mod_name}»?\n\n"
            f"{rel}\n\n"
            f"File will be renamed to:\n{os.path.basename(target)}\n\n"
            f"This can be reversed by removing .mohidden extension.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if os.path.exists(target):
                os.remove(target)
            os.rename(full, target)
            _log(f"Hidden: {full} → {target}")
            mod_dir = _mod_directory(self._org, mod_name)
            if mod_dir:
                _cleanup_empty_dirs(os.path.dirname(full), mod_dir)
            self._refresh()
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Failed to hide:\n{e}")

    def _do_delete(self, mod_name: str, full: str, rel: str):
        reply = QMessageBox.warning(
            self, "Delete file",
            f"PERMANENTLY delete file in «{mod_name}»?\n\n"
            f"{rel}\n\n"
            f"Full path:\n{full}\n\n"
            f"⚠️ This CANNOT be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(full)
            _log(f"Deleted: {full}")
            mod_dir = _mod_directory(self._org, mod_name)
            if mod_dir:
                _cleanup_empty_dirs(os.path.dirname(full), mod_dir)
            self._refresh()
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Failed to delete:\n{e}")

    def _do_rename(self, mod_name: str, full: str, rel: str):
        old_name = os.path.basename(full)
        new_name, ok = QInputDialog.getText(
            self, "Rename file",
            f"Rename file in «{mod_name}»:\n{rel}\n\nNew file name:",
            text=old_name,
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        # Disallow path separators in the name
        if "/" in new_name or "\\" in new_name:
            QMessageBox.warning(self, "Invalid name", "File name cannot contain path separators.")
            return

        target = os.path.join(os.path.dirname(full), new_name)
        if os.path.exists(target):
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"File already exists:\n{new_name}\n\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            os.rename(full, target)
            _log(f"Renamed: {full} → {target}")
            self._refresh()
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Failed to rename:\n{e}")

    def _refresh(self):
        self._conflicts.invalidate()
        self._known_mods = None
        try:
            self._org.refresh()
        except Exception:
            pass
        old = self._current
        self._current = None
        if old:
            self._show(old)

    @staticmethod
    def _short(name: str, mx: int = 35) -> str:
        return name if len(name) <= mx else name[:mx - 1] + "…"

    # ══════════════════════════════════════════════════════════════════════════
    #  DISPLAY
    # ══════════════════════════════════════════════════════════════════════════

    def _show(self, name):
        if name == self._current:
            return
        self._current = name
        if not name:
            self._label_name.setText("No mod selected")
            self._label_size.setText("")
            self._label_types.setText("")
            self._type_model.clear()
            self._mdl_l.clear(); self._mdl_r.clear()
            self._hdr_l.setText("Overwritten by")
            self._hdr_r.setText("Overwrites")
            self._label_method.setText("")
            self._label_cerr.setText("")
            return
        self._label_name.setText(name)
        self._fill_size(name)
        self._fill_conflicts(name)

    def _fill_size(self, name):
        mp = _mod_directory(self._org, name)
        self._type_model.clear()
        if not mp:
            self._label_size.setText("(directory not found)")
            self._label_types.setText("")
            return
        total = count = 0
        pe: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        pc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        pce: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for dp, _, fns in os.walk(mp):
            for fn in fns:
                if fn.lower() in _SKIP_FILES:
                    continue
                fp2 = os.path.join(dp, fn)
                try:
                    sz = os.path.getsize(fp2)
                except OSError:
                    sz = 0
                rel = os.path.relpath(fp2, mp).replace("\\", "/")
                ext = os.path.splitext(fn)[1].lower() or "(no ext)"
                pe[ext][0] += 1; pe[ext][1] += sz
                cat = _classify_file(rel, ext)
                pc[cat][0] += 1; pc[cat][1] += sz
                pce[cat][ext][0] += 1; pce[cat][ext][1] += sz
                total += sz; count += 1
        self._label_size.setText(f"Files: {count}     Size: {_human_size(total)}")
        lines = [f"  {e}: {i[0]} × {_human_size(i[1])}"
                 for e, i in sorted(pe.items(), key=lambda x: -x[1][1])]
        self._label_types.setText("\n".join(lines))
        self._update_type_tree(pc, pce)

    def _update_type_tree(self, pc, pce):
        self._type_model.clear()
        self._type_model.setHorizontalHeaderLabels(["Group / Type", "Files", "Size"])
        for cat, t in sorted(pc.items(), key=lambda x: -x[1][1]):
            r0 = QStandardItem(cat)
            r1 = QStandardItem(str(t[0]))
            r2 = QStandardItem(_human_size(t[1]))
            self._type_model.appendRow([r0, r1, r2])
            for ext, i in sorted(pce.get(cat, {}).items(), key=lambda x: -x[1][1]):
                r0.appendRow([QStandardItem(ext), QStandardItem(str(i[0])),
                              QStandardItem(_human_size(i[1]))])

    def _fill_conflicts(self, name):
        ob = self._conflicts.overwritten_by(name)
        ow = self._conflicts.overwrites(name)
        self._mdl_l.clear(); self._mdl_r.clear()

        nl = self._fill_tree(self._mdl_l, ob, is_overwritten_by=True)
        nr = self._fill_tree(self._mdl_r, ow, is_overwritten_by=False)

        self._hdr_l.setText(f"Overwritten by ({nl})" if nl else "Overwritten by")
        self._hdr_r.setText(f"Overwrites ({nr})" if nr else "Overwrites")
        self._label_method.setText(f"Method: {self._conflicts.method_name}")
        err = self._conflicts.last_error
        self._label_cerr.setText(err or "")

    def _fill_tree(self, model: QStandardItemModel,
                   data: dict[str, list[str]],
                   is_overwritten_by: bool) -> int:
        """
        Populate conflict tree. Each child item stores:
          _ROLE_MOD     = the OTHER mod name
          _ROLE_REL     = relative path
          _ROLE_IS_FILE = True
        """
        total = 0
        for other_mod, paths in sorted(data.items()):
            parent = QStandardItem(f"{other_mod}  [{len(paths)}]")
            parent.setToolTip(other_mod)
            parent.setData(other_mod, _ROLE_MOD)
            parent.setData(False, _ROLE_IS_FILE)

            for p in sorted(paths):
                child = QStandardItem(p)
                child.setToolTip(p)
                child.setData(other_mod, _ROLE_MOD)
                child.setData(p, _ROLE_REL)
                child.setData(True, _ROLE_IS_FILE)
                parent.appendRow(child)

            model.appendRow(parent)
            total += len(paths)
        return total


# ── Plugin class ──────────────────────────────────────────────────────────────


class ModInfoTabPlugin(mobase.IPluginTool):
    NAME = "Mod Info Tab"

    def __init__(self):
        super().__init__()
        self._org: Optional[mobase.IOrganizer] = None
        self._window = None
        self._widget: Optional[ModInfoWidget] = None
        self._injected = False
        self._attempts = 0

    def init(self, organizer):
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._on_ui_ready)
        return True

    def name(self):           return self.NAME
    def author(self):         return "ModInfoTab"
    def description(self):    return "Per-mod size statistics and file conflicts in right panel"
    def version(self):
        try:    return mobase.VersionInfo(1, 4, 0, mobase.ReleaseType.FINAL)
        except: return mobase.VersionInfo(1, 4, 0)
    def isActive(self):       return True
    def settings(self):       return []
    def displayName(self):    return self.NAME
    def tooltip(self):        return self.description()
    def icon(self):           return QIcon()

    def display(self):
        if not self._widget:
            return
        p = self._widget.parent()
        while p and not isinstance(p, QTabWidget):
            p = p.parent()
        if isinstance(p, QTabWidget):
            i = p.indexOf(self._widget)
            if i >= 0:
                p.setCurrentIndex(i)

    def _on_ui_ready(self, mw):
        self._window = mw
        QTimer.singleShot(1200, self._try_inject)

    def _try_inject(self):
        if self._injected or not self._window or not self._org:
            return
        self._attempts += 1
        tw = _find_right_tab_widget(self._window)
        if not tw:
            if self._attempts < 20:
                QTimer.singleShot(2000, self._try_inject)
            return
        for i in range(tw.count()):
            if tw.tabText(i) == _TAB_LABEL:
                w = tw.widget(i)
                if isinstance(w, ModInfoWidget):
                    self._widget = w
                self._injected = True
                return
        self._widget = ModInfoWidget(self._org)
        mv = _find_mod_list_view()
        if mv:
            self._widget.attach_to_mod_list(mv)
        tw.addTab(self._widget, _TAB_LABEL)
        self._injected = True
        _log("Tab injected")


def createPlugin():
    return ModInfoTabPlugin()
