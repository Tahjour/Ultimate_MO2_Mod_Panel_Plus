import logging
from typing import List, Optional, Union

from esp_viewer.core.data_types import Group, PluginFile, Record
from esp_viewer.core.record_parser import is_valid_signature, parse_record
from esp_viewer.utils.binary_reader import ByteReader


logger = logging.getLogger(__name__)

MAX_RECURSION_DEPTH = 128


def parse_group(
    reader: ByteReader,
    header_size: int,
    plugin: Optional[PluginFile],
    depth: int = 0,
) -> Group:
    if depth > MAX_RECURSION_DEPTH:
        raise ValueError(f"Maximum group nesting depth ({MAX_RECURSION_DEPTH}) exceeded")

    offset = reader.pos
    signature = reader.read(4)
    if signature != b"GRUP":
        raise ValueError(f"Expected GRUP at offset {offset}, got {signature!r}")

    group_size = reader.read_u32()
    label_raw = reader.read(4)
    group_type = reader.read_u32()
    stamp = reader.read_u32()

    unknown1: Optional[int] = None
    unknown2: Optional[int] = None
    if header_size == 24:
        unknown1 = reader.read_u16()
        unknown2 = reader.read_u16()

    children_size = group_size - header_size
    if children_size < 0:
        raise ValueError(
            f"Invalid group size {group_size} at offset {offset} "
            f"(header_size={header_size})",
        )

    end_pos = reader.pos + children_size
    children: List[Union[Group, Record]] = []

    while reader.pos < end_pos:
        if not reader.can_read(4):
            logger.warning(f"Truncated group at offset {offset}")
            break

        sig = reader.peek(4)
        if sig == b"GRUP":
            children.append(parse_group(reader, header_size, plugin, depth + 1))
        elif is_valid_signature(sig):
            children.append(parse_record(reader, header_size, plugin))
        else:
            logger.warning(
                f"Invalid signature {sig!r} at offset {reader.pos}, skipping to end of group"
            )
            reader.pos = end_pos
            break

    if reader.pos != end_pos:
        logger.debug(
            f"Group at offset {offset}: position mismatch (at {reader.pos}, expected {end_pos})"
        )
        reader.pos = end_pos

    return Group(
        label_raw=label_raw,
        group_type=group_type,
        group_size=group_size,
        stamp=stamp,
        unknown1=unknown1,
        unknown2=unknown2,
        children=children,
        raw_offset=offset,
    )
