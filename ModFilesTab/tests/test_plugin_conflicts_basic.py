import os
from pathlib import Path

from esp_viewer.core.conflict_analyzer import analyze_conflicts_for_plugin, _load_plugins, _read_masters_quick
from esp_viewer.core.plugin_file import parse_plugin


def _write_minimal_plugin(path: Path, masters: list[str], form_id: int, value: int) -> None:
    header = bytearray()
    header.extend(b"TES4")
    data = bytearray()
    data.extend(b"HEDR")
    data.extend((12).to_bytes(2, "little"))
    data.extend(b"\x00" * 12)
    for name in masters:
        encoded = name.encode("ascii") + b"\x00"
        data.extend(b"MAST")
        data.extend(len(encoded).to_bytes(2, "little"))
        data.extend(encoded)
    header.extend(len(data).to_bytes(4, "little"))
    header.extend((0).to_bytes(4, "little"))
    header.extend((0).to_bytes(4, "little"))
    header.extend((0).to_bytes(4, "little"))
    body = header + data

    rec = bytearray()
    rec.extend(b"GMST")
    sub = bytearray()
    sub.extend(b"EDID")
    name = b"test_conflict"
    sub.extend(len(name).to_bytes(2, "little"))
    sub.extend(name)
    sub.extend(b"DATA")
    sub.extend((4).to_bytes(2, "little"))
    sub.extend(value.to_bytes(4, "little", signed=False))
    rec.extend(len(sub).to_bytes(4, "little"))
    rec.extend((0).to_bytes(4, "little"))
    rec.extend(form_id.to_bytes(4, "little", signed=False))
    rec.extend((0).to_bytes(4, "little"))
    rec.extend(sub)

    with path.open("wb") as handle:
        handle.write(body)
        handle.write(rec)


def test_formid_resolution_avoids_false_conflict(tmp_path: Path) -> None:
    master = tmp_path / "Skyrim.esm"
    _write_minimal_plugin(master, [], 0x00001234, 1)

    a = tmp_path / "A.esp"
    b = tmp_path / "B.esp"

    _write_minimal_plugin(a, [master.name], 0x01001234, 2)
    _write_minimal_plugin(b, [master.name], 0x01001234, 3)

    master_plugin = parse_plugin(str(master))
    a_plugin = parse_plugin(str(a))
    b_plugin = parse_plugin(str(b))

    result_a = analyze_conflicts_for_plugin(a_plugin, str(tmp_path))
    result_b = analyze_conflicts_for_plugin(b_plugin, str(tmp_path))

    keys = [key for key in result_a.statuses if key[0] == "GMST"]
    assert keys
    key = keys[0]

    status_a = result_a.statuses[key]
    status_b = result_b.statuses[key]

    assert status_a is not None
    assert status_b is not None


def test_read_masters_quick_matches_written_header(tmp_path: Path) -> None:
    path = tmp_path / "Example.esm"
    _write_minimal_plugin(path, ["Skyrim.esm", "Update.esm"], 0x00001234, 1)
    masters = _read_masters_quick(str(path))
    masters_lower = {os.path.basename(name).lower() for name in masters}
    assert "skyrim.esm" in masters_lower
    assert "update.esm" in masters_lower


def test_load_plugins_filters_unrelated_plugins(tmp_path: Path) -> None:
    master = tmp_path / "Skyrim.esm"
    _write_minimal_plugin(master, [], 0x00001234, 1)

    related = tmp_path / "Related.esp"
    _write_minimal_plugin(related, [master.name], 0x01001234, 2)

    unrelated = tmp_path / "Unrelated.esp"
    _write_minimal_plugin(unrelated, [], 0x02001234, 3)

    target_plugin = parse_plugin(str(related))
    plugins = _load_plugins(str(tmp_path), target_plugin)
    names = {os.path.basename(p.path).lower() for p in plugins}

    assert os.path.basename(related).lower() in names
    assert os.path.basename(master).lower() in names
    assert os.path.basename(unrelated).lower() not in names
