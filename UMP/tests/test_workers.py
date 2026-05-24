import importlib.util
import sys
import types
import unittest
from pathlib import Path


UMP_PATH = Path(__file__).parents[1]
PACKAGE_NAME = "ump_workers_test_package"


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
workers = _load_module(f"{PACKAGE_NAME}.workers", UMP_PATH / "workers.py")


class WorkerTests(unittest.TestCase):
    def test_file_search_batches_results_and_closes_catalog(self) -> None:
        sources = [
            archive_core.AssetSource(
                owner="Archive Mod",
                virtual_path=f"meshes/search_{number}.nif",
                source_kind="bsa",
                container_path="ArchiveMod.bsa",
                archive_name="ArchiveMod.bsa",
            )
            for number in range(120)
        ]

        class FakeCatalog:
            instance = None

            def __init__(self, *_args, **_kwargs):
                self.errors = []
                self.closed = False
                FakeCatalog.instance = self

            def iter_sources(self, *_args, **_kwargs):
                yield from sources

            def close(self):
                self.closed = True

        original_catalog = workers.AssetCatalog
        try:
            workers.AssetCatalog = FakeCatalog
            worker = workers.FileSearchWorker(object(), "search", [".nif"], search_in_bsa=True)
            worker.results_batch = _CaptureSignal()
            worker.progress = _CaptureSignal()
            worker.finished_search = _CaptureSignal()
            worker.warning = _CaptureSignal()

            worker.run()

            self.assertEqual([len(call[0]) for call in worker.results_batch.calls], [50, 50, 20])
            self.assertEqual(worker.finished_search.calls, [(120,)])
            self.assertTrue(FakeCatalog.instance.closed)
        finally:
            workers.AssetCatalog = original_catalog

    def test_file_search_cancellation_stops_before_emitting_hits(self) -> None:
        class FakeCatalog:
            instance = None

            def __init__(self, *_args, **_kwargs):
                self.errors = []
                self.closed = False
                FakeCatalog.instance = self

            def iter_sources(self, *_args, **_kwargs):
                yield archive_core.AssetSource(
                    owner="Mod",
                    virtual_path="meshes/search.nif",
                    source_kind="loose",
                    container_path="meshes/search.nif",
                )

            def close(self):
                self.closed = True

        original_catalog = workers.AssetCatalog
        try:
            workers.AssetCatalog = FakeCatalog
            worker = workers.FileSearchWorker(object(), "search", [".nif"])
            worker.results_batch = _CaptureSignal()
            worker.progress = _CaptureSignal()
            worker.finished_search = _CaptureSignal()
            worker.warning = _CaptureSignal()
            worker.cancel()

            worker.run()

            self.assertEqual(worker.results_batch.calls, [])
            self.assertEqual(worker.finished_search.calls, [(0,)])
            self.assertTrue(FakeCatalog.instance.closed)
        finally:
            workers.AssetCatalog = original_catalog


if __name__ == "__main__":
    unittest.main()
