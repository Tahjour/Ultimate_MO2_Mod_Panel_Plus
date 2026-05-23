import csv
from typing import Dict, Iterable, List

from ..serializers import filter_fields, format_export_value


class CSVExportFormatter:
    def __init__(self, delimiter: str = ",", extension: str = "csv") -> None:
        self._delimiter = delimiter
        self._extension = extension

    def file_extension(self) -> str:
        return self._extension

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        include_header = options.get("include_header", True)
        quote_all = options.get("quote_all", False)
        encoding = options.get("encoding", "utf-8")
        quoting = csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL
        count = 0
        with open(path, "w", encoding=str(encoding), newline="") as handle:
            writer = csv.writer(handle, delimiter=self._delimiter, quoting=quoting)
            if include_header:
                writer.writerow(fields)
            for row in rows:
                data = filter_fields(row, fields)
                writer.writerow([format_export_value(data.get(field)) for field in fields])
                count += 1
        return count
