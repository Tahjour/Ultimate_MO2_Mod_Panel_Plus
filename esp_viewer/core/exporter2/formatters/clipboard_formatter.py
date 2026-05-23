from typing import Dict, Iterable, List

from ..serializers import filter_fields, format_export_value


class ClipboardFormatter:
    def file_extension(self) -> str:
        return "clipboard"

    def write_table(
        self,
        _path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> str:
        include_header = options.get("include_header", True)
        lines: List[str] = []
        if include_header:
            lines.append("\t".join(fields))
        for row in rows:
            data = filter_fields(row, fields)
            lines.append("\t".join(format_export_value(data.get(field)) for field in fields))
        return "\n".join(lines)
