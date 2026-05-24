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


class _CaptureSignal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


qtcore.QThread = _Thread
qtcore.pyqtSignal = lambda *_args: _Signal()
pyqt6 = types.ModuleType("PyQt6")
pyqt6.QtCore = qtcore
sys.modules.setdefault("PyQt6", pyqt6)
sys.modules.setdefault("PyQt6.QtCore", qtcore)

archive_core = _load_module(f"{PACKAGE_NAME}.archive_core", UMP_PATH / "archive_core.py")
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
            index.add_texture_provider(
                "textures/example.dds",
                archive_core.AssetSource(
                    owner="Texture Pack",
                    virtual_path="textures/example.dds",
                    source_kind="loose",
                    container_path="mods/Texture Pack/textures/example.dds",
                    physical_path="mods/Texture Pack/textures/example.dds",
                ),
            )
            index.add_texture_provider(
                "textures/example.dds",
                archive_core.AssetSource(
                    owner="[Game Data]",
                    virtual_path="textures/example.dds",
                    source_kind="bsa",
                    container_path="Skyrim - Textures0.bsa",
                    archive_name="Skyrim - Textures0.bsa",
                    is_game=True,
                ),
            )
            self.assertTrue(index.save_to_cache())

            loaded = nif_core.NifTextureIndex(Path(directory))
            self.assertTrue(loaded.load_from_cache(scope))
            entry, _score = loaded.find_nifs_by_texture("example.dds")[0]
            self.assertEqual(entry.source_kind, "bsa")
            self.assertEqual(entry.container_path, "Skyrim - Meshes0.bsa")
            self.assertTrue(entry.is_game)
            providers = loaded.find_texture_providers("textures/example.dds")
            self.assertEqual([provider.source_kind for provider in providers], ["loose", "bsa"])
            self.assertEqual(providers[1].archive_name, "Skyrim - Textures0.bsa")
            self.assertEqual(loaded.find_texture_providers("textures/missing.dds"), [])

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

    def test_worker_publishes_private_index_with_texture_providers(self) -> None:
        nif_source = archive_core.AssetSource(
            owner="[Game Data]",
            virtual_path="meshes/demo/item.nif",
            source_kind="bsa",
            container_path="Skyrim - Meshes0.bsa",
            archive_name="Skyrim - Meshes0.bsa",
            is_game=True,
        )
        texture_sources = [
            archive_core.AssetSource(
                owner="Texture Override",
                virtual_path="textures/demo/item.dds",
                source_kind="loose",
                container_path="mods/Texture Override/textures/demo/item.dds",
                physical_path="mods/Texture Override/textures/demo/item.dds",
            ),
            archive_core.AssetSource(
                owner="[Game Data]",
                virtual_path="textures/demo/item.dds",
                source_kind="bsa",
                container_path="Skyrim - Textures0.bsa",
                archive_name="Skyrim - Textures0.bsa",
                is_game=True,
            ),
        ]

        class FakeCatalog:
            instances = []

            def __init__(self, *_args, **_kwargs):
                self.errors = []
                self.closed = False
                FakeCatalog.instances.append(self)

            def iter_sources(self, extensions, **_kwargs):
                if extensions == [".nif"]:
                    yield nif_source
                else:
                    yield from texture_sources

            def read_bytes(self, _source):
                return b"Gamebryo File Format\ntextures/demo/item.dds\x00"

            def close(self):
                self.closed = True

        original_catalog = nif_core.AssetCatalog
        original_scope = nif_core.build_index_scope
        try:
            nif_core.AssetCatalog = FakeCatalog
            nif_core.build_index_scope = lambda *_args: {
                "include_archives": True,
                "only_active": False,
                "archive_fingerprints": [],
            }
            with tempfile.TemporaryDirectory() as directory:
                seed = nif_core.NifTextureIndex(Path(directory))
                worker = nif_core.NifIndexWorker(
                    object(),
                    seed,
                    only_active=False,
                    incremental=False,
                    include_archives=True,
                )
                worker.started = _CaptureSignal()
                worker.phase = _CaptureSignal()
                worker.progress = _CaptureSignal()
                worker.index_ready = _CaptureSignal()
                worker.finished = _CaptureSignal()
                worker.error = _CaptureSignal()
                worker.warning = _CaptureSignal()

                worker.run()

                self.assertEqual(worker.error.calls, [])
                built_index = worker.index_ready.calls[0][0]
                self.assertIsNot(built_index, seed)
                providers = built_index.find_texture_providers("textures/demo/item.dds")
                self.assertEqual(len(providers), 2)
                self.assertEqual(providers[1].archive_name, "Skyrim - Textures0.bsa")
                self.assertTrue(FakeCatalog.instances[0].closed)
        finally:
            nif_core.AssetCatalog = original_catalog
            nif_core.build_index_scope = original_scope


if __name__ == "__main__":
    unittest.main()
