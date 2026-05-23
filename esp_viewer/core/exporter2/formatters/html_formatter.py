from html import escape
from typing import Dict, Iterable, List

from ..serializers import filter_fields, format_export_value


class HTMLExportFormatter:
    def file_extension(self) -> str:
        return "html"

    def write_table(
        self,
        path: str,
        rows: Iterable[dict],
        fields: List[str],
        options: Dict[str, object],
    ) -> int:
        include_css = bool(options.get("include_css", True))
        sortable = bool(options.get("sortable", False))
        theme = options.get("theme", "light")
        encoding = str(options.get("encoding", "utf-8"))
        count = 0
        with open(path, "w", encoding=encoding) as handle:
            handle.write("<html><head><meta charset=\"utf-8\">")
            if include_css:
                background = "#1e1e1e" if theme == "dark" else "#ffffff"
                text = "#e6e6e6" if theme == "dark" else "#111111"
                handle.write(
                    "<style>body{font-family:Arial, sans-serif;background:%s;color:%s;}"
                    "table{border-collapse:collapse;width:100%%;}"
                    "th,td{border:1px solid #999;padding:4px 6px;text-align:left;}"
                    "th{background:#444;color:#fff;}"
                    "</style>" % (background, text)
                )
            if sortable:
                handle.write(
                    "<script>function sortTable(n){var table=document.getElementById('exportTable');"
                    "var rows=Array.prototype.slice.call(table.rows,1);"
                    "var asc=table.getAttribute('data-sort-col')!=n||table.getAttribute('data-sort-dir')=='desc';"
                    "rows.sort(function(a,b){var x=a.cells[n].innerText.toLowerCase();"
                    "var y=b.cells[n].innerText.toLowerCase();if(x<y){return asc?-1:1;}"
                    "if(x>y){return asc?1:-1;}return 0;});"
                    "for(var i=0;i<rows.length;i++){table.tBodies[0].appendChild(rows[i]);}"
                    "table.setAttribute('data-sort-col',n);"
                    "table.setAttribute('data-sort-dir',asc?'asc':'desc');}</script>"
                )
            handle.write("</head><body>")
            handle.write("<table id=\"exportTable\"><thead><tr>")
            for index, field in enumerate(fields):
                if sortable:
                    handle.write(f"<th onclick=\"sortTable({index})\">{escape(field)}</th>")
                else:
                    handle.write(f"<th>{escape(field)}</th>")
            handle.write("</tr></thead><tbody>")
            for row in rows:
                data = filter_fields(row, fields)
                handle.write("<tr>")
                for field in fields:
                    value = format_export_value(data.get(field))
                    handle.write(f"<td>{escape(value)}</td>")
                handle.write("</tr>")
                count += 1
            handle.write("</tbody></table></body></html>")
        return count
