"""Run separately from the headless unit suite, which uses Qt signal stubs."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import time
from unittest.mock import patch

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / ".test-runtime"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QPushButton, QTreeWidgetItem

PACKAGE = "ump_widget_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "UMP")]
sys.modules[PACKAGE] = package
bridge = types.ModuleType(f"{PACKAGE}.preview_bridge")
bridge.can_preview_virtual_path = lambda path: path.endswith((".nif", ".dds"))
bridge.preview_asset_source = lambda *_args: True
bridge.preview_nif_entry = lambda *_args: True
sys.modules[bridge.__name__] = bridge

from ump_widget_tests.tabs_nif import NifTextureSearchTab
from ump_widget_tests.nif_core import NifTextureEntry, NifTextureIndex
from ump_widget_tests.nif_search import WinnerSnapshot, ResolvedProvider, ScoredMeshProvider, MeshResult, ResolutionSession
from ump_widget_tests.archive_core import AssetSource
from ump_widget_tests.nif_tree_filter import filter_terms

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
app.setFont(QFont("Segoe UI", 9))


class Organizer:
    def __init__(self, directory):
        self.directory = directory

    def basePath(self):
        return self.directory

    def modList(self):
        return self

    def displayName(self, name):
        return name

    def allMods(self):
        return ["Winning Mod"]

    def state(self, name):
        return 2

    def priority(self, name):
        return 10

    def findFileInfos(self, parent, predicate):
        metadata = types.SimpleNamespace(
            filePath="D:/mods/Winning Mod/meshes/vampire/item.nif", origins=["Winning Mod"], archive=""
        )
        return [metadata] if parent == "meshes/vampire" and predicate(metadata) else []


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.temp.name) / "settings.ini"), QSettings.Format.IniFormat)
        with patch(f"{PACKAGE}.tabs_nif.QSettings", return_value=settings):
            self.tab = NifTextureSearchTab(None, Organizer(self.temp.name), None)
        self.tab.resize(1450, 800)
        self.entry = NifTextureEntry(
            "Winning Mod", "meshes/vampire/item.nif",
            [f"textures/vampire/texture{number}.dds" for number in range(24)],
            container_path="D:/mods/Winning Mod/meshes/vampire/item.nif",
        )
        self.tab._index.add_entry(self.entry)
        self.snapshot = WinnerSnapshot(NifTextureIndex(Path(self.temp.name)))
        self.loose = AssetSource("Winning Mod", self.entry.textures[0], "loose", "D:/mods/Winning Mod/texture0.dds")
        self.archive = AssetSource("Base", self.entry.textures[0], "bsa", "D:/game/Data/Skyrim - Textures0.bsa",
                                   archive_name="Skyrim - Textures0.bsa", is_game=True)
        self.inactive = AssetSource("Inactive Pack", self.entry.textures[1], "loose", "D:/mods/Inactive Pack/texture1.dds")
        self.snapshot.textures = {
            "vampire/texture0.dds": [ResolvedProvider(self.loose, True, True, True, (0,)),
                                     ResolvedProvider(self.archive, False, True, True, (1,))],
            "vampire/texture1.dds": [ResolvedProvider(self.inactive, False, False, True, (2,))],
        }
        for path in self.entry.textures[2:]:
            self.snapshot.textures[self.snapshot.index.normalize_path(path)] = []
        self.version = ScoredMeshProvider(self.entry, 100, ResolvedProvider(
            AssetSource(self.entry.mod_name, self.entry.relative_path, "loose", self.entry.container_path),
            True, True, True, (0,),
        ))
        self.mesh_group = MeshResult(self.entry.relative_path, self.version, (self.version,), 100)

    def tearDown(self):
        self.tab._results_filter.timer.stop()
        self.tab._details_filter.timer.stop()
        self.tab._profile_refresh_timer.stop()
        self.tab._invalidate_search()
        for worker in self.tab._texture_workers + self.tab._search_workers:
            worker.wait(5000)
        app.processEvents()
        self.tab.close()
        self.tab.deleteLater()
        app.processEvents()
        self.temp.cleanup()

    def render(self, mode=False):
        self.tab._on_search_ready(self.tab._search_generation, {
            "snapshot": self.snapshot, "results": [self.mesh_group], "total": 1,
            "query": "item.dds", "nif_to_dds": mode,
        })
        return self.tab._results_tree.topLevelItem(0)

    def select_nif(self):
        item = self.render()
        self.tab._results_tree.setCurrentItem(item)
        self.tab._on_result_clicked(item, 0)
        return self.tab._details_tree.topLevelItem(5)

    def test_details_hierarchy_has_all_paths_and_providers(self):
        group = self.select_nif()
        self.assertEqual(self.tab._results_tree.headerItem().text(3), "Mod / Source")
        self.assertEqual([self.tab._details_tree.topLevelItem(i).text(0) for i in range(6)],
                         ["File", "Path", "Mod", "Source Type", "Texture Count", "Referenced Textures"])
        self.assertEqual(group.childCount(), 24)
        found = group.child(0)
        missing = group.child(1)
        self.assertEqual(found.text(0), "Found")
        self.assertEqual(found.childCount(), 2)
        self.assertIn("Winning", found.child(0).text(1))
        self.assertIn("Skyrim - Textures0.bsa", found.child(1).text(1))
        self.assertEqual(missing.text(0), "Missing")
        self.assertIn("Inactive", missing.child(0).text(1))

    def test_filter_and_phrase_matching_restore_expansion_and_fixed_properties(self):
        group = self.select_nif()
        group.setExpanded(False)
        self.tab._details_filter_input.setText("am re texture0")
        self.tab._details_filter.apply()
        self.assertTrue(group.isExpanded())
        self.assertFalse(group.child(0).isHidden())
        self.assertFalse(group.child(0).child(1).isHidden())
        self.assertTrue(group.child(1).isHidden())
        self.assertFalse(self.tab._details_tree.topLevelItem(0).isHidden())
        self.assertEqual(self.tab._details_label.text(), "1/24 referenced textures")
        self.tab._details_filter_input.clear()
        self.assertFalse(group.isExpanded())
        self.assertTrue(all(not group.child(i).isHidden() for i in range(24)))
        self.assertEqual(filter_terms('"winning mod" am re'), ["winning mod", "am", "re"])

    def test_provider_match_keeps_ancestors_and_filters_are_independent(self):
        group = self.select_nif()
        self.tab._details_filter_input.setText('"inactive pack"')
        self.tab._details_filter.apply()
        self.assertFalse(group.isHidden())
        self.assertFalse(group.child(1).isHidden())
        self.assertTrue(group.child(0).isHidden())
        self.tab._results_filter_input.setText("not-present")
        self.tab._results_filter.apply()
        self.assertIn("no filter matches", self.tab._results_label.text())
        self.assertFalse(group.child(1).isHidden())
        self.tab._results_filter_input.clear()
        self.assertFalse(self.tab._results_tree.topLevelItem(0).isHidden())

    def test_nif_mode_texture_children_and_provider_specific_actions(self):
        item = self.render(mode=True)
        self.assertEqual(item.childCount(), 1)
        self.assertEqual(item.child(0).childCount(), 24)
        child = item.child(0).child(0)
        self.tab._results_tree.setCurrentItem(child)
        self.tab._on_result_clicked(child, 0)
        texture = self.tab._details_tree.topLevelItem(4).child(0)
        self.assertIs(self.tab._action_source(self.tab._action_data), self.loose)
        provider = texture.child(1)
        self.tab._details_tree.setCurrentItem(provider)
        self.tab._on_detail_clicked(provider, 1)
        self.assertIs(self.tab._action_source(self.tab._action_data), self.archive)
        with patch(f"{PACKAGE}.tabs_nif.preview_asset_source", return_value=True) as preview:
            self.tab._preview_selected_result()
            self.assertIs(preview.call_args.args[1], self.archive)
        self.assertFalse(self.tab._goto_btn.isEnabled())

    def test_expand_collapse_buttons_and_filter_reapplied_to_selection(self):
        group = self.select_nif()
        buttons = self.tab.findChildren(QPushButton)
        expand = next(button for button in buttons if button.text() == "Expand All" and button.parent().title() == "Details")
        collapse = next(button for button in buttons if button.text() == "Collapse All" and button.parent().title() == "Details")
        expand.click()
        self.assertTrue(group.child(0).isExpanded())
        collapse.click()
        self.assertFalse(group.isExpanded())
        self.tab._details_filter_input.setText("texture0")
        nif = self.tab._results_tree.topLevelItem(0)
        self.tab._on_result_clicked(nif, 0)
        group = self.tab._details_tree.topLevelItem(5)
        self.assertFalse(group.child(0).isHidden())
        self.assertTrue(group.child(2).isHidden())

    def test_stale_search_results_are_discarded_and_truncation_reported(self):
        self.tab._on_search_ready(-1, {"bad": "stale payload"})
        self.assertEqual(self.tab._results_tree.topLevelItemCount(), 0)
        self.tab._on_search_ready(self.tab._search_generation, {
            "snapshot": self.snapshot, "results": [self.mesh_group], "total": 200,
            "query": "item", "nif_to_dds": True,
        })
        self.assertIn("first 1 of 200", self.tab._results_label.text())
        self.tab._on_priority_changed("Winning Mod", 1, 2)
        self.assertEqual(self.tab._results_tree.topLevelItemCount(), 0)

    def test_screenshot(self):
        self.select_nif()
        self.tab._details_tree.expandAll()
        self.tab.show()
        app.processEvents()
        self.assertTrue(self.tab.grab().save(str(ROOT / ".test-runtime" / "nif-tab-preview.png")))

    def test_close_parent_exact_child_selection_filters_and_clipboard(self):
        query = "textures/dlc01/architecture/hearse/coffin01.dds"
        alternative = NifTextureEntry("Comfy Coffins - AIO", self.entry.relative_path, [query],
                                      container_path="D:/mods/Comfy Coffins/meshes/vampire/item.nif")
        losing = ScoredMeshProvider(alternative, 100, ResolvedProvider(
            AssetSource(alternative.mod_name, alternative.relative_path, "loose", alternative.container_path),
            False, True, True, (1,),
        ))
        winning = ScoredMeshProvider(self.entry, 80, self.version.provider)
        self.mesh_group = MeshResult(self.entry.relative_path, winning, (winning, losing), 100)
        root = self.render()
        self.assertEqual([root.text(i) for i in range(3)], ["Close Match", "item.nif", "80"])
        child = root.child(0)
        self.assertEqual([child.text(i) for i in range(3)], ["Exact Match", "item.nif", "100"])
        self.tab._on_result_clicked(child, 0)
        self.assertEqual(self.tab._details_tree.topLevelItem(2).text(1), alternative.mod_name)
        self.assertEqual(self.tab._details_tree.topLevelItem(5).child(0).text(1), query)
        with patch(f"{PACKAGE}.tabs_nif.preview_nif_entry", return_value=True) as preview:
            self.tab._preview_selected_result()
            self.assertIs(preview.call_args.args[1], alternative)
        with patch.object(self.tab, "_goto_mod_in_view") as navigate:
            self.tab._goto_selected_mod()
            navigate.assert_called_once_with(alternative.mod_name)
        self.tab._copy_results()
        text = QApplication.clipboard().text()
        self.assertIn("[Close Match] [score: 80]", text)
        self.assertIn("[Exact Match] [score: 100]", text)
        self.assertIn("Comfy Coffins", text)
        root.setExpanded(False)
        self.tab._results_filter_input.setText('"Comfy Coffins"')
        self.tab._results_filter.apply()
        self.assertFalse(root.isHidden())
        self.assertFalse(child.isHidden())
        self.assertTrue(root.isExpanded())
        self.assertEqual(self.tab._results_label.text(), "1/1 mesh paths")
        self.tab._results_filter_input.clear()
        self.assertFalse(root.isExpanded())

    def test_unavailable_parent_does_not_redirect_actions_to_loser(self):
        version = ScoredMeshProvider(self.entry, 100, ResolvedProvider(
            self.version.provider.source, False, False, True, (2,),
        ))
        self.mesh_group = MeshResult(self.entry.relative_path, None, (version,), 100)
        root = self.render()
        self.assertEqual(root.text(3), "No active winner")
        self.assertEqual(root.text(2), "")
        self.tab._on_result_clicked(root, 0)
        self.assertIsNone(self.tab._action_source(self.tab._action_data))
        with patch(f"{PACKAGE}.tabs_nif.preview_nif_entry") as preview:
            self.tab._on_result_double_clicked(root, 0)
            preview.assert_not_called()
        self.tab._on_result_clicked(root.child(0), 0)
        self.assertEqual(self.tab._action_source(self.tab._action_data).owner, self.entry.mod_name)

    def test_details_resolution_is_lazy_stale_safe_and_query_cache_survives(self):
        self.snapshot.textures.clear()
        self.tab._resolution_session = ResolutionSession(self.tab._organizer, self.tab._index)
        root = self.render(mode=True)
        texture = root.child(0).child(0)
        self.assertEqual(texture.text(0), "Loading")
        session = self.tab._resolution_session
        self.tab._on_result_clicked(root, 0)
        deadline = time.monotonic() + 5
        while self.tab._texture_workers and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.002)
        app.processEvents()
        self.assertFalse(self.tab._texture_workers)
        self.assertEqual(root.child(0).child(0).text(0), "Missing")
        self.assertEqual(self.tab._details_tree.topLevelItem(5).child(0).text(0), "Missing")
        self.tab._on_texture_ready(-1, {"bogus.dds": ((), ())})
        self.assertNotIn("bogus.dds", self.tab._snapshot.textures)
        self.tab._invalidate_search()
        self.assertIs(self.tab._resolution_session, session)
        self.tab._on_priority_changed("Winning Mod", 1, 2)
        self.assertIsNone(self.tab._resolution_session)

    def test_real_qthread_search_publishes_and_releases_worker(self):
        self.tab._search_input.setText("item")
        self.tab._do_search()
        deadline = time.monotonic() + 5
        while self.tab._search_workers and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        app.processEvents()
        self.assertFalse(self.tab._search_workers)
        self.assertEqual(self.tab._results_tree.topLevelItemCount(), 1)
        self.assertEqual(self.tab._results_tree.topLevelItem(0).text(1), "item.nif")
        self.assertTrue(self.tab._search_btn.isEnabled())

    def test_exact_provider_preview_bypasses_virtual_winner_redirect(self):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.actual_preview_bridge", ROOT / "UMP" / "preview_bridge.py"
        )
        actual_bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(actual_bridge)
        plugin = types.SimpleNamespace(supportsArchives=lambda: True, genDataPreview=lambda *_args: self.tab)
        with patch.object(actual_bridge, "_try_organizer_preview", return_value=True) as redirect, \
             patch.object(actual_bridge, "_read_archive_source", return_value=b"dds"), \
             patch.object(actual_bridge, "_find_preview_plugin", return_value=plugin), \
             patch.object(actual_bridge, "_show_preview_dialog"):
            self.assertTrue(actual_bridge.preview_asset_source(self.tab, self.archive, self.tab._organizer, exact_source=True))
            redirect.assert_not_called()
        with patch.object(actual_bridge, "preview_asset_source", return_value=True) as preview:
            self.assertTrue(actual_bridge.preview_nif_entry(self.tab, self.entry, self.tab._organizer))
            self.assertTrue(preview.call_args.kwargs["exact_source"])

    def test_index_thread_retains_empty_and_unreadable_meshes_and_exits_safely(self):
        sources = [AssetSource("Winning Mod", f"meshes/{name}.nif", "loose", f"D:/mods/{name}.nif")
                   for name in ("empty", "corrupt")]

        class Catalog:
            errors = []

            def __init__(self, *_args, **_kwargs):
                pass

            def iter_index_assets(self, _cancelled):
                for source in sources:
                    yield types.SimpleNamespace(**source.__dict__, source=lambda source=source: source)

            def read_bytes(self, source):
                return b"Gamebryo File Format\n" if "empty" in source.virtual_path else b"corrupt"

            def close(self):
                time.sleep(0.015)

        with patch(f"{PACKAGE}.nif_core.build_index_scope", return_value={}), \
             patch(f"{PACKAGE}.nif_core.AssetCatalog", Catalog):
            self.tab._start_indexing(force_rebuild=True)
            deadline = time.monotonic() + 5
            while (self.tab._index_workers or self.tab._is_indexing) and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)
            app.processEvents()
        self.assertFalse(self.tab._index_workers)
        self.assertFalse(self.tab._is_indexing)
        self.assertEqual(self.tab._index.nif_count, 2)
        entries = {entry.relative_path: entry for entry in self.tab._index.entries()}
        self.assertEqual(entries["meshes/empty.nif"].textures, [])
        self.assertEqual(entries["meshes/corrupt.nif"].parse_error, "Invalid NIF header")


if __name__ == "__main__":
    unittest.main(verbosity=2)
