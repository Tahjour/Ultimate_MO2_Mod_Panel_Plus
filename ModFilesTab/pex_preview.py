import re
import struct
from pathlib import Path
from typing import Optional


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def can_read(self, size: int) -> bool:
        return self.pos + size <= len(self.data)

    def read_u8(self) -> int:
        if not self.can_read(1):
            return 0
        val = self.data[self.pos]
        self.pos += 1
        return val

    def read_u16(self) -> int:
        if not self.can_read(2):
            return 0
        val = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return val

    def read_u32(self) -> int:
        if not self.can_read(4):
            return 0
        val = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return val

    def read_u64(self) -> int:
        if not self.can_read(8):
            return 0
        val = struct.unpack_from("<Q", self.data, self.pos)[0]
        self.pos += 8
        return val

    def read_str(self, length_size: int) -> str:
        if length_size == 2:
            length = self.read_u16()
        else:
            length = self.read_u32()
        if length == 0:
            return ""
        if length > 20000 or not self.can_read(length):
            return ""
        value = self.data[self.pos:self.pos + length].decode("utf-8", errors="ignore")
        self.pos += length
        return value


def _detect_length_size(reader: _Reader) -> int:
    start = reader.pos
    if reader.can_read(2):
        length16 = struct.unpack_from("<H", reader.data, start)[0]
        if 0 <= length16 <= 20000 and start + 2 + length16 <= len(reader.data):
            return 2
    if reader.can_read(4):
        length32 = struct.unpack_from("<I", reader.data, start)[0]
        if 0 <= length32 <= 20000 and start + 4 + length32 <= len(reader.data):
            return 4
    return 2


def _is_identifier(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value))


def build_pex_preview(path: Path, max_strings: int = 4000, max_functions: int = 400) -> Optional[tuple[str, str]]:
    try:
        data = path.read_bytes()
    except Exception:
        return None

    reader = _Reader(data)
    magic = reader.read_u32()
    if magic != 0xFA57C0D3:
        return None

    major = reader.read_u16()
    minor = reader.read_u16()
    game_id = reader.read_u16()
    _reserved = reader.read_u16()
    compile_time = reader.read_u64()

    length_size = _detect_length_size(reader)
    source_file = reader.read_str(length_size)
    user = reader.read_str(length_size)
    machine = reader.read_str(length_size)

    string_count = reader.read_u32()
    strings: list[str] = []
    truncated = False
    for i in range(string_count):
        if i >= max_strings:
            truncated = True
            break
        strings.append(reader.read_str(length_size))

    func_candidates = [s for s in strings if _is_identifier(s)]
    func_candidates = func_candidates[:max_functions]

    lines: list[str] = []
    lines.append(f"Version: {major}.{minor}")
    lines.append(f"Game ID: {game_id}")
    lines.append(f"Compilation time: {compile_time}")
    if source_file:
        lines.append(f"Source: {source_file}")
    if user or machine:
        lines.append(f"Compiler: {user} @ {machine}")
    lines.append(f"Strings: {string_count}")
    if strings:
        lines.append("String table:")
        for value in strings[:200]:
            lines.append(f"  {value}")
        if len(strings) > 200:
            lines.append(f"  ... {len(strings) - 200} more")
    if truncated:
        lines.append(f"String table truncated at {max_strings}")
    if func_candidates:
        lines.append("Functions (from string table):")
        for value in func_candidates:
            lines.append(f"  {value}")

    return "PEX preview", "\n".join(lines)
