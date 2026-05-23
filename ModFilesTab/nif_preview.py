import importlib.util
import re
from pathlib import Path
from typing import Optional


_PARSER: Optional[type] = None
_PARSER_TRIED = False


def _load_parser() -> Optional[type]:
    global _PARSER
    global _PARSER_TRIED
    if _PARSER_TRIED:
        return _PARSER
    _PARSER_TRIED = True
    base_dir = Path(__file__).resolve().parents[1]
    parser_path = base_dir / "NIF Analyzer" / "nif_parser.py"
    if not parser_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("nif_analyzer_parser", parser_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    parser = getattr(module, "NifParser", None)
    if parser is None:
        return None
    _PARSER = parser
    return _PARSER


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _format_counts(counts: dict[str, int], limit: int = 20) -> list[str]:
    return [f"{name}: {count}" for name, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]]


def build_nif_preview(path: Path, max_items: int = 60) -> Optional[tuple[str, str]]:
    parser = _load_parser()
    if parser is not None:
        try:
            summary = parser(path).parse()
        except Exception:
            summary = None
        if summary is not None:
            lines: list[str] = []
            lines.append(f"Version: {summary.get('version', '')} ({summary.get('game', '')})")
            lines.append(f"User version: {summary.get('user_version', '')}")
            lines.append(f"Stream version: {summary.get('stream_version', '')}")
            lines.append(f"Blocks: {summary.get('num_blocks', 0)}")
            lines.append(f"Shapes: {summary.get('shape_count', 0)}")
            lines.append(f"Meshes: {summary.get('mesh_count', 0)}")
            lines.append(f"Vertices: {summary.get('total_vertices', 0)}")
            lines.append(f"Triangles: {summary.get('total_triangles', 0)}")
            lines.append(f"Has skinning: {summary.get('has_skinning', False)}")
            lines.append(f"Bones: {summary.get('bone_count', 0)}")
            lines.append(f"Has collision: {summary.get('has_collision', False)}")
            lines.append(f"Has animation: {summary.get('has_animation', False)}")

            block_counts = summary.get("block_type_counts", {}) or {}
            if block_counts:
                lines.append("Blocks (top):")
                for item in _format_counts(block_counts, 30):
                    lines.append(f"  {item}")

            textures = _unique(summary.get("textures", []) or [])
            if textures:
                lines.append(f"Textures ({len(textures)}):")
                for tex in textures[:max_items]:
                    lines.append(f"  {tex}")
                if len(textures) > max_items:
                    lines.append(f"  ... {len(textures) - max_items} more")

            return "NIF preview", "\n".join(lines)

    try:
        data = path.read_bytes()
    except Exception:
        return None

    pattern = re.compile(rb"textures[/\\][^\x00\r\n\xff]{3,200}\.dds", re.IGNORECASE)
    textures_raw = [m.group(0).decode("utf-8", errors="ignore") for m in pattern.finditer(data[:5 * 1024 * 1024])]
    textures = _unique(textures_raw)

    lines = [f"Size: {len(data)} bytes"]
    if textures:
        lines.append(f"Textures ({len(textures)}):")
        for tex in textures[:max_items]:
            lines.append(f"  {tex}")
        if len(textures) > max_items:
            lines.append(f"  ... {len(textures) - max_items} more")
    return "NIF preview", "\n".join(lines)
