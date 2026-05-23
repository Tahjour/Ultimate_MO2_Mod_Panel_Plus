import json
from typing import Dict, Iterable, List

from ..serializers import filter_fields


class JSONExportFormatter:
    def file_extension(self) -> str:
        return "json"

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        pretty = bool(options.get("pretty", True))
        include_null = bool(options.get("include_null", True))
        payload = []
        for row in rows:
            filtered = filter_fields(row, fields)
            if not include_null:
                filtered = {key: value for key, value in filtered.items() if value not in (None, "")}
            payload.append(filtered)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2 if pretty else None)
        return len(payload)

    def write_payload(
        self,
        path: str,
        payload: Dict[str, object],
        options: Dict[str, object],
    ) -> None:
        pretty = bool(options.get("pretty", True))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2 if pretty else None)
