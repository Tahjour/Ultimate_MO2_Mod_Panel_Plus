from typing import Dict, Iterable, List

from ..serializers import filter_fields, format_export_value


class TXTExportFormatter:
    def file_extension(self) -> str:
        return "txt"

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        include_header = options.get("include_header", True)
        count = 0
        with open(path, "w", encoding=str(options.get("encoding", "utf-8"))) as handle:
            if include_header:
                handle.write("\t".join(fields) + "\n")
            for row in rows:
                data = filter_fields(row, fields)
                line = "\t".join(format_export_value(data.get(field)) for field in fields)
                handle.write(line + "\n")
                count += 1
        return count
