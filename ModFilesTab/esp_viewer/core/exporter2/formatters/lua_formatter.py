from typing import Dict, Iterable, List

from ..serializers import filter_fields, format_export_value


class LuaExportFormatter:
    def file_extension(self) -> str:
        return "lua"

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        count = 0
        with open(path, "w", encoding=str(options.get("encoding", "utf-8"))) as handle:
            handle.write("return {\n")
            for row in rows:
                data = filter_fields(row, fields)
                handle.write("  { ")
                parts = []
                for field in fields:
                    value = format_export_value(data.get(field))
                    parts.append(f"{field} = {self._lua_value(value)}")
                handle.write(", ".join(parts))
                handle.write(" },\n")
                count += 1
            handle.write("}\n")
        return count

    def _lua_value(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"\"{escaped}\""
