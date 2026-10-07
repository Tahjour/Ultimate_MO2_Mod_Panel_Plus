"""Synthetic-scale timings and Qt heartbeat coverage; never imports MO2 plugins."""

from dataclasses import dataclass
import json
import gc
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from qt_nif_widgets import app, PACKAGE, Organizer, NifTextureSearchTab, ROOT
from PyQt6.QtCore import QTimer, QSettings
from ump_widget_tests.archive_core import AssetSource
from ump_widget_tests.nif_core import NifIndexWorker, NifTextureIndex
from ump_widget_tests.nif_search import NifSearchWorker, ResolutionSession

NIFS = 203494
TEXTURES = 79096


@dataclass(frozen=True)
class Record:
    number: int
    texture: bool = False

    @property
    def owner(self):
        return "High" if self.texture or self.number % 2 else "Low"

    @property
    def virtual_path(self):
        if self.texture:
            return f"textures/bench/item{self.number:06}.dds"
        number = self.number // 2
        return f"meshes/bench/{number % 128:03}/item{number:06}.nif"

    @property
    def container_path(self):
        return f"D:/mods/{self.owner}/{self.virtual_path}"

    def source(self):
        return AssetSource(self.owner, self.virtual_path, "loose", self.container_path,
                           physical_path=self.container_path)


class Catalog:
    errors = []
    traversals = 0

    def __init__(self, *_args, **_kwargs):
        pass

    def iter_index_assets(self, cancelled):
        Catalog.traversals += 1
        for number in range(NIFS):
            if cancelled():
                return
            yield Record(number)
        for number in range(TEXTURES):
            if cancelled():
                return
            yield Record(number, True)

    def read_bytes(self, source):
        number = int(source.virtual_path.rsplit("item", 1)[-1][:-4]) % TEXTURES
        return f"Gamebryo File Format\ntextures/bench/item{number:06}.dds\x00".encode("ascii")

    def close(self):
        pass


class BenchOrganizer(Organizer):
    def __init__(self, directory):
        super().__init__(directory)
        self.calls = 0
        self.infos = {}
        for number in range(NIFS // 2):
            record = Record(2 * number + 1)
            parent = record.virtual_path.rpartition("/")[0]
            self.infos.setdefault(parent, []).append(SimpleNamespace(
                filePath=record.container_path, origins=["High", "Low"], archive="",
            ))

    def allMods(self):
        return ["Low", "High"]

    def priority(self, name):
        return 20 if name == "High" else 10

    def findFileInfos(self, parent, predicate):
        self.calls += 1
        return [info for info in self.infos.get(parent, []) if predicate(info)]


def wait(worker, ticks, timeout=120):
    started = time.perf_counter()
    deadline = started + timeout
    while worker.isRunning() and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert not worker.isRunning(), "Worker exceeded benchmark timeout"
    worker.wait()
    app.processEvents()
    return time.perf_counter() - started


def main():
    report = {}
    gc_starts, gc_times = {}, []
    def record_gc(phase, info):
        generation = info["generation"]
        if phase == "start":
            gc_starts[generation] = time.perf_counter()
        elif generation in gc_starts:
            gc_times.append((time.perf_counter() - gc_starts.pop(generation), generation))
    gc.callbacks.append(record_gc)
    ticks = [time.perf_counter()]
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start()
    with tempfile.TemporaryDirectory() as directory:
        organizer = BenchOrganizer(directory)
        settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
        with patch(f"{PACKAGE}.tabs_nif.QSettings", return_value=settings):
            tab = NifTextureSearchTab(None, organizer, None)
        seed = NifTextureIndex(Path(directory))
        worker = NifIndexWorker(organizer, seed, incremental=False)
        indexes, errors, phases = [], [], []
        worker.index_ready.connect(lambda index, cached: indexes.append(index))
        worker.error.connect(errors.append)
        worker.phase.connect(lambda phase: phases.append((phase, time.perf_counter())))
        with patch(f"{PACKAGE}.nif_core.AssetCatalog", Catalog), \
             patch(f"{PACKAGE}.nif_core.build_index_scope", return_value={"benchmark": True}):
            gc_times.clear()
            ticks[:] = [time.perf_counter()]
            worker.start()
            report["synthetic_cold_index_seconds"] = wait(worker, ticks)
        assert not errors, errors
        assert Catalog.traversals == 1
        index = indexes[0]
        assert (index.nif_count, index.texture_count) == (NIFS, TEXTURES)
        report["index_entries"] = index.nif_count
        report["index_gc_largest_ms"] = [(round(seconds * 1000, 2), generation)
                                         for seconds, generation in sorted(gc_times, reverse=True)[:3]]
        report["texture_paths"] = index.texture_count
        report["inventory_traversals"] = Catalog.traversals
        report["index_phase_seconds"] = {
            phases[i][0]: round(phases[i + 1][1] - phases[i][1], 4)
            for i in range(len(phases) - 1)
        }
        report["index_max_heartbeat_gap_ms"] = round(max(b - a for a, b in zip(ticks, ticks[1:])) * 1000, 2)
        gaps = sorted(((b - a, a, b) for a, b in zip(ticks, ticks[1:])), reverse=True)[:3]
        report["index_largest_gaps"] = [
            dict(milliseconds=round(gap * 1000, 2), phase=next(
                (phase for phase, timestamp in reversed(phases) if timestamp <= start), "startup"))
            for gap, start, end in gaps
        ]
        tab._index = index
        session = ResolutionSession(organizer, index)
        tab._resolution_session = session
        for name, query, nif in (
            ("cold_dds", "textures/bench/item000001.dds", False),
            ("warm_dds", "textures/bench/item000001.dds", False),
            ("cold_broad_dds", "item", False),
            ("warm_broad_dds", "item", False),
            ("warm_nif", "item000001.nif", True),
        ):
            tab._invalidate_search()
            ticks[:] = [time.perf_counter()]
            calls = organizer.calls
            results, errors = [], []
            search_worker = NifSearchWorker(organizer, index, query, nif, tab._search_generation, session)
            search_worker.ready.connect(lambda generation, payload: results.append(payload))
            search_worker.failed.connect(lambda generation, error: errors.append(error))
            search_worker.start()
            elapsed = wait(search_worker, ticks)
            assert not errors, errors
            payload = results[0]
            before_render = time.perf_counter()
            tab._clear_search_views()
            tab._search_btn.setEnabled(False)
            tab._on_search_ready(tab._search_generation, payload)
            while not tab._search_btn.isEnabled():
                app.processEvents()
                time.sleep(0.001)
            app.processEvents()
            rendering = time.perf_counter() - before_render
            assert tab._results_tree.topLevelItemCount() == len(payload["results"])
            ticks.append(time.perf_counter())
            report[name] = dict(
                total_worker_seconds=round(elapsed, 4),
                matching_seconds=round(payload["timings"]["matching"], 4),
                resolution_seconds=round(payload["timings"]["resolution"], 4),
                rendering_seconds=round(rendering, 4),
                vfs_calls=organizer.calls - calls,
                displayed_groups=len(payload["results"]),
                total_groups=payload["total"],
                max_heartbeat_gap_ms=round(max(b - a for a, b in zip(ticks, ticks[1:])) * 1000, 2),
            )
            if name.startswith("warm"):
                assert organizer.calls == calls, "Warm query repeated VFS resolution"
            if report[name]["max_heartbeat_gap_ms"] >= 150:
                print(json.dumps(report, indent=2))
                raise AssertionError("Search/rendering noticeably blocked Qt heartbeat")
            assert payload["snapshot"].textures == {}, "Search eagerly resolved texture providers"
        tab._profile_refresh_timer.stop()
        tab._results_filter.timer.stop()
        tab._details_filter.timer.stop()
        tab.close()
        tab.deleteLater()
        app.processEvents()
    timer.stop()
    gc.callbacks.remove(record_gc)
    output = ROOT / ".test-runtime" / "nif-search-benchmark.json"
    output.write_text(json.dumps(report, indent=2), encoding="ascii")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
