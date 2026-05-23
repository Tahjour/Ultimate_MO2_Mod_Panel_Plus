"""
Mod Quick Actions — средняя кнопка мыши для модов MO2

  Middle Click        → открыть папку мода в проводнике
  Ctrl + Middle Click → открыть страницу мода на Nexus Mods

Установка: скопировать в <MO2>/plugins/mod_quick_actions.py
"""

import mobase
import os

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QTreeView,
        QMessageBox, QToolTip,
    )
    from PyQt6.QtCore import Qt, QObject, QTimer, QUrl, QEvent
    from PyQt6.QtGui import QDesktopServices, QIcon, QCursor
    _QT6 = True
except ImportError:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QTreeView,
        QMessageBox, QToolTip,
    )
    from PyQt5.QtCore import Qt, QObject, QTimer, QUrl, QEvent
    from PyQt5.QtGui import QDesktopServices, QIcon, QCursor
    _QT6 = False


PLUGIN_NAME = "Mod Quick Actions"

_NEXUS_SLUG = {
    "skyrimse":       "skyrimspecialedition",
    "skyrimvr":       "skyrimspecialedition",
    "skyrim":         "skyrim",
    "enderal":        "enderal",
    "enderalse":      "enderalspecialedition",
    "fallout3":       "fallout3",
    "falloutnv":      "newvegas",
    "fallout4":       "fallout4",
    "fallout4vr":     "fallout4",
    "oblivion":       "oblivion",
    "morrowind":      "morrowind",
    "starfield":      "starfield",
    "baldursgate3":   "baldursgate3",
    "cyberpunk2077":  "cyberpunk2077",
    "witcher3":       "witcher3",
    "stardewvalley":  "stardewvalley",
    "nomanssky":      "nomanssky",
    "dragonage":      "dragonage",
    "mountandblade2bannerlord": "mountandblade2bannerlord",
}


def _log(msg: str) -> None:
    print(f"[QuickActions] {msg}", flush=True)


# ══════════════════════════════════════════════════════
#  Nexus URL from meta.ini
# ══════════════════════════════════════════════════════

def _nexus_url(mods_dir: str, mod_name: str,
               game_fallback: str = "") -> str:
    meta = os.path.join(mods_dir, mod_name, "meta.ini")
    if not os.path.isfile(meta):
        return ""
    try:
        try:
            with open(meta, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(meta, "r", encoding="latin-1") as f:
                lines = f.readlines()

        mod_id = ""
        game = ""
        in_general = False

        for raw in lines:
            line = raw.strip()
            if line.startswith("["):
                in_general = (line.lower() == "[general]")
                continue
            if not in_general:
                continue
            if "=" not in line:
                continue

            key, _, val = line.partition("=")
            key = key.strip().lower()
            val = val.strip()

            if key == "modid":
                mod_id = val
            elif key == "gamename":
                game = val
            if mod_id and game:
                break

        if not mod_id or mod_id in ("0", "-1"):
            return ""
        if not game:
            game = game_fallback

        slug = _NEXUS_SLUG.get(game.lower(), game.lower())
        return f"https://www.nexusmods.com/{slug}/mods/{mod_id}"

    except Exception as exc:
        _log(f"meta.ini error ({mod_name}): {exc}")
        return ""


# ══════════════════════════════════════════════════════
#  Поиск виджетов MO2
# ══════════════════════════════════════════════════════

def _find_main_window() -> QMainWindow:
    app = QApplication.instance()
    if not app:
        return None
    for w in app.topLevelWidgets():
        if (isinstance(w, QMainWindow)
                and w.isVisible()
                and w.centralWidget()):
            return w
    for w in app.topLevelWidgets():
        if isinstance(w, QMainWindow) and w.isVisible():
            return w
    return None


def _find_modlist(win: QMainWindow) -> QTreeView:
    for name in ("modList", "modListView", "modlist"):
        v = win.findChild(QTreeView, name)
        if v and v.isVisible():
            _log(f"  modlist by name '{name}'")
            return v

    cx = win.width() // 2
    best = None
    for v in win.findChildren(QTreeView):
        if not v.isVisible() or not v.model():
            continue
        gp = v.mapToGlobal(v.rect().topLeft())
        lp = win.mapFromGlobal(gp)
        if lp.x() < cx:
            if (best is None
                    or v.model().rowCount() > best.model().rowCount()):
                best = v
    if best:
        _log(f"  modlist by position '{best.objectName()}'")
    return best


def _selected_mod_name(view: QTreeView, known: set) -> str:
    if not view:
        return ""
    sm = view.selectionModel()
    if not sm:
        return ""

    rows = sm.selectedRows(0)
    if not rows:
        cur = view.currentIndex()
        if cur.isValid():
            rows = [cur.sibling(cur.row(), 0)]

    for idx in rows:
        if not idx.isValid():
            continue
        text = idx.data()
        if not text:
            continue
        text = text.strip()
        if text in known:
            return text
    return ""


# ══════════════════════════════════════════════════════
#  Фильтр — средняя кнопка мыши
# ══════════════════════════════════════════════════════

class _MiddleClickFilter(QObject):
    """
    Middle Click       → on_plain()   → открыть папку
    Ctrl + Middle Click → on_ctrl()   → открыть Nexus
    """

    def __init__(self, on_plain, on_ctrl):
        super().__init__()
        self._on_plain = on_plain
        self._on_ctrl = on_ctrl

    def eventFilter(self, obj, event):
        # ── Определяем константы ──
        if _QT6:
            mpress  = QEvent.Type.MouseButtonPress
            mid_btn = Qt.MouseButton.MiddleButton
            ctrl    = Qt.KeyboardModifier.ControlModifier
        else:
            mpress  = QEvent.MouseButtonPress
            mid_btn = Qt.MiddleButton
            ctrl    = Qt.ControlModifier

        # ── Только нажатие средней кнопки ──
        if event.type() != mpress or event.button() != mid_btn:
            return False

        # ── Ctrl зажат? ──
        if event.modifiers() & ctrl:
            _log("🖱️ Ctrl + Middle Click → Nexus")
            self._on_ctrl()
        else:
            _log("🖱️ Middle Click → Folder")
            self._on_plain()

        return True    # поглощаем событие


# ══════════════════════════════════════════════════════
#  Плагин MO2
# ══════════════════════════════════════════════════════

class ModQuickActionsPlugin(mobase.IPluginTool):
    """
    Middle Click — открыть папку мода
    Ctrl + Middle Click — открыть Nexus
    """

    def __init__(self):
        super().__init__()
        self._org = None
        self._win = None
        self._tree = None
        self._filter = None
        self._ready = False
        self._mods = set()
        self._tries = 0

    # ─────────── IPlugin ───────────

    def init(self, organizer):
        self._org = organizer
        QTimer.singleShot(3000, self._setup)
        _log("init() — ожидание GUI")
        return True

    def name(self):
        return PLUGIN_NAME

    def author(self):
        return "QuickActions"

    def description(self):
        return ("Middle click — open mod folder, "
                "Ctrl+Middle click — open Nexus page.")

    def version(self):
        try:
            return mobase.VersionInfo(1, 2, 0,
                                      mobase.ReleaseType.FINAL)
        except AttributeError:
            return mobase.VersionInfo(1, 2, 0)

    def settings(self):
        return []

    # ─────────── IPluginTool ───────────

    def displayName(self):
        return PLUGIN_NAME

    def tooltip(self):
        return self.description()

    def icon(self):
        return QIcon()

    def display(self):
        if not self._ready:
            self._tries = 0
            self._setup()

        status = "✅ Active" if self._ready else "❌ Not active"

        QMessageBox.information(
            self._win,
            PLUGIN_NAME,
            f"Mouse actions on mod list:\n\n"
            f"  🖱️ Middle Click          →  Open mod folder\n"
            f"  🖱️ Ctrl + Middle Click   →  Open Nexus page\n\n"
            f"Status: {status}",
        )

    # ─────────── Setup ───────────

    def _setup(self):
        if self._ready:
            return
        self._tries += 1
        if self._tries > 20:
            _log("❌ не удалось найти GUI за 20 попыток")
            return

        self._win = _find_main_window()
        if not self._win:
            QTimer.singleShot(2000, self._setup)
            return

        self._tree = _find_modlist(self._win)
        if not self._tree:
            QTimer.singleShot(2000, self._setup)
            return

        # ── Фильтр средней кнопки ──
        self._filter = _MiddleClickFilter(
            on_plain=self._act_folder,
            on_ctrl=self._act_nexus,
        )

        self._tree.viewport().installEventFilter(self._filter)
        self._tree.installEventFilter(self._filter)

        # ── Кэш списка модов ──
        self._refresh_mods()
        timer = QTimer(self._win)
        timer.timeout.connect(self._refresh_mods)
        timer.start(15_000)

        self._ready = True
        _log(f"✅ Готово!  Middle=папка  Ctrl+Middle=nexus  "
             f"tree='{self._tree.objectName()}'  "
             f"mods={len(self._mods)}")

    def _refresh_mods(self):
        try:
            self._mods = set(self._org.modList().allMods())
        except Exception:
            pass

    # ─────────── Actions ───────────

    def _current_mod(self) -> str:
        if not self._tree or not self._tree.isVisible():
            if self._win:
                self._tree = _find_modlist(self._win)
                if self._tree and self._filter:
                    self._tree.viewport().installEventFilter(
                        self._filter)
                    self._tree.installEventFilter(self._filter)
        return _selected_mod_name(self._tree, self._mods)

    def _tip(self, text: str) -> None:
        try:
            QToolTip.showText(QCursor.pos(), text)
        except Exception:
            pass

    def _act_folder(self):
        mod = self._current_mod()
        if not mod:
            self._tip("Select a mod first")
            return
        path = os.path.join(self._org.modsPath(), mod)
        if not os.path.isdir(path):
            self._tip(f"Folder not found:\n{path}")
            _log(f"missing folder: {path}")
            return
        _log(f"📂 {mod}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _act_nexus(self):
        mod = self._current_mod()
        if not mod:
            self._tip("Select a mod first")
            return
        try:
            game = self._org.managedGame().gameShortName()
        except Exception:
            game = ""

        url = _nexus_url(self._org.modsPath(), mod, game)
        if not url:
            self._tip(f"No Nexus link for:\n{mod}")
            _log(f"no nexus: {mod}")
            return
        _log(f"🌐 {mod} → {url}")
        QDesktopServices.openUrl(QUrl(url))


# ══════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════

def createPlugin():
    return ModQuickActionsPlugin()