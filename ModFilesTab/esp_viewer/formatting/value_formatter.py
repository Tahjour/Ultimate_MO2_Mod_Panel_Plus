from esp_viewer.core.data_types import RECORD_FLAGS


def format_file_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_flags(flags: int) -> str:
    names = []
    for bit, name in RECORD_FLAGS.items():
        if flags & bit:
            names.append(name)
    if names:
        return f"0x{flags:08X} ({', '.join(names)})"
    return f"0x{flags:08X}"
