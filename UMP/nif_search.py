"""Current-profile asset resolution and searches, independent of the widgets."""

from dataclasses import dataclass, field
import ntpath
from collections import defaultdict

from PyQt6.QtCore import QThread, pyqtSignal

from .archive_core import AssetSource, normalize_virtual_path
from .nif_core import NifTextureIndex


def disk_key(path):
    return ntpath.normcase(ntpath.normpath(str(path))) if path else ""


def entry_source(entry):
    return AssetSource(
        entry.mod_name, normalize_virtual_path(entry.relative_path), entry.source_kind,
        entry.container_path,
        physical_path=entry.container_path if entry.source_kind == "loose" else "",
        archive_name=ntpath.basename(entry.container_path) if entry.source_kind == "bsa" else "",
        is_game=entry.is_game, mtime=entry.file_mtime,
    )


@dataclass(frozen=True)
class ResolvedProvider:
    source: AssetSource
    winning: bool
    active: bool
    loaded: bool
    precedence: tuple

    @property
    def label(self):
        kind = self.source.archive_name or ntpath.basename(self.source.container_path)
        kind = kind if self.source.source_kind == "bsa" else "Loose"
        status = "Winning" if self.winning else (
            "Inactive" if not self.active else "Unloaded" if not self.loaded else "Overridden"
        )
        return f"{self.source.owner} [{kind}] ({status})"


@dataclass
class WinnerSnapshot:
    index: NifTextureIndex
    textures: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def providers(self, texture_path):
        return self.textures.get(self.index.normalize_path(texture_path), [])


class ProfileResolver:
    """Trust MO2's winning origin/container, never a guessed mod-priority winner."""

    def __init__(self, organizer, cancelled=lambda: False):
        self.organizer = organizer
        self.cancelled = cancelled
        self.mod_list = organizer.modList()
        try:
            import mobase
            active_flag = int(mobase.ModState.ACTIVE)
        except ImportError:
            active_flag = 2
        self.states = {}
        for name in self.mod_list.allMods():
            if self.cancelled():
                break
            self.states[name] = (bool(int(self.mod_list.state(name)) & active_flag),
                                 int(self.mod_list.priority(name)))
        self.archive_paths = {}
        self.loaded_archives = {}
        try:
            import mobase
            feature = organizer.gameFeatures().gameFeature(mobase.DataArchives)
            for rank, name in enumerate(feature.archives(organizer.profile())):
                self.loaded_archives[ntpath.basename(str(name)).casefold()] = rank
        except (AttributeError, ImportError, TypeError):
            pass

    def file_infos(self, paths):
        """One VFS call per containing directory; findFileInfos is not recursive."""
        directories = defaultdict(set)
        for path in paths:
            path = normalize_virtual_path(path)
            parent, _, name = path.rpartition("/")
            directories[parent].add(name)
        result = {}
        for parent, names in directories.items():
            if self.cancelled():
                return result
            infos = self.organizer.findFileInfos(
                parent, lambda info: ntpath.basename(str(info.filePath)).casefold() in names
            )
            for info in infos:
                name = ntpath.basename(str(info.filePath)).casefold()
                path = f"{parent}/{name}" if parent else name
                result[path] = info
                if info.archive:
                    archive = ntpath.basename(str(info.archive)).casefold()
                    self.loaded_archives.setdefault(archive, -1)
        return result

    def _archive_path(self, archive):
        key = ntpath.basename(archive).casefold()
        if key not in self.archive_paths:
            self.archive_paths[key] = disk_key(self.organizer.resolvePath(archive))
        return self.archive_paths[key]

    def resolve(self, sources, info):
        origins = list(info.origins) if info else []
        archive = ntpath.basename(str(info.archive)).casefold() if info else ""
        candidates = []
        for source in sources:
            if not info or not origins:
                break
            if source.source_kind == "loose":
                matches = not archive and disk_key(source.physical_path or source.container_path) == disk_key(info.filePath)
            else:
                matches = bool(archive) and ntpath.basename(source.container_path).casefold() == archive
                if matches:
                    physical = self._archive_path(str(info.archive))
                    matches = (disk_key(source.container_path) == physical if physical else
                               source.owner == origins[0])
            if matches:
                candidates.append(source)

        preferred = [source for source in candidates if source.owner == origins[0]] if origins else []
        candidates = preferred or candidates
        winner = candidates[0] if len(candidates) == 1 else None

        providers = []
        for source in sources:
            active, priority = self.states.get(source.owner, (source.is_game or source.owner in origins, -1))
            winning = source is winner
            active = active or winning
            name = ntpath.basename(source.container_path).casefold()
            loaded = source.source_kind == "loose" or (
                active and name in self.loaded_archives and (source.owner in origins or source.is_game)
                and (not self._archive_path(name) or disk_key(source.container_path) == self._archive_path(name))
            )
            loaded = loaded or winning
            origin_rank = origins.index(source.owner) if source.owner in origins else len(origins)
            if winning:
                precedence = (0,)
            elif active and loaded:
                precedence = (1, source.source_kind == "bsa", origin_rank,
                              -self.loaded_archives.get(name, -1), -priority, disk_key(source.container_path))
            else:
                precedence = (2, -priority, not active, disk_key(source.container_path))
            providers.append(ResolvedProvider(source, winning, active, loaded, precedence))
        return sorted(providers, key=lambda provider: provider.precedence)

    def snapshot(self, index):
        by_path = defaultdict(list)
        for entry in index.entries():
            by_path[normalize_virtual_path(entry.relative_path)].append(entry)
        mesh_infos = self.file_infos(by_path)
        winners = NifTextureIndex(index.cache_dir)
        snapshot = WinnerSnapshot(winners)
        for path, entries in by_path.items():
            if self.cancelled():
                return snapshot
            info = mesh_infos.get(path)
            sources = [entry_source(entry) for entry in entries]
            providers = self.resolve(sources, info)
            selected = next((provider.source for provider in providers if provider.winning), None)
            if selected is None:
                if info:
                    snapshot.warnings.append(f"Unindexed or unresolved winning mesh: {path}")
                continue
            entry = entries[sources.index(selected)]
            winners.add_entry(entry)
            if entry.parse_error:
                snapshot.warnings.append(f"Unreadable winning mesh: {path}: {entry.parse_error}")

        # Include original reference inventories so missing/unindexed winning DDSs
        # cannot be mistaken for an installed losing provider.
        paths = index.referenced_texture_paths()
        texture_infos = self.file_infos(f"textures/{path}" for path in paths)
        for path in paths:
            if self.cancelled():
                return snapshot
            sources = index.find_texture_providers(path)
            info = texture_infos.get(f"textures/{path}")
            providers = self.resolve(sources, info)
            snapshot.textures[path] = providers
            if info and not any(provider.winning for provider in providers):
                snapshot.warnings.append(f"Unindexed or unresolved winning texture: textures/{path}")
        winners.mark_build_complete()
        return snapshot


class NifSearchWorker(QThread):
    ready = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, organizer, index, query, nif_to_dds, generation):
        super().__init__()
        self.organizer = organizer
        self.index = index
        self.query = query
        self.nif_to_dds = nif_to_dds
        self.generation = generation
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        try:
            resolver = ProfileResolver(self.organizer, lambda: self.cancelled)
            snapshot = resolver.snapshot(self.index)
            if self.cancelled:
                return
            if self.nif_to_dds:
                results = snapshot.index.find_textures_by_nif(self.query, limit=None)
                limit = 100
            else:
                results = snapshot.index.find_nifs_by_texture(self.query, limit=None)
                limit = 500
            results.sort(key=lambda item: (-item[1], normalize_virtual_path(item[0].relative_path)))
            if not self.cancelled:
                self.ready.emit(self.generation, {
                    "snapshot": snapshot, "results": results[:limit], "total": len(results),
                    "query": self.query, "nif_to_dds": self.nif_to_dds,
                })
        except Exception as exc:
            if not self.cancelled:
                self.failed.emit(self.generation, str(exc))
