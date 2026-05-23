import json
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from esp_viewer.core.localization import decode_text
from esp_viewer.core.plugin_file import parse_plugin
from esp_viewer.core.search_engine import iter_records
from esp_viewer.formatting.record_formatter import DetailNode, StructuredSubrecordParser


def iter_nodes(nodes: Iterable[DetailNode]) -> Iterable[DetailNode]:
    for node in nodes:
        yield node
        if node.children:
            yield from iter_nodes(node.children)


def is_hex_preview(text: str) -> bool:
    if not text:
        return False
    if "bytes total" in text:
        return True
    compact = text.replace(" ", "")
    if not compact or len(compact) % 2 != 0:
        return False
    if all(ch in "0123456789ABCDEF" for ch in compact):
        if " " not in text:
            return len(compact) >= 8
        return True
    if " " not in text and not any(ch in "ABCDEF" for ch in compact):
        return compact.isdigit() and len(compact) >= 8
    return False


def scan_binary_output(path: str, limit: int = 40, include_strings: bool = False) -> Dict[str, object]:
    plugin = parse_plugin(path)
    issues_by_field: Dict[Tuple[str, str], int] = defaultdict(int)
    issues_by_record: Dict[str, int] = defaultdict(int)
    examples: Dict[Tuple[str, str], Dict[str, object]] = {}

    total_records = 0
    total_nodes = 0

    string_like: Dict[str, int] = defaultdict(int)
    string_examples: Dict[str, Dict[str, object]] = {}

    for record in iter_records(plugin.children):
        total_records += 1
        parser = StructuredSubrecordParser(record, plugin)
        try:
            nodes = parser.iter_nodes()
        except Exception:
            continue
        if include_strings:
            for field in record.fields:
                if field.size == 0 or field.size > 256:
                    continue
                text = decode_text(field.raw)
                if text is None or text == "":
                    continue
                sig = field.signature
                string_like[sig] += 1
                if sig not in string_examples:
                    string_examples[sig] = {"form_id": record.form_id, "value": text}

        for node in iter_nodes(nodes):
            total_nodes += 1
            if not is_hex_preview(node.value):
                continue
            sig = node.name.split(" - ", 1)[0] if " - " in node.name else None
            key = (record.signature, sig) if sig and len(sig) == 4 else (record.signature, node.name)
            issues_by_field[key] += 1
            issues_by_record[record.signature] += 1
            if key not in examples:
                examples[key] = {"form_id": record.form_id, "value": node.value}

    top_fields = sorted(issues_by_field.items(), key=lambda item: item[1], reverse=True)[:limit]
    top_records = sorted(issues_by_record.items(), key=lambda item: item[1], reverse=True)[:limit]

    report = {
        "total_records": total_records,
        "total_nodes": total_nodes,
        "binary_nodes": sum(issues_by_field.values()),
        "top_record_signatures": top_records,
        "top_fields": [(key[0], key[1], count, examples[key]) for key, count in top_fields],
    }

    if include_strings:
        current_text_sigs = {
            "EDID",
            "FULL",
            "DESC",
            "CNAM",
            "SNAM",
            "ANAM",
            "RNAM",
            "QNAM",
            "MAST",
        }
        candidates = [
            (sig, count, string_examples[sig])
            for sig, count in string_like.items()
            if sig not in current_text_sigs
        ]
        candidates.sort(key=lambda item: item[1], reverse=True)
        report["string_candidates"] = candidates[:limit]

    return report


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Usage: python -m esp_viewer.utils.scan_binary_output <path> [limit] [--strings]")
        return 2
    path = argv[1]
    include_strings = "--strings" in argv[2:]
    limit = 40
    for arg in argv[2:]:
        if arg.isdigit():
            limit = int(arg)
            break
    report = scan_binary_output(path, limit, include_strings)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
