"""Advanced Search (Full Mod Search) plugin package for Mod Organizer 2.

Этот пакет предоставляет точку входа createPlugin() по образцу других
модульных плагинов MO2 (например, ContentFilter, NIF Analyzer и т.п.).

Основная реализация плагина находится в модуле amsp_pro.py внутри этой
же папки AdvancedSearch. Здесь мы только проксируем создание экземпляра,
чтобы плагин можно было считать "модульным" и размещённым в собственной
папке.
"""

from __future__ import annotations

from typing import Optional
import os
import importlib.util
import mobase

try:
    from .plugin import FullModSearchPlugin
except ImportError:
    FullModSearchPlugin = None  # type: ignore[assignment]

try:
    from .amsp_pro import FullModSearchPlugin as AdvancedSearchProPlugin
except ImportError as e:  # pragma: no cover - защитный путь
    AdvancedSearchProPlugin = None  # type: ignore[assignment]
    _import_error: Optional[Exception] = e
else:
    _import_error = None

_hmm_module = None
_hmm_import_error: Optional[Exception] = None
try:
    _hmm_path = os.path.join(os.path.dirname(__file__), "Holy Mod Migration.py")
    if os.path.exists(_hmm_path):
        _spec = importlib.util.spec_from_file_location("advancedsearch_holy_mod_migration", _hmm_path)
        if _spec and _spec.loader:
            _hmm_module = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_hmm_module)  # type: ignore[attr-defined]
except Exception as e:
    _hmm_import_error = e

_autoscroller_module = None
_autoscroller_import_error: Optional[Exception] = None
try:
    _autoscroller_path = os.path.join(os.path.dirname(__file__), "autoscroller.py")
    if os.path.exists(_autoscroller_path):
        _spec = importlib.util.spec_from_file_location("advancedsearch_autoscroller", _autoscroller_path)
        if _spec and _spec.loader:
            _autoscroller_module = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_autoscroller_module)  # type: ignore[attr-defined]
except Exception as e:
    _autoscroller_import_error = e

_copy_past_module = None
_copy_past_import_error: Optional[Exception] = None
try:
    _copy_past_path = os.path.join(os.path.dirname(__file__), "COPY-Past.py")
    if os.path.exists(_copy_past_path):
        _spec = importlib.util.spec_from_file_location("advancedsearch_copy_past", _copy_past_path)
        if _spec and _spec.loader:
            _copy_past_module = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_copy_past_module)  # type: ignore[attr-defined]
except Exception as e:
    _copy_past_import_error = e


_mod_renamer_module = None
_mod_renamer_import_error: Optional[Exception] = None
try:
    _mod_renamer_path = os.path.join(os.path.dirname(__file__), "Mod Renamer.py")
    if os.path.exists(_mod_renamer_path):
        _spec = importlib.util.spec_from_file_location("advancedsearch_mod_renamer", _mod_renamer_path)
        if _spec and _spec.loader:
            _mod_renamer_module = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod_renamer_module)  # type: ignore[attr-defined]
except Exception as e:
    _mod_renamer_import_error = e


class CombinedPlugin(mobase.IPluginTool):
    def __init__(self, main_plugin, hmm_plugin, autoscroller_plugin):
        super().__init__()
        self._main = main_plugin
        self._hmm = hmm_plugin
        self._autoscroller = autoscroller_plugin

    def init(self, organizer) -> bool:
        main_ok = True
        hmm_ok = True
        auto_ok = True
        if self._main is not None:
            main_ok = bool(self._main.init(organizer))
        if self._hmm is not None:
            hmm_ok = bool(self._hmm.init(organizer))
        if self._autoscroller is not None:
            auto_ok = bool(self._autoscroller.init(organizer))
        return bool(main_ok and hmm_ok and auto_ok)

    def name(self) -> str:
        if self._main is not None:
            return self._main.name()
        return "UMP"

    def author(self) -> str:
        if self._main is not None:
            return self._main.author()
        return ""

    def description(self) -> str:
        if self._main is not None:
            return self._main.description()
        return ""

    def version(self):
        if self._main is not None:
            return self._main.version()
        return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)

    def isActive(self) -> bool:
        if self._main is not None:
            return bool(self._main.isActive())
        return True

    def settings(self):
        if self._main is not None:
            return self._main.settings()
        return []

    def displayName(self) -> str:
        if self._hmm is not None and hasattr(self._hmm, "displayName"):
            return self._hmm.displayName()
        return self.name()

    def tooltip(self) -> str:
        if self._hmm is not None and hasattr(self._hmm, "tooltip"):
            return self._hmm.tooltip()
        return self.description()

    def icon(self):
        if self._hmm is not None and hasattr(self._hmm, "icon"):
            return self._hmm.icon()
        return None

    def display(self):
        if self._hmm is not None and hasattr(self._hmm, "display"):
            return self._hmm.display()
        return None


def _createPlugin():
    main_plugin = FullModSearchPlugin() if FullModSearchPlugin is not None else None
    hmm_plugin = None
    autoscroller_plugin = None
    try:
        if _hmm_module is not None and hasattr(_hmm_module, "createPlugin"):
            hmm_plugin = _hmm_module.createPlugin()
    except Exception:
        hmm_plugin = None
    try:
        if _autoscroller_module is not None and hasattr(_autoscroller_module, "createPlugin"):
            autoscroller_plugin = _autoscroller_module.createPlugin()
    except Exception:
        autoscroller_plugin = None
    if main_plugin is None and hmm_plugin is None:
        return None
    return CombinedPlugin(main_plugin, hmm_plugin, autoscroller_plugin)


def createPlugins():
    plugins = []

    if FullModSearchPlugin is not None:
        plugins.append(FullModSearchPlugin())

    if "AdvancedSearchProPlugin" in globals() and AdvancedSearchProPlugin is not None:
        plugins.append(AdvancedSearchProPlugin())

    try:
        if _hmm_module is not None and hasattr(_hmm_module, "createPlugin"):
            hmm_plugin = _hmm_module.createPlugin()
            if hmm_plugin is not None:
                plugins.append(hmm_plugin)
    except Exception:
        pass

    try:
        if _autoscroller_module is not None and hasattr(_autoscroller_module, "createPlugin"):
            autoscroller_plugin = _autoscroller_module.createPlugin()
            if autoscroller_plugin is not None:
                plugins.append(autoscroller_plugin)
    except Exception:
        pass

    try:
        if _copy_past_module is not None and hasattr(_copy_past_module, "createPlugin"):
            copy_past_plugin = _copy_past_module.createPlugin()
            if copy_past_plugin is not None:
                plugins.append(copy_past_plugin)
    except Exception:
        pass

    try:
        if _mod_renamer_module is not None and hasattr(_mod_renamer_module, "createPlugin"):
            mod_renamer_plugin = _mod_renamer_module.createPlugin()
            if mod_renamer_plugin is not None:
                plugins.append(mod_renamer_plugin)
    except Exception:
        pass

    return plugins


__all__ = ["createPlugins"]
