from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .archive_core import AssetSource, BsaArchive, normalize_virtual_path


PREVIEW_EXTENSIONS = {".dds", ".nif"}
PREVIEW_SIZE = QSize(1600, 950)


def can_preview_virtual_path(path: str) -> bool:
    return Path(path or "").suffix.lower() in PREVIEW_EXTENSIONS


def preview_asset_source(parent: QWidget, source: AssetSource, organizer=None) -> bool:
    if source is None or not can_preview_virtual_path(source.virtual_path):
        QMessageBox.information(parent, "Preview", "Only DDS and NIF files can be previewed here.")
        return False

    if _try_organizer_preview(parent, organizer, source):
        return True

    data = b""
    if source.source_kind == "bsa":
        try:
            data = _read_archive_source(source)
        except Exception as exc:
            QMessageBox.warning(parent, "Preview", f"Could not extract archive file:\n{exc}")
            return False

    plugin = _find_preview_plugin(Path(source.virtual_path).suffix.lower())
    if plugin is None:
        QMessageBox.information(
            parent,
            "Preview Unavailable",
            "MO2 did not expose a DDS/NIF previewer to UMP. Make sure the preview plugin is enabled.",
        )
        return False

    try:
        if source.source_kind == "loose" and source.physical_path:
            widget = plugin.genFilePreview(source.physical_path, PREVIEW_SIZE)
        elif data and bool(getattr(plugin, "supportsArchives", lambda: False)()):
            widget = plugin.genDataPreview(data, source.virtual_path, PREVIEW_SIZE)
        else:
            QMessageBox.information(
                parent,
                "Preview Unavailable",
                "The selected archive source needs a preview plugin with archive-data support.",
            )
            return False
    except Exception as exc:
        QMessageBox.warning(parent, "Preview Error", f"Could not launch preview:\n{exc}")
        return False

    if not isinstance(widget, QWidget):
        QMessageBox.warning(parent, "Preview Error", "The preview plugin did not return a widget.")
        return False

    _show_preview_dialog(parent, widget, source.filename)
    return True


def preview_nif_entry(parent: QWidget, entry, organizer=None) -> bool:
    source = asset_source_from_nif_entry(entry, organizer)
    if source is None:
        QMessageBox.information(parent, "Preview", "Could not resolve the selected NIF source.")
        return False
    return preview_asset_source(parent, source, organizer)


def asset_source_from_nif_entry(entry, organizer=None) -> Optional[AssetSource]:
    if entry is None:
        return None

    virtual_path = normalize_virtual_path(getattr(entry, "relative_path", ""))
    if not virtual_path:
        return None

    owner = getattr(entry, "mod_name", "")
    source_kind = getattr(entry, "source_kind", "loose") or "loose"
    container_path = getattr(entry, "container_path", "") or ""
    is_game = bool(getattr(entry, "is_game", False))

    if source_kind == "bsa":
        return AssetSource(
            owner=owner,
            virtual_path=virtual_path,
            source_kind="bsa",
            container_path=container_path,
            archive_name=Path(container_path).name,
            is_game=is_game,
        )

    physical_path = container_path
    if not physical_path and organizer is not None and owner:
        try:
            mod = organizer.modList().getMod(owner)
            if mod:
                physical_path = str(Path(mod.absolutePath()) / Path(*virtual_path.split("/")))
        except Exception:
            physical_path = ""

    if not physical_path:
        return None

    return AssetSource(
        owner=owner,
        virtual_path=virtual_path,
        source_kind="loose",
        container_path=physical_path,
        physical_path=physical_path,
        is_game=is_game,
    )


def _read_archive_source(source: AssetSource) -> bytes:
    archive = BsaArchive(Path(source.container_path))
    try:
        member = archive.find_member(source.virtual_path)
        if member is None:
            raise FileNotFoundError(source.location_text)
        return archive.extract(member)
    finally:
        archive.close()


def _try_organizer_preview(parent: QWidget, organizer, source: AssetSource) -> bool:
    if organizer is None:
        return False
    candidates = []
    if source.source_kind == "loose" and source.physical_path:
        candidates.append(source.physical_path)
    candidates.append(source.virtual_path)

    for method_name in ("previewFile", "showPreview", "openPreview", "displayPreview"):
        method = getattr(organizer, method_name, None)
        if not callable(method):
            continue
        for value in candidates:
            for args in ((value,), (value, parent), (value, PREVIEW_SIZE), (value, PREVIEW_SIZE, parent)):
                try:
                    result = method(*args)
                except TypeError:
                    continue
                except Exception:
                    break
                if isinstance(result, QWidget):
                    _show_preview_dialog(parent, result, source.filename)
                    return True
                if result:
                    return True
    return False


def _find_preview_plugin(extension: str):
    key = extension.lower().lstrip(".")
    app = QApplication.instance()
    if app is None:
        return None

    handlers = getattr(app, "ump_preview_file_handlers", {})
    handler = handlers.get(key) if isinstance(handlers, dict) else None
    if handler is not None and _plugin_supports_extension(handler, key):
        return handler

    seen = set()
    for root in list(QApplication.allWidgets()) + [app]:
        for obj in _walk_qobjects(root, seen):
            if _plugin_supports_extension(obj, key):
                return obj
    return None


def _walk_qobjects(root, seen: set[int]):
    if root is None:
        return
    marker = id(root)
    if marker in seen:
        return
    seen.add(marker)
    yield root
    try:
        children = root.children()
    except Exception:
        children = []
    for child in children:
        yield from _walk_qobjects(child, seen)


def _plugin_supports_extension(plugin, extension: str) -> bool:
    if not callable(getattr(plugin, "genFilePreview", None)):
        return False
    try:
        supported = plugin.supportedExtensions()
    except Exception:
        return False
    return extension in {str(ext).lower().lstrip(".") for ext in supported}


def _show_preview_dialog(parent: QWidget, preview_widget: QWidget, title: str) -> None:
    dialog = QDialog(parent)
    dialog.setObjectName("PreviewDialog")
    dialog.setWindowTitle("Preview")
    dialog.resize(PREVIEW_SIZE.width(), PREVIEW_SIZE.height())

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(4)

    label = QLabel(title or "Preview", dialog)
    label.setTextInteractionFlags(label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(label)
    layout.addWidget(preview_widget, 1)

    bottom = QHBoxLayout()
    bottom.addStretch()
    close_btn = QPushButton("Close", dialog)
    close_btn.clicked.connect(dialog.close)
    bottom.addWidget(close_btn)
    layout.addLayout(bottom)

    app = QApplication.instance()
    if app is not None:
        dialogs = getattr(app, "_ump_preview_dialogs", [])
        dialogs.append(dialog)
        setattr(app, "_ump_preview_dialogs", dialogs)

        def release_dialog():
            try:
                dialogs.remove(dialog)
            except ValueError:
                pass

        dialog.destroyed.connect(release_dialog)

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


__all__ = [
    "asset_source_from_nif_entry",
    "can_preview_virtual_path",
    "preview_asset_source",
    "preview_nif_entry",
]
