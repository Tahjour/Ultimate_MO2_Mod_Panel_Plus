from typing import Dict, Iterable, List
from xml.etree.ElementTree import Element, SubElement, ElementTree

from ..serializers import filter_fields, format_export_value


class XMLExportFormatter:
    def file_extension(self) -> str:
        return "xml"

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        include_null = bool(options.get("include_null", True))
        root = Element("export")
        count = 0
        for row in rows:
            item = SubElement(root, "item")
            data = filter_fields(row, fields)
            for field in fields:
                value = data.get(field)
                if value in (None, "") and not include_null:
                    continue
                child = SubElement(item, field)
                child.text = format_export_value(value)
            count += 1
        ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        return count
