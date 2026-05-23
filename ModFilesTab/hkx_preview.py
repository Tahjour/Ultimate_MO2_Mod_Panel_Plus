import re
from pathlib import Path
from typing import Optional


_VERSION_RE = re.compile(rb"hk_[0-9]{4}\.[0-9]\.[0-9]-r[0-9]", re.IGNORECASE)


def build_hkx_preview(path: Path, scan_limit: int = 256 * 1024) -> Optional[tuple[str, str]]:
    try:
        data = path.read_bytes()
    except Exception:
        return None

    head = data[:scan_limit]
    stripped = head.lstrip()
    is_xml = stripped.startswith(b"<?xml")

    version = ""
    match = _VERSION_RE.search(head)
    if match:
        version = match.group(0).decode("ascii", errors="ignore")

    section_names = []
    for name in (b"__data__", b"__classnames__", b"__types__", b"__type__", b"__assets__", b"__properties__"):
        if name in head:
            section_names.append(name.decode("ascii", errors="ignore"))

    lines = [f"Size: {len(data)} bytes"]
    lines.append(f"Format: {'XML' if is_xml else 'Binary'}")
    if version:
        lines.append(f"Version: {version}")
    if section_names:
        lines.append("Sections:")
        for name in section_names:
            lines.append(f"  {name}")
    return "HKX preview", "\n".join(lines)
