from typing import Dict, Iterable, List

from ..serializers import filter_fields


class PythonDictFormatter:
    def file_extension(self) -> str:
        return "py"

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        payload = []
        for row in rows:
            payload.append(filter_fields(row, fields))
        with open(path, "w", encoding=str(options.get("encoding", "utf-8"))) as handle:
            handle.write("data = ")
            handle.write(repr(payload))
            handle.write("\n")
        return len(payload)
