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

    def run_search(self, organizer, query, nif=False, session=None):
        worker = search.NifSearchWorker(organizer, self.index, query, nif, 3, session)
        worker.ready = _CaptureSignal()
        worker.failed = _CaptureSignal()
        worker.run()
        self.assertEqual(worker.failed.calls, [])
        return worker.ready.calls[0][1]

    def test_losing_matches_inactive_paths_and_identical_basenames(self):
        loser = mesh("Low", textures=["textures/old.dds"])
        winner = mesh("High", textures=["textures/new.dds"])
        disabled = mesh("Disabled", "meshes/inactive.nif")
        other = mesh("Low", "meshes/other/item.nif")
        for entry in (loser, winner, disabled, other):
            self.index.add_entry(entry)
        organizer = FakeOrganizer({winner.relative_path: info(winner, ["High", "Low"]),
                                   other.relative_path: info(other)})
        result = self.run_search(organizer, "textures/old.dds")["results"][0]
        self.assertEqual(result.winner.entry.mod_name, "High")
        self.assertEqual(result.winner.score, 0)
        self.assertEqual(result.versions[1].score, 100)
        groups = self.run_search(organizer, "item.nif", nif=True)["results"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(len({group.virtual_path for group in groups}), 2)
        inactive_group = self.run_search(organizer, "inactive.nif", nif=True)["results"][0]
        self.assertIsNone(inactive_group.winner)
        self.assertFalse(inactive_group.versions[0].provider.active)

    def test_textureless_and_unreadable_winners_keep_independent_scores(self):
        for error in ("", "Corrupt archive member"):
            with self.subTest(error=error):
                self.index.clear()
                winner = mesh("High", textures=[], error=error)
                self.index.add_entry(mesh("Low"))
                self.index.add_entry(winner)
                payload = self.run_search(FakeOrganizer({winner.relative_path: info(winner)}), "textures/item.dds")
                group = payload["results"][0]
                self.assertEqual(group.winner.score, None if error else 0)
                self.assertEqual(group.versions[1].score, 100)
                self.assertEqual(bool(payload["snapshot"].warnings), bool(error))

    def test_actual_bsa_container_wins_over_mod_priority_and_unloaded_archive(self):
        loose = mesh("High")
        bsa = mesh("Low", archive="D:/mods/Low/Loaded.bsa")
        unloaded = mesh("High", archive="D:/mods/High/Unused.bsa")
        organizer = FakeOrganizer({bsa.relative_path: info(bsa, ["Low", "High"], "Loaded.bsa")})
        organizer.archives["loaded.bsa"] = bsa.container_path
        for entry in (loose, bsa, unloaded):
            self.index.add_entry(entry)
        group = self.run_search(organizer, "item.nif", nif=True)["results"][0]
        self.assertEqual(group.winner.entry.container_path, bsa.container_path)
        self.assertFalse(next(v for v in group.versions if v.entry is unloaded).provider.loaded)

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
        payload = self.run_search(FakeOrganizer({high.relative_path: info(high)}), "item.nif", nif=True)
        self.assertIsNone(payload["results"][0].winner)
        self.assertEqual(payload["results"][0].winner_origin, "High")
        self.assertIn("Unindexed", payload["snapshot"].warnings[0])

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
        self.assertEqual(len(payload["results"][0].versions), 2)
        self.assertEqual(self.index.nif_count, 210)
        cancelled = search.NifSearchWorker(FakeOrganizer(infos), self.index, "item", True, 4)
        cancelled.ready = _CaptureSignal()
        cancelled.cancel()
        cancelled.run()
        self.assertEqual(cancelled.ready.calls, [])

    def test_coffin_exact_child_and_close_parent(self):
        query = "textures/dlc01/architecture/hearse/coffin01.dds"
        path = "meshes/_byoh/architecture/byohhouse/coffin/byohcoffin01.nif"
        winner = mesh("High", path, ["textures/pbr/dlc01/architecture/hearse/coffin01.dds"])
        loser = mesh("Low", path, [query])
        self.index.add_entry(loser)
        self.index.add_entry(winner)
        payload = self.run_search(FakeOrganizer({path: info(winner, ["High", "Low"])}), query)
        group = payload["results"][0]
        self.assertEqual((group.best_score, group.winner.score), (100, 80))
        self.assertEqual([v.score for v in group.versions], [80, 100])
        self.assertEqual(payload["counts"]["Exact Match"], 1)
        self.assertEqual(payload["counts"]["Close Match"], 0)

    def test_match_category_boundaries_and_full_nif_path(self):
        self.assertEqual([search.match_label(n) for n in (None, 0, 1, 69, 70, 99, 100)],
                         ["Unreadable", "No Match", "Partial Match", "Partial Match",
                          "Close Match", "Close Match", "Exact Match"])
        winner = mesh("High")
        self.index.add_entry(winner)
        self.assertEqual(self.index.find_textures_by_nif("MESHES\\ITEM.NIF")[0][1], 100)

    def test_warm_queries_reuse_metadata_and_do_not_resolve_unrelated_textures(self):
        entry = mesh("High")
        other = mesh("High", "meshes/unrelated/other.nif", ["textures/unrelated/other.dds"])
        self.index.add_entry(entry)
        self.index.add_entry(other)
        organizer = FakeOrganizer({entry.relative_path: info(entry), other.relative_path: info(other)})
        session = search.ResolutionSession(organizer, self.index)
        first = self.run_search(organizer, "textures/item.dds", session=session)
        calls = list(organizer.calls)
        second = self.run_search(organizer, "item.nif", nif=True, session=session)
        self.assertEqual(organizer.calls, calls)
        self.assertEqual(calls, ["meshes"])
        self.assertEqual(first["snapshot"].textures, {})
        self.assertIs(second["snapshot"].index, self.index)
        worker = search.TextureResolutionWorker(session, entry.textures, 10)
        worker.ready, worker.failed = _CaptureSignal(), _CaptureSignal()
        worker.run()
        self.assertEqual(worker.failed.calls, [])
        self.assertEqual(organizer.calls, ["meshes", "textures"])
        self.assertEqual(worker.ready.calls[0][1], {"item.dds": ((), ())})
        worker.run()
        self.assertEqual(organizer.calls, ["meshes", "textures"])

    def test_new_session_reflects_priority_change_and_cancelled_lock_wait(self):
        high, low = mesh("High"), mesh("Low")
        self.index.add_entry(high)
        self.index.add_entry(low)
        organizer = FakeOrganizer({high.relative_path: info(high)})
        old = search.ResolutionSession(organizer, self.index)
        self.assertIs(self.run_search(organizer, "item", nif=True, session=old)["results"][0].winner.entry, high)
        organizer.infos[high.relative_path] = info(low)
        fresh = search.ResolutionSession(organizer, self.index)
        self.assertIs(self.run_search(organizer, "item", nif=True, session=fresh)["results"][0].winner.entry, low)
        fresh.lock.acquire()
        try:
            worker = search.NifSearchWorker(organizer, self.index, "item", True, 8, fresh)
            worker.cancel()
            worker.ready = _CaptureSignal()
            worker.run()
            self.assertEqual(worker.ready.calls, [])
        finally:
            fresh.lock.release()

    def test_derived_lookup_maps_survive_update_removal_and_version5_cache(self):
        high = mesh("High", textures=["textures/old.dds"])
        self.index.add_entry(high)
        replacement = mesh("High", textures=["textures/new.dds"])
        self.index.add_entry(replacement)
        self.assertEqual(self.index.mesh_versions(high.relative_path), [replacement])
        self.assertEqual(self.index.find_nifs_by_texture("old.dds"), [])
        self.assertTrue(self.index.save_to_cache())
        loaded = nif_core.NifTextureIndex(Path(self.temp.name))
        self.assertEqual(loaded.CACHE_VERSION, 5)
        self.assertTrue(loaded.load_from_cache())
        self.assertEqual(loaded.find_nifs_by_texture("new.dds")[0][0].mod_name, "High")
        self.assertEqual(len(loaded.mesh_versions(high.relative_path)), 1)
        loaded.invalidate_mod("High")
        self.assertEqual(loaded.find_textures_by_nif("item"), [])
        self.assertEqual(loaded.find_nifs_by_texture("new.dds"), [])

    def test_selected_texture_resolves_loose_mod_bsa_game_bsa_and_missing(self):
        texture = "textures/item.dds"
        loose = archive_core.AssetSource("High", texture, "loose", "D:/mods/High/item.dds")
        mod = archive_core.AssetSource("Low", texture, "bsa", "D:/mods/Low/Mod.bsa", archive_name="Mod.bsa")
        game = archive_core.AssetSource("[Game Data]", texture, "bsa", "D:/game/Base.bsa", archive_name="Base.bsa", is_game=True)
        for source in (game, mod, loose):
            self.index.add_texture_provider(texture, source)
        organizer = FakeOrganizer({texture: SimpleNamespace(filePath=loose.container_path, archive="", origins=["High", "Low", "data"])})
        organizer.archives = {"mod.bsa": mod.container_path, "base.bsa": game.container_path}
        session = search.ResolutionSession(organizer, self.index)
        self.assertTrue(session.acquire(lambda: False))
        try:
            session.resolver.loaded_archives = {"mod.bsa": 1, "base.bsa": 0}
            result = session.texture_providers([texture, "textures/missing.dds"], lambda: False)
        finally:
            session.lock.release()
        self.assertEqual([p.source for p in result["item.dds"][0]], [loose, mod, game])
        self.assertTrue(result["item.dds"][0][0].winning)
        self.assertEqual(result["missing.dds"], ((), ()))

    def test_cancelled_save_preserves_previous_cache_and_removes_temporary_file(self):
        self.index.add_entry(mesh("High"))
        self.assertTrue(self.index.save_to_cache())
        cache = Path(self.temp.name) / "nif_texture_index.json"
        before = cache.read_bytes()
        self.index.add_entry(mesh("Low", "meshes/new.nif"))
        self.assertFalse(self.index.save_to_cache(lambda: True))
        self.assertEqual(cache.read_bytes(), before)
        self.assertEqual(list(Path(self.temp.name).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
