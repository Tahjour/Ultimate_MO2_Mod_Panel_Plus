"""Debounced, ancestor-preserving filters for the two asset trees."""

import re
from PyQt6.QtCore import Qt, QTimer


def filter_terms(text):
    return [match.group(1).casefold() if match.group(1) is not None else match.group(2).casefold()
            for match in re.finditer(r'"([^\"]*)"|(\S+)', text) if match.group(1) or match.group(2)]


class AssetTreeFilter:
    def __init__(self, tree, edit, label, counted_type):
        self.tree, self.edit, self.label = tree, edit, label
        self.counted_type = counted_type
        self.baseline = None
        self.suffix = ""
        self.timer = QTimer(tree)
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.apply)
        edit.textChanged.connect(self.schedule)

    def schedule(self, text):
        if text.strip():
            self.timer.start()
        else:
            self.timer.stop()
            self.apply()

    def items(self):
        def walk(item):
            yield item
            for index in range(item.childCount()):
                yield from walk(item.child(index))
        for index in range(self.tree.topLevelItemCount()):
            yield from walk(self.tree.topLevelItem(index))

    def reset(self, clear=False):
        self.timer.stop()
        self.baseline = None
        if clear:
            self.edit.blockSignals(True)
            self.edit.clear()
            self.edit.blockSignals(False)

    def apply(self):
        terms = filter_terms(self.edit.text())
        if terms and self.baseline is None:
            self.baseline = [(item, item.isExpanded()) for item in self.items()]
        visible = total = 0

        def visit(item, inherited=False, context=""):
            nonlocal visible, total
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            kind = data.get("type")
            searchable = kind in ("mesh", "nif", "texture", "provider")
            own_text = data.get("search", " ".join(item.text(i) for i in range(item.columnCount())))
            text = f"{context} {own_text}".casefold()
            matched = searchable and all(term in text for term in terms)
            descendants = False
            for index in range(item.childCount()):
                descendants = visit(item.child(index), inherited or matched,
                                    text if searchable else context) or descendants
            shown = not terms or inherited or matched or descendants or kind == "property"
            item.setHidden(not shown)
            if terms and shown and item.childCount():
                item.setExpanded(True)
            if kind == self.counted_type:
                total += 1
                visible += shown
            return shown and kind != "property"

        self.tree.setUpdatesEnabled(False)
        try:
            for index in range(self.tree.topLevelItemCount()):
                visit(self.tree.topLevelItem(index))
            if not terms and self.baseline is not None:
                for item, expanded in self.baseline:
                    item.setExpanded(expanded)
                self.baseline = None
            if any(item.isHidden() for item in self.tree.selectedItems()):
                self.tree.clearSelection()
        finally:
            self.tree.setUpdatesEnabled(True)
        noun = "mesh paths" if self.counted_type == "mesh" else "NIFs" if self.counted_type == "nif" else "referenced textures"
        message = f"{visible}/{total} {noun}" if terms else f"{total} {noun}"
        if terms and not visible:
            message += " - no filter matches"
        self.label.setText(message + self.suffix)

    def expand_all(self):
        self.tree.expandAll()

    def collapse_all(self):
        self.tree.collapseAll()
