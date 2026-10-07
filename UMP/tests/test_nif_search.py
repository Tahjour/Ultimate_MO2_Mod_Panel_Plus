import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_nif_core import nif_core, archive_core, _load_module, PACKAGE_NAME, UMP_PATH, _CaptureSignal

search = _load_module(f"{PACKAGE_NAME}.nif_search", UMP_PATH / "nif_search.py")


class FakeModList:
    def __init__(self, states=None, priorities=None):
        self.states = states or {"Low": 2, "High": 2, "Disabled": 0}
        self.priorities = priorities or {"Low": 10, "High": 20, "Disabled": 100}

    def allMods(self):
        return list(self.states)

    def state(self, name):
        return self.states.get(name, 0)

    def priority(self, name):
        return self.priorities.get(name, -1)


class FakeOrganizer:
    def __init__(self, infos=None):
        self.infos = infos or {}
        self.mods = FakeModList()
        self.archives = {}
        self.calls = []

    def modList(self):
        return self.mods

    def findFileInfos(self, parent, predicate):
        self.calls.append(parent)
        return [info for path, info in self.infos.items()
                if path.rpartition("/")[0] == parent and predicate(info)]

    def resolvePath(self, path):
        return self.archives.get(path.casefold(), "")


def info(entry, origins=None, archive=""):
    return SimpleNamespace(filePath=entry.container_path if not archive else entry.relative_path,
                           origins=origins or [entry.mod_name], archive=archive)


def mesh(owner, path="meshes/item.nif", textures=None, archive="", error=""):
    return nif_core.NifTextureEntry(
        owner, path, textures if textures is not None else ["textures/item.dds"],
        source_kind="bsa" if archive else "loose",
        container_path=archive or f"D:/mods/{owner}/{path}",
        is_game=owner == "[Game Data]", parse_error=error,
    )


class WinnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.index = nif_core.NifTextureIndex(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_winner_before_matching_inactive_and_identical_basenames(self):
        loser = mesh("Low", textures=["textures/old.dds"])
        winner = mesh("High", textures=["textures/new.dds"])
        disabled = mesh("Disabled", "meshes/inactive.nif")
        other = mesh("Low", "meshes/other/item.nif")
        for entry in (loser, winner, disabled, other):
            self.index.add_entry(entry)
        organizer = FakeOrganizer({winner.relative_path: info(winner, ["High", "Low"]),
                                   other.relative_path: info(other)})
        snapshot = search.ProfileResolver(organizer).snapshot(self.index)
        self.assertEqual(snapshot.index.nif_count, 2)
        self.assertEqual(snapshot.index.find_nifs_by_texture("old.dds"), [])
        self.assertEqual(snapshot.index.find_nifs_by_texture("new.dds")[0][0].mod_name, "High")

    def test_textureless_and_unreadable_winners_never_use_losing_references(self):
        for error in ("", "Corrupt archive member"):
            with self.subTest(error=error):
                self.index.clear()
                winner = mesh("High", textures=[], error=error)
                self.index.add_entry(mesh("Low"))
                self.index.add_entry(winner)
                snapshot = search.ProfileResolver(FakeOrganizer({winner.relative_path: info(winner)})).snapshot(self.index)
                self.assertEqual(snapshot.index.find_nifs_by_texture("item.dds"), [])
                self.assertEqual(len(snapshot.index.find_textures_by_nif("item.nif")), 1)
                self.assertEqual(bool(snapshot.warnings), bool(error))

    def test_actual_bsa_container_wins_over_mod_priority_and_unloaded_archive(self):
        loose = mesh("High")
        bsa = mesh("Low", archive="D:/mods/Low/Loaded.bsa")
        unloaded = mesh("High", archive="D:/mods/High/Unused.bsa")
        organizer = FakeOrganizer({bsa.relative_path: info(bsa, ["Low", "High"], "Loaded.bsa")})
        organizer.archives["loaded.bsa"] = bsa.container_path
        for entry in (loose, bsa, unloaded):
            self.index.add_entry(entry)
        snapshot = search.ProfileResolver(organizer).snapshot(self.index)
        self.assertEqual(snapshot.index.entries()[0].container_path, bsa.container_path)

    def test_provider_order_and_missing_when_only_inactive_providers_exist(self):
        texture = "textures/item.dds"
        loose = archive_core.AssetSource("Low", texture, "loose", "D:/mods/Low/textures/item.dds")
        bsa = archive_core.AssetSource("High", texture, "bsa", "D:/mods/High/A.bsa", archive_name="A.bsa")
        unused = archive_core.AssetSource("High", texture, "bsa", "D:/mods/High/Unused.bsa", archive_name="Unused.bsa")
        inactive = archive_core.AssetSource("Disabled", texture, "loose", "D:/mods/Disabled/textures/item.dds")
        organizer = FakeOrganizer()
        organizer.archives["a.bsa"] = bsa.container_path
        resolver = search.ProfileResolver(organizer)
        resolver.loaded_archives = {"a.bsa": 2}
        metadata = SimpleNamespace(filePath=loose.container_path, archive="", origins=["Low", "High"])
        providers = resolver.resolve([inactive, unused, bsa, loose], metadata)
        self.assertEqual([p.source for p in providers], [loose, bsa, inactive, unused])
        self.assertTrue(providers[0].winning)
        self.assertIn("Inactive", providers[2].label)
        self.assertIn("Unloaded", providers[3].label)
        self.assertFalse(any(p.winning for p in resolver.resolve([inactive], None)))

    def test_multiple_archives_same_mod_and_physical_duplicate_container(self):
        texture = "textures/item.dds"
        sources = [archive_core.AssetSource("High", texture, "bsa", path, archive_name=Path(path).name)
                   for path in ("D:/mods/High/A.bsa", "D:/mods/High/B.bsa", "D:/mods/Disabled/B.bsa")]
        organizer = FakeOrganizer()
        organizer.archives = {"a.bsa": sources[0].container_path, "b.bsa": sources[1].container_path}
        resolver = search.ProfileResolver(organizer)
        resolver.loaded_archives = {"a.bsa": 0, "b.bsa": 1}
        providers = resolver.resolve(sources, SimpleNamespace(filePath="meshes/item.nif", archive="B.bsa", origins=["High"]))
        self.assertEqual(providers[0].source, sources[1])
        self.assertTrue(providers[0].winning)
        self.assertFalse(next(p for p in providers if p.source is sources[2]).loaded)

    def test_unindexed_winner_is_reported_without_fallback(self):
        self.index.add_entry(mesh("Low"))
        high = mesh("High")
        snapshot = search.ProfileResolver(FakeOrganizer({high.relative_path: info(high)})).snapshot(self.index)
        self.assertEqual(snapshot.index.nif_count, 0)
        self.assertIn("Unindexed", snapshot.warnings[0])

    def test_cache_migration_and_empty_error_entries(self):
        self.index.add_entry(mesh("High", textures=[], error="read failed"))
        self.assertTrue(self.index.save_to_cache())
        loaded = nif_core.NifTextureIndex(Path(self.temp.name))
        self.assertTrue(loaded.load_from_cache())
        self.assertEqual(loaded.entries()[0].parse_error, "read failed")
        cache = Path(self.temp.name) / "nif_texture_index.json"
        data = json.loads(cache.read_text(encoding="utf-8"))
        data["version"] = 4
        cache.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(nif_core.NifTextureIndex(Path(self.temp.name)).load_from_cache())

    def test_worker_limits_after_winners_and_keeps_index_private(self):
        infos = {}
        for number in range(105):
            entry = mesh("High", f"meshes/item{number}.nif")
            self.index.add_entry(mesh("Low", entry.relative_path))
            self.index.add_entry(entry)
            infos[entry.relative_path] = info(entry, ["High", "Low"])
        worker = search.NifSearchWorker(FakeOrganizer(infos), self.index, "item", True, 3)
        worker.ready = _CaptureSignal()
        worker.failed = _CaptureSignal()
        worker.run()
        self.assertEqual(worker.failed.calls, [])
        generation, payload = worker.ready.calls[0]
        self.assertEqual((generation, payload["total"], len(payload["results"])), (3, 105, 100))
        self.assertEqual(self.index.nif_count, 210)
        cancelled = search.NifSearchWorker(FakeOrganizer(infos), self.index, "item", True, 4)
        cancelled.ready = _CaptureSignal()
        cancelled.cancel()
        cancelled.run()
        self.assertEqual(cancelled.ready.calls, [])


if __name__ == "__main__":
    unittest.main()
