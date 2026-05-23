import importlib.util
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "archive_core.py"
SPEC = importlib.util.spec_from_file_location("ump_archive_core_test", MODULE_PATH)
archive_core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = archive_core
SPEC.loader.exec_module(archive_core)


def _write_bsa(path: Path, version: int, files: dict[str, bytes], compress: bool = False) -> None:
    grouped: dict[str, list[tuple[str, bytes]]] = {}
    for virtual_path, data in files.items():
        folder, name = virtual_path.rsplit("/", 1)
        grouped.setdefault(folder, []).append((name, data))

    folder_struct = struct.Struct("<QIIQ" if version == 105 else "<QII")
    flags = 0x1 | 0x2
    blocks: list[tuple[str, list[tuple[str, bytes, int]]]] = []
    names_blob = bytearray()
    folder_blocks_size = 0

    for folder, entries in grouped.items():
        stored_entries = []
        folder_bytes = folder.encode("utf-8") + b"\x00"
        folder_blocks_size += 1 + len(folder_bytes) + 16 * len(entries)
        for name, raw in entries:
            payload = struct.pack("<I", len(raw)) + zlib.compress(raw) if compress else raw
            raw_size = len(payload) | (0x40000000 if compress else 0)
            stored_entries.append((name, payload, raw_size))
            names_blob.extend(name.encode("utf-8") + b"\x00")
        blocks.append((folder, stored_entries))

    folder_records_size = folder_struct.size * len(blocks)
    data_offset = 36 + folder_records_size + folder_blocks_size + len(names_blob)
    payload_offset = data_offset
    folder_records = bytearray()
    folder_blocks = bytearray()
    payloads = bytearray()

    for folder, entries in blocks:
        if version == 105:
            folder_records.extend(folder_struct.pack(0, len(entries), 0, 0))
        else:
            folder_records.extend(folder_struct.pack(0, len(entries), 0))
        folder_bytes = folder.encode("utf-8") + b"\x00"
        folder_blocks.extend(bytes([len(folder_bytes)]) + folder_bytes)
        for _name, payload, raw_size in entries:
            folder_blocks.extend(struct.pack("<QII", 0, raw_size, payload_offset))
            payloads.extend(payload)
            payload_offset += len(payload)

    header = struct.pack(
        "<4s8I",
        b"BSA\x00",
        version,
        36,
        flags,
        len(blocks),
        len(files),
        sum(len(folder.encode("utf-8")) + 1 for folder in grouped),
        len(names_blob),
        0,
    )
    path.write_bytes(header + folder_records + folder_blocks + names_blob + payloads)


class ArchiveCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_v105_lists_and_extracts_uncompressed_members(self) -> None:
        archive_path = self.root / "sample.bsa"
        expected = b"Gamebryo File Format, Version 20.2.0.7\ntextures/demo/a.dds"
        _write_bsa(archive_path, 105, {"meshes/demo/a.nif": expected})

        archive = archive_core.BsaArchive(archive_path)

        self.assertEqual([item.virtual_path for item in archive.members], ["meshes/demo/a.nif"])
        self.assertEqual(archive.extract(archive.members[0]), expected)

    def test_v104_extracts_zlib_compressed_member(self) -> None:
        archive_path = self.root / "compressed.bsa"
        expected = b"textures/demo/compressed.dds" * 20
        _write_bsa(archive_path, 104, {"meshes/demo/compressed.nif": expected}, compress=True)

        archive = archive_core.BsaArchive(archive_path)

        self.assertTrue(archive.members[0].compressed)
        self.assertEqual(archive.extract(archive.members[0]), expected)

    def test_corrupt_archive_raises_readable_error(self) -> None:
        archive_path = self.root / "broken.bsa"
        archive_path.write_bytes(b"BSA\x00")

        with self.assertRaisesRegex(ValueError, "header"):
            tuple(archive_core.BsaArchive(archive_path).members)

    def test_catalog_includes_mod_and_game_archive_members(self) -> None:
        mod_root = self.root / "mods" / "Disabled Mod"
        game_data = self.root / "game" / "Data"
        mod_root.mkdir(parents=True)
        game_data.mkdir(parents=True)
        _write_bsa(mod_root / "DisabledAssets.bsa", 105, {"meshes/mod/hidden.nif": b"nif"})
        _write_bsa(game_data / "Skyrim - Meshes0.bsa", 105, {"meshes/game/base.nif": b"nif"})

        class FakeMod:
            def absolutePath(self):
                return str(mod_root)

        class FakeModList:
            def allMods(self):
                return ["Disabled Mod"]

            def state(self, _name):
                return 0

        class FakeDirectory:
            def absolutePath(self):
                return str(game_data)

        class FakeGame:
            def dataDirectory(self):
                return FakeDirectory()

        class FakeOrganizer:
            def modList(self):
                return FakeModList()

            def getMod(self, _name):
                return FakeMod()

            def modsPath(self):
                return str(self.root / "mods")

            def managedGame(self):
                return FakeGame()

        organizer = FakeOrganizer()
        organizer.root = self.root
        catalog = archive_core.AssetCatalog(
            organizer,
            include_archives=True,
            exhaustive=True,
        )
        paths = {source.virtual_path for source in catalog.iter_sources([".nif"])}

        self.assertEqual(paths, {"meshes/mod/hidden.nif", "meshes/game/base.nif"})

    def test_real_skyrim_lz4_archive_when_configured(self) -> None:
        archive_path = os.environ.get("UMP_TEST_SKYRIM_MESHES_BSA")
        lz4_path = os.environ.get("MO2_LZ4_PATH")
        if not archive_path or not lz4_path:
            self.skipTest("Set UMP_TEST_SKYRIM_MESHES_BSA and MO2_LZ4_PATH for integration coverage")

        archive = archive_core.BsaArchive(Path(archive_path), Path(lz4_path))
        member = next(item for item in archive.members if item.virtual_path.endswith(".nif"))

        self.assertTrue(archive.extract(member).startswith(b"Gamebryo File Format"))


if __name__ == "__main__":
    unittest.main()
