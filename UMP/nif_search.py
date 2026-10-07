"""Current-profile asset resolution and searches, independent of the widgets."""

from dataclasses import dataclass, field
import ntpath
from collections import defaultdict
from threading import Lock
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from .archive_core import AssetSource, normalize_virtual_path
from .nif_core import NifTextureIndex, NifTextureEntry


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
    texture_warnings: dict = field(default_factory=dict)

    def providers(self, texture_path):
        return self.textures.get(self.index.normalize_path(texture_path), [])

    def texture_ready(self, texture_path):
        return self.index.normalize_path(texture_path) in self.textures


def match_label(score):
    if score is None:
        return "Unreadable"
    if score == 100:
        return "Exact Match"
    if score >= 70:
        return "Close Match"
    if score > 0:
        return "Partial Match"
    return "No Match"


@dataclass(frozen=True)
class ScoredMeshProvider:
    entry: NifTextureEntry
    score: Optional[int]
    provider: ResolvedProvider


@dataclass(frozen=True)
class MeshResult:
    virtual_path: str
    winner: Optional[ScoredMeshProvider]
    versions: tuple[ScoredMeshProvider, ...]
    best_score: int
    winner_origin: str = ""
    warnings: tuple = ()
    winner_source: Optional[AssetSource] = None


@dataclass(frozen=True)
class _FileMetadata:
    filePath: str
    origins: tuple[str, ...]
    archive: str


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
        self.directory_infos = {}
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
            if parent not in self.directory_infos:
                infos = self.organizer.findFileInfos(parent, lambda info: True)
                inventory = {}
                for info in infos:
                    name = ntpath.basename(str(info.filePath)).casefold()
                    inventory[name] = _FileMetadata(str(info.filePath), tuple(info.origins), str(info.archive))
                    if info.archive:
                        archive = ntpath.basename(str(info.archive)).casefold()
                        self.loaded_archives.setdefault(archive, -1)
                self.directory_infos[parent] = inventory
                time.sleep(0)
            for name in names:
                info = self.directory_infos[parent].get(name)
                if info is not None:
                    path = f"{parent}/{name}" if parent else name
                    result[path] = info
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


class ResolutionSession:
    """Worker-owned caches; queries share them, profile/index revisions do not."""

    def __init__(self, organizer, index):
        self.organizer = organizer
        self.index = index
        self.lock = Lock()
        self.resolver = None
        self.meshes = {}
        self.textures = {}

    def acquire(self, cancelled):
        while not cancelled():
            if self.lock.acquire(timeout=0.05):
                try:
                    if self.resolver is None:
                        resolver = ProfileResolver(self.organizer, cancelled)
                        if cancelled():
                            self.lock.release()
                            return False
                        self.resolver = resolver
                    self.resolver.cancelled = cancelled
                    return True
                except Exception:
                    self.lock.release()
                    raise
        return False

    def mesh_providers(self, paths, cancelled):
        missing = [path for path in paths if path not in self.meshes]
        infos = self.resolver.file_infos(missing)
        for path in missing:
            if cancelled():
                break
            entries = self.index.mesh_versions(path)
            sources = [entry_source(entry) for entry in entries]
            info = infos.get(path)
            providers = self.resolver.resolve(sources, info)
            by_source = dict(zip(sources, entries))
            versions = tuple((by_source[p.source], p) for p in providers)
            origin = str(info.origins[0]) if info and info.origins else "[Unknown origin]" if info else ""
            identity = None
            if info:
                archive = str(info.archive)
                container = self.resolver._archive_path(archive) if archive else str(info.filePath)
                identity = AssetSource(origin, path, "bsa" if archive else "loose", container or archive,
                                       physical_path="" if archive else str(info.filePath),
                                       archive_name=ntpath.basename(archive),
                                       is_game=origin not in self.resolver.states)
            self.meshes[path] = (versions, origin, identity)

    def texture_providers(self, paths, cancelled):
        normalized = {self.index.normalize_path(path) for path in paths}
        missing = normalized - self.textures.keys()
        infos = self.resolver.file_infos(f"textures/{path}" for path in missing)
        for path in missing:
            if cancelled():
                break
            info = infos.get(f"textures/{path}")
            providers = self.resolver.resolve(self.index.find_texture_providers(path), info)
            warnings = ()
            if info and not any(p.winning for p in providers):
                warnings = (f"Unindexed or unresolved winning texture: textures/{path}",)
            self.textures[path] = (tuple(providers), warnings)
        return {path: self.textures[path] for path in normalized if path in self.textures}


class NifSearchWorker(QThread):
    ready = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, organizer, index, query, nif_to_dds, generation, session=None):
        super().__init__()
        self.organizer = organizer
        self.index = index
        self.query = query
        self.nif_to_dds = nif_to_dds
        self.generation = generation
        self.cancelled = False
        self.session = session or ResolutionSession(organizer, index)

    def cancel(self):
        self.cancelled = True

    def run(self):
        acquired = False
        try:
            started = time.perf_counter()
            scores, best = self.index.matching_groups(self.query, self.nif_to_dds, lambda: self.cancelled)
            limit = 100 if self.nif_to_dds else 500
            # Stable passes avoid allocating a sorting tuple for every indexed mesh.
            paths = sorted(best)
            paths.sort(key=best.__getitem__, reverse=True)
            paths = paths[:limit]
            matched_at = time.perf_counter()
            acquired = self.session.acquire(lambda: self.cancelled)
            if not acquired or self.cancelled:
                return
            self.session.mesh_providers(paths, lambda: self.cancelled)
            results = []
            snapshot = WinnerSnapshot(self.index)
            for path in paths:
                if self.cancelled:
                    return
                versions, origin, identity = self.session.meshes[path]
                scored = tuple(ScoredMeshProvider(entry, None if entry.parse_error else scores.get(entry.key, 0), provider)
                               for entry, provider in versions)
                winner = next((version for version in scored if version.provider.winning), None)
                warnings = []
                if origin and winner is None:
                    warnings.append(f"Unindexed or unresolved winning mesh: {path} ({origin})")
                if winner and winner.entry.parse_error:
                    warnings.append(f"Unreadable winning mesh: {path}: {winner.entry.parse_error}")
                results.append(MeshResult(path, winner, scored, best[path], origin, tuple(warnings), identity))
                snapshot.warnings.extend(warnings)
            # Already resolved Details data can be reused without additional MO2 calls.
            for group in results:
                for version in group.versions:
                    for path in version.entry.textures:
                        normalized = self.index.normalize_path(path)
                        if normalized in self.session.textures:
                            snapshot.textures[normalized] = self.session.textures[normalized][0]
                            snapshot.texture_warnings[normalized] = self.session.textures[normalized][1]
            if not self.cancelled:
                self.ready.emit(self.generation, {
                    "snapshot": snapshot, "results": results, "total": len(best),
                    "query": self.query, "nif_to_dds": self.nif_to_dds,
                    "counts": {label: sum(match_label(score) == label for score in best.values())
                               for label in ("Exact Match", "Close Match", "Partial Match")},
                    "timings": {"matching": matched_at - started,
                                "resolution": time.perf_counter() - matched_at},
                })
        except Exception as exc:
            if not self.cancelled:
                self.failed.emit(self.generation, str(exc))
        finally:
            if acquired:
                self.session.lock.release()


class TextureResolutionWorker(QThread):
    ready = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, session, paths, generation):
        super().__init__()
        self.session, self.paths, self.generation = session, paths, generation
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        acquired = False
        try:
            acquired = self.session.acquire(lambda: self.cancelled)
            if acquired and not self.cancelled:
                providers = self.session.texture_providers(self.paths, lambda: self.cancelled)
                if not self.cancelled:
                    self.ready.emit(self.generation, providers)
        except Exception as exc:
            if not self.cancelled:
                self.failed.emit(self.generation, str(exc))
        finally:
            if acquired:
                self.session.lock.release()
