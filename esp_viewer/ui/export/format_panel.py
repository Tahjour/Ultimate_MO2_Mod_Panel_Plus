from typing import Dict, List, Set

from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class FormatPanel(QGroupBox):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Formats")
        self._json = QCheckBox("JSON", self)
        self._csv = QCheckBox("CSV", self)
        self._tsv = QCheckBox("TSV", self)
        self._txt = QCheckBox("TXT", self)
        self._html = QCheckBox("HTML", self)
        self._xml = QCheckBox("XML", self)
        self._lua = QCheckBox("Lua", self)
        self._python = QCheckBox("Python", self)
        self._clipboard = QCheckBox("Clipboard", self)

        self._json_pretty = QCheckBox("Pretty", self)
        self._json_pretty.setChecked(True)
        self._json_include_null = QCheckBox("Include empty", self)
        self._json_include_null.setChecked(True)

        self._csv_include_header = QCheckBox("Include header", self)
        self._csv_include_header.setChecked(True)
        self._csv_quote_all = QCheckBox("Quote all", self)
        self._csv_encoding = QComboBox(self)
        self._csv_encoding.addItems(["utf-8", "utf-8-sig", "cp1252"])

        self._xml_include_null = QCheckBox("Include empty", self)
        self._xml_include_null.setChecked(True)

        self._html_include_css = QCheckBox("Include CSS", self)
        self._html_include_css.setChecked(True)
        self._html_sortable = QCheckBox("Sortable", self)
        self._html_theme = QComboBox(self)
        self._html_theme.addItems(["light", "dark"])
        self._html_encoding = QComboBox(self)
        self._html_encoding.addItems(["utf-8", "utf-8-sig", "cp1252"])
        self._json.setChecked(True)

        format_layout = QVBoxLayout()
        format_layout.addWidget(self._json)
        format_layout.addWidget(self._csv)
        format_layout.addWidget(self._tsv)
        format_layout.addWidget(self._txt)
        format_layout.addWidget(self._html)
        format_layout.addWidget(self._xml)
        format_layout.addWidget(self._lua)
        format_layout.addWidget(self._python)
        format_layout.addWidget(self._clipboard)

        json_layout = QHBoxLayout()
        json_layout.addWidget(QLabel("JSON options", self))
        json_layout.addStretch(1)

        json_options = QHBoxLayout()
        json_options.addWidget(self._json_pretty)
        json_options.addWidget(self._json_include_null)
        json_options.addStretch(1)

        csv_layout = QHBoxLayout()
        csv_layout.addWidget(QLabel("CSV/TSV options", self))
        csv_layout.addStretch(1)

        csv_options = QHBoxLayout()
        csv_options.addWidget(self._csv_include_header)
        csv_options.addWidget(self._csv_quote_all)
        csv_options.addWidget(QLabel("Encoding", self))
        csv_options.addWidget(self._csv_encoding)
        csv_options.addStretch(1)

        xml_layout = QHBoxLayout()
        xml_layout.addWidget(QLabel("XML options", self))
        xml_layout.addStretch(1)

        xml_options = QHBoxLayout()
        xml_options.addWidget(self._xml_include_null)
        xml_options.addStretch(1)

        html_layout = QHBoxLayout()
        html_layout.addWidget(QLabel("HTML options", self))
        html_layout.addStretch(1)

        html_options = QHBoxLayout()
        html_options.addWidget(self._html_include_css)
        html_options.addWidget(self._html_sortable)
        html_options.addWidget(QLabel("Theme", self))
        html_options.addWidget(self._html_theme)
        html_options.addWidget(QLabel("Encoding", self))
        html_options.addWidget(self._html_encoding)
        html_options.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(format_layout)
        layout.addLayout(json_layout)
        layout.addLayout(json_options)
        layout.addLayout(csv_layout)
        layout.addLayout(csv_options)
        layout.addLayout(xml_layout)
        layout.addLayout(xml_options)
        layout.addLayout(html_layout)
        layout.addLayout(html_options)
        layout.addStretch(1)

        for checkbox in self.findChildren(QCheckBox):
            checkbox.toggled.connect(self._on_any_changed)
        for combo in self.findChildren(QComboBox):
            combo.currentIndexChanged.connect(self._on_any_changed)

    def selected_formats(self) -> Set[str]:
        formats: Set[str] = set()
        if self._json.isChecked():
            formats.add("json")
        if self._csv.isChecked():
            formats.add("csv")
        if self._tsv.isChecked():
            formats.add("tsv")
        if self._txt.isChecked():
            formats.add("txt")
        if self._html.isChecked():
            formats.add("html")
        if self._xml.isChecked():
            formats.add("xml")
        if self._lua.isChecked():
            formats.add("lua")
        if self._python.isChecked():
            formats.add("python")
        if self._clipboard.isChecked():
            formats.add("clipboard")
        return formats

    def set_selected_formats(self, formats: List[str]) -> None:
        self._json.setChecked("json" in formats)
        self._csv.setChecked("csv" in formats)
        self._tsv.setChecked("tsv" in formats)
        self._txt.setChecked("txt" in formats)
        self._html.setChecked("html" in formats)
        self._xml.setChecked("xml" in formats)
        self._lua.setChecked("lua" in formats)
        self._python.setChecked("python" in formats)
        self._clipboard.setChecked("clipboard" in formats)

    def format_options(self) -> Dict[str, Dict[str, object]]:
        options: Dict[str, Dict[str, object]] = {}
        options["json"] = {
            "pretty": self._json_pretty.isChecked(),
            "include_null": self._json_include_null.isChecked(),
        }
        csv_options = {
            "include_header": self._csv_include_header.isChecked(),
            "quote_all": self._csv_quote_all.isChecked(),
            "encoding": self._csv_encoding.currentText(),
        }
        options["csv"] = csv_options
        options["tsv"] = csv_options
        options["txt"] = {
            "include_header": self._csv_include_header.isChecked(),
            "encoding": self._csv_encoding.currentText(),
        }
        options["clipboard"] = {"include_header": self._csv_include_header.isChecked()}
        options["xml"] = {"include_null": self._xml_include_null.isChecked()}
        options["html"] = {
            "include_css": self._html_include_css.isChecked(),
            "sortable": self._html_sortable.isChecked(),
            "theme": self._html_theme.currentText(),
            "encoding": self._html_encoding.currentText(),
        }

    def _on_any_changed(self, *_) -> None:
        self.changed.emit()
        return options

    def state(self) -> Dict[str, object]:
        return {
            "formats": sorted(self.selected_formats()),
            "json_pretty": self._json_pretty.isChecked(),
            "json_include_null": self._json_include_null.isChecked(),
            "csv_include_header": self._csv_include_header.isChecked(),
            "csv_quote_all": self._csv_quote_all.isChecked(),
            "csv_encoding": self._csv_encoding.currentText(),
            "xml_include_null": self._xml_include_null.isChecked(),
            "html_include_css": self._html_include_css.isChecked(),
            "html_sortable": self._html_sortable.isChecked(),
            "html_theme": self._html_theme.currentText(),
            "html_encoding": self._html_encoding.currentText(),
        }

    def apply_state(self, state: Dict[str, object]) -> None:
        formats = state.get("formats", [])
        if isinstance(formats, list):
            self.set_selected_formats([str(item) for item in formats])
        self._json_pretty.setChecked(bool(state.get("json_pretty", True)))
        self._json_include_null.setChecked(bool(state.get("json_include_null", True)))
        self._csv_include_header.setChecked(bool(state.get("csv_include_header", True)))
        self._csv_quote_all.setChecked(bool(state.get("csv_quote_all", False)))
        csv_encoding = str(state.get("csv_encoding", "utf-8"))
        csv_index = self._csv_encoding.findText(csv_encoding)
        if csv_index >= 0:
            self._csv_encoding.setCurrentIndex(csv_index)
        self._xml_include_null.setChecked(bool(state.get("xml_include_null", True)))
        self._html_include_css.setChecked(bool(state.get("html_include_css", True)))
        self._html_sortable.setChecked(bool(state.get("html_sortable", False)))
        html_theme = str(state.get("html_theme", "light"))
        theme_index = self._html_theme.findText(html_theme)
        if theme_index >= 0:
            self._html_theme.setCurrentIndex(theme_index)
        html_encoding = str(state.get("html_encoding", "utf-8"))
        html_index = self._html_encoding.findText(html_encoding)
        if html_index >= 0:
            self._html_encoding.setCurrentIndex(html_index)
