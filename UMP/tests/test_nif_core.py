import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


UMP_PATH = Path(__file__).parents[1]
PACKAGE_NAME = "ump_nif_test_package"


def _load_module(full_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(UMP_PATH)]
sys.modules[PACKAGE_NAME] = package

qtcore = types.ModuleType("PyQt6.QtCore")


class _Thread:
    pass


class _Signal:
    def emit(self, *_args):
        pass


qtcore.QThread = _Thread
qtcore.pyqtSignal = lambda *_args: _Signal()
pyqt6 = types.ModuleType("PyQt6")
pyqt6.QtCore = qtcore
sys.modules.setdefault("PyQt6", pyqt6)
sys.modules.setdefault("PyQt6.QtCore", qtcore)

_load_module(f"{PACKAGE_NAME}.archive_core", UMP_PATH / "archive_core.py")
nif_core = _load_module(f"{PACKAGE_NAME}.nif_core", UMP_PATH / "nif_core.py")


class NifCoreTests(unittest.TestCase):
    def test_parser_reads_textures_from_extracted_bytes(self) -> None:
        data = b"Gamebryo File Format\ntextures/actors/test/body.dds\x00"

        textures = nif_core.LightweightNifParser().parse_bytes(data)

        self.assertEqual(textures, ["textures/actors/test/body.dds"])

    def test_cache_preserves_archive_origin_and_rejects_other_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scope = {
                "include_archives": True,
                "only_active": False,
                "archive_fingerprints": [["example.bsa", 10, 20]],
            }
            index = nif_core.NifTextureIndex(Path(directory))
            index.set_scope(scope)
            index.add_nif(
                "[Game Data]",
                "meshes/example.nif",
                ["textures/example.dds"],
                4.0,
                source_kind="bsa",
                container_path="Skyrim - Meshes0.bsa",
                is_game=True,
            )
            self.assertTrue(index.save_to_cache())

            loaded = nif_core.NifTextureIndex(Path(directory))
            self.assertTrue(loaded.load_from_cache(scope))
            entry, _score = loaded.find_nifs_by_texture("example.dds")[0]
            self.assertEqual(entry.source_kind, "bsa")
            self.assertEqual(entry.container_path, "Skyrim - Meshes0.bsa")
            self.assertTrue(entry.is_game)

            other_scope = dict(scope, include_archives=False)
            rejected = nif_core.NifTextureIndex(Path(directory))
            self.assertFalse(rejected.load_from_cache(other_scope))

    def test_replacing_entry_removes_old_texture_backlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index = nif_core.NifTextureIndex(Path(directory))
            index.add_nif("Mod", "meshes/item.nif", ["textures/old.dds"])
            index.add_nif("Mod", "meshes/item.nif", ["textures/new.dds"])

            self.assertEqual(index.find_nifs_by_texture("old.dds"), [])
            self.assertEqual(len(index.find_nifs_by_texture("new.dds")), 1)


if __name__ == "__main__":
    unittest.main()
