import struct
from typing import List, Optional, Tuple

from esp_viewer.core.compression import decompress_record
from esp_viewer.core.data_types import Field, PluginFile, Record
from esp_viewer.core.localization import resolve_string
from esp_viewer.utils.binary_reader import ByteReader


COMPRESSED_FLAG = 0x00040000

def is_valid_signature(sig: bytes) -> bool:
    if len(sig) != 4:
        return False
    if sig == b"GRUP":
        return True
    return all(65 <= b <= 90 or 48 <= b <= 57 or b == 95 for b in sig)


def parse_subrecords(data: bytes) -> Tuple[List[Field], Optional[str]]:
    fields: List[Field] = []
    pos = 0
    error: Optional[str] = None
    pending_size: Optional[int] = None
    data_len = len(data)

    while pos < data_len:
        if pos + 6 > data_len:
            remaining = data_len - pos
            error = f"Insufficient data for subrecord header ({remaining} bytes remaining)"
            break

        signature = data[pos : pos + 4].decode("ascii", errors="replace")
        size = struct.unpack_from("<H", data, pos + 4)[0]
        pos += 6

        if signature == "XXXX":
            if size != 4 or pos + 4 > data_len:
                error = "Invalid XXXX subrecord"
                break
            pending_size = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            continue

        if pending_size is not None:
            size = pending_size
            pending_size = None

        if pos + size > data_len:
            error = (
                f"Subrecord {signature} at offset {pos - 6}: "
                f"declared size {size}, but only {data_len - pos} bytes available"
            )
            break

        raw = data[pos : pos + size]
        pos += size
        fields.append(Field(signature=signature, size=size, raw=raw))

    return fields, error


def extract_string_field(
    fields: List[Field],
    signatures: Tuple[str, ...],
    plugin: Optional[PluginFile],
) -> Optional[str]:
    for f in fields:
        if f.signature not in signatures:
            continue
        text = resolve_string(f, plugin)
        if text:
            return text

    return None


def parse_record(
    reader: ByteReader,
    header_size: int,
    plugin: Optional[PluginFile],
) -> Record:
    offset = reader.pos
    signature = reader.read(4).decode("ascii", errors="replace")
    data_size = reader.read_u32()
    flags = reader.read_u32()
    form_id = reader.read_u32()
    vci1 = reader.read_u32()

    form_version: Optional[int] = None
    vci2: Optional[int] = None
    if header_size == 24:
        form_version = reader.read_u16()
        vci2 = reader.read_u16()

    raw_data = reader.read(data_size)
    is_compressed = bool(flags & COMPRESSED_FLAG)
    parse_error: Optional[str] = None

    if is_compressed:
        raw_data, parse_error = decompress_record(raw_data)

    fields, fields_error = parse_subrecords(raw_data)
    if fields_error:
        if parse_error:
            parse_error = f"{parse_error}; {fields_error}"
        else:
            parse_error = fields_error

    editor_id = extract_string_field(fields, ("EDID",), None)
    full_name = extract_string_field(fields, ("FULL", "DESC"), plugin)

    return Record(
        signature=signature,
        data_size=data_size,
        flags=flags,
        form_id=form_id,
        vci1=vci1,
        form_version=form_version,
        vci2=vci2,
        fields=fields,
        is_compressed=is_compressed,
        editor_id=editor_id,
        full_name=full_name,
        parse_error=parse_error,
        raw_offset=offset,
    )
