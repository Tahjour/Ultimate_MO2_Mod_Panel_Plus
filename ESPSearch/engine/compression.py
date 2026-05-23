import zlib
from typing import Optional, Tuple


def decompress_record(raw_data: bytes) -> Tuple[bytes, Optional[str]]:
    if len(raw_data) < 4:
        return raw_data, "Compressed record too short for size prefix"

    expected_size = int.from_bytes(raw_data[:4], "little", signed=False)
    try:
        decompressed = zlib.decompress(raw_data[4:])
    except zlib.error as exc:
        return raw_data, f"Decompression error: {exc}"

    if len(decompressed) != expected_size:
        return (
            decompressed,
            f"Decompressed size mismatch: expected {expected_size}, got {len(decompressed)}",
        )

    return decompressed, None
