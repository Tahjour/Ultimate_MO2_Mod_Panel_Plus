import importlib
import os
import sys
import types
from typing import Optional

import mobase
from PyQt6.QtWidgets import QLabel, QTreeView, QVBoxLayout, QWidget


_contentfilter_loaded = False
_contentfilter_error: Optional[Exception] = None
_contentfilter_modules: dict = {}


def _load_contentfilter_modules() -> dict:
    global _contentfilter_loaded
    global _contentfilter_error
    global _contentfilter_modules

    if _contentfilter_loaded:
        return _contentfilter_modules

    base_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "ContentFilter")
    )

    if not os.path.isdir(base_dir):
        _contentfilter_error = FileNotFoundError(base_dir)
        _contentfilter_loaded = True
        return _contentfilter_modules

    try:
        package_name = "ContentFilter"
        if package_name not in sys.modules:
            package = types.ModuleType(package_name)
            package.__path__ = [base_dir]
            package.__package__ = package_name
            sys.modules[package_name] = package

        importlib.invalidate_caches()

        filter_proxy = importlib.import_module(
            f"{package_name}.filter_proxy"
        )
        scanner = importlib.import_module(
            f"{package_name}.scanner"
        )
        ui_panel = importlib.import_module(
            f"{package_name}.ui_panel"
        )

        _contentfilter_modules = {
            "ContentFilterProxy": filter_proxy.ContentFilterProxy,
            "FilterMode": filter_proxy.FilterMode,
            "ModContentScanner": scanner.ModContentScanner,
            "FilterControlPanel": ui_panel.FilterControlPanel,
        }
    except Exception as e:
        _contentfilter_error = e

    _contentfilter_loaded = True
    return _contentfilter_modules


class ContentFilterTab(QWidget):
    def __init__(self, parent, organizer: "mobase.IOrganizer", mods_view: "QTreeView"):
        super().__init__(parent)
        self._organizer = organizer
        self._mods_view = mods_view
        self._filter_proxy = None
        self._panel = None
        self._modules = None
        self._base_model = self._mods_view.model() if self._mods_view else None

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        self._modules = _load_contentfilter_modules()
        if _contentfilter_error or not self._modules or not self._mods_view:
            message = "ContentFilter is unavailable"
            if _contentfilter_error:
                message = f"ContentFilter load failed: {_contentfilter_error}"
            elif not self._mods_view:
                message = "Mods view not available"
            label = QLabel(message, self)
            label.setWordWrap(True)
            layout.addWidget(label)
            return

        self._ensure_integration()
        if self._filter_proxy is None:
            proxy_cls = self._modules["ContentFilterProxy"]
            scanner_cls = self._modules["ModContentScanner"]
            self._filter_proxy = proxy_cls(scanner_cls(self._organizer))

        panel_cls = self._modules["FilterControlPanel"]
        self._panel = panel_cls(self._filter_proxy, self._organizer, self)
        layout.addWidget(self._panel)
        if hasattr(self._panel, "filterToggled"):
            self._panel.filterToggled.connect(self._apply_proxy_state)
        if hasattr(self._panel, "is_enabled"):
            self._apply_proxy_state(self._panel.is_enabled())

    def _ensure_integration(self) -> None:
        if not self._modules or not self._mods_view:
            return

        proxy_cls = self._modules["ContentFilterProxy"]
        scanner_cls = self._modules["ModContentScanner"]

        current_model = self._mods_view.model()
        if isinstance(current_model, proxy_cls):
            self._filter_proxy = current_model
            if self._base_model is None:
                self._base_model = current_model.sourceModel()
            return

        if self._filter_proxy is None:
            self._filter_proxy = proxy_cls(scanner_cls(self._organizer))

        if current_model is not None and self._base_model is None:
            self._base_model = current_model

        if self._base_model is not None and self._filter_proxy.sourceModel() is not self._base_model:
            self._filter_proxy.setSourceModel(self._base_model)

    def _apply_proxy_state(self, enabled: bool) -> None:
        if not self._mods_view or not self._filter_proxy:
            return

        if enabled:
            current_model = self._mods_view.model()
            if current_model is not self._filter_proxy:
                if self._base_model is None:
                    self._base_model = current_model
                if self._base_model is not None and self._filter_proxy.sourceModel() is not self._base_model:
                    self._filter_proxy.setSourceModel(self._base_model)
                self._mods_view.setModel(self._filter_proxy)
            return

        if self._mods_view.model() is self._filter_proxy:
            source = self._filter_proxy.sourceModel()
            if source is not None:
                self._mods_view.setModel(source)
            elif self._base_model is not None:
                self._mods_view.setModel(self._base_model)

    def refresh_if_needed(self):
        self._ensure_integration()
        if self._panel and hasattr(self._panel, "is_enabled"):
            self._apply_proxy_state(self._panel.is_enabled())


__all__ = ["ContentFilterTab"]
