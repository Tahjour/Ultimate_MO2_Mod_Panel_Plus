import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class FollowupStaticTests(unittest.TestCase):
    def test_active_paths_avoid_deprecated_organizer_get_mod(self) -> None:
        active_paths = [
            "UMP/archive_core.py",
            "UMP/esp_search_tab.py",
            "UMP/plugin.py",
            "UMP/tabs.py",
            "UMP/tabs_files.py",
            "UMP/tabs_mods_plugins.py",
            "UMP/tabs_nif.py",
            "ModInfoTab/__init__.py",
        ]
        deprecated = re.compile(r"(?:self\._organizer|organizer)\.getMod\(")
        for relative_path in active_paths:
            with self.subTest(path=relative_path):
                self.assertIsNone(deprecated.search(_read(relative_path)))

    def test_nif_details_use_cached_providers_and_truthful_summary(self) -> None:
        source = _read("UMP/tabs_nif.py")
        self.assertIn("def _show_dds_search_summary", source)
        self.assertNotIn("def _check_texture_exists", source)
        self.assertNotIn("AssetCatalog", source)
        self.assertIn('"Texture Count"', source)
        self.assertIn('"--- Texture Paths ---"', source)
        self.assertIn("find_texture_providers", source)

    def test_worker_owns_scope_and_provider_catalog_work(self) -> None:
        tab_source = _read("UMP/tabs_nif.py")
        worker_source = _read("UMP/nif_core.py")
        self.assertNotIn("build_index_scope", tab_source)
        self.assertIn("scope = build_index_scope(", worker_source)
        self.assertIn("Mapping texture providers...", worker_source)
        self.assertIn("index_ready.emit(working_index", worker_source)

    def test_f1_reveals_ump_and_callbacks_use_new_payload_shape(self) -> None:
        plugin_source = _read("UMP/plugin.py")
        autoscroller_source = _read("UMP/autoscroller.py")
        self.assertIn("Qt.Key.Key_F1", plugin_source)
        self.assertIn("activated.connect(self._show_search)", plugin_source)
        self.assertNotIn("Qt.Key.Key_Tab", plugin_source)
        self.assertIn("self._on_mod_state_changed", autoscroller_source)
        self.assertIn("self._on_plugin_state_changed", autoscroller_source)
        self.assertNotIn("lambda *_:", autoscroller_source)

    def test_dds_preview_external_handoff_bridge(self) -> None:
        plugin_source = _read("UMP/plugin.py")
        dock_source = _read("UMP/dock_widget.py")
        tab_source = _read("UMP/tabs_nif.py")

        self.assertIn('setattr(app, "ump_find_nif_references"', plugin_source)
        self.assertIn("def find_nif_references(self, texture_path: str) -> bool:", plugin_source)
        self.assertIn("from .tabs_nif import NifTextureSearchTab", dock_source)
        self.assertIn("self.tab_widget.setCurrentIndex(index)", dock_source)
        self.assertIn("_pending_external_texture_query", tab_source)
        self.assertIn("self._dds_to_nif_radio.setChecked(True)", tab_source)
        self.assertIn("QTimer.singleShot(0, self._run_pending_external_search)", tab_source)

    def test_file_and_nif_results_expose_preview_actions(self) -> None:
        file_source = _read("UMP/tabs_files.py")
        nif_source = _read("UMP/tabs_nif.py")
        bridge_source = _read("UMP/preview_bridge.py")

        self.assertIn('QPushButton("Preview"', file_source)
        self.assertIn('QPushButton("Preview"', nif_source)
        self.assertIn("itemDoubleClicked.connect(self._on_item_double_clicked)", file_source)
        self.assertIn("itemDoubleClicked.connect(self._on_result_double_clicked)", nif_source)
        self.assertIn("preview_asset_source", file_source)
        self.assertIn("preview_nif_entry", nif_source)
        self.assertIn("def preview_asset_source", bridge_source)
        self.assertIn("genFilePreview", bridge_source)
        self.assertIn("genDataPreview", bridge_source)


if __name__ == "__main__":
    unittest.main()
