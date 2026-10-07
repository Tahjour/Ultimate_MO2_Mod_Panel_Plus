"""Extract a real Skyrim NIF and verify archive-only DDS providers without MO2 UI."""

from pathlib import Path
import os
import tempfile
from types import SimpleNamespace

from test_nif_core import archive_core, nif_core
from test_nif_search import FakeOrganizer, search


def main():
    mesh_path = Path(os.environ["UMP_TEST_SKYRIM_MESHES_BSA"])
    lz4_path = Path(os.environ["MO2_LZ4_PATH"])
    mesh_archive = archive_core.BsaArchive(mesh_path, lz4_path)
    texture_archives = []
    try:
        candidates = [member for member in mesh_archive.members if "vampirecoffin" in member.virtual_path]
        if not candidates:
            candidates = [member for member in mesh_archive.members if member.virtual_path.endswith(".nif")][:200]
        for member in candidates:
            textures = nif_core.LightweightNifParser().parse_bytes(mesh_archive.extract(member))
            if textures:
                break
        assert textures, "No referenced DDSs found in candidate Skyrim NIFs"
        with tempfile.TemporaryDirectory() as directory:
            index = nif_core.NifTextureIndex(Path(directory))
            entry = nif_core.NifTextureEntry(
                "[Game Data]", member.virtual_path, textures, source_kind="bsa",
                container_path=str(mesh_path), is_game=True,
            )
            index.add_entry(entry)
            organizer = FakeOrganizer({member.virtual_path: SimpleNamespace(
                filePath=str(mesh_path.parent / member.virtual_path), archive=mesh_path.name, origins=["data"]
            )})
            organizer.archives[mesh_path.name.casefold()] = str(mesh_path)
            referenced = set(index.referenced_texture_paths())
            for path in sorted(mesh_path.parent.glob("Skyrim - Textures*.bsa")):
                archive = archive_core.BsaArchive(path, lz4_path)
                texture_archives.append(archive)
                organizer.archives[path.name.casefold()] = str(path)
                for texture_member in archive.members:
                    texture_path = texture_member.virtual_path
                    if index.normalize_path(texture_path) not in referenced:
                        continue
                    index.add_texture_provider(texture_path, archive_core.AssetSource(
                        "[Game Data]", texture_path, "bsa", str(path), archive_name=path.name, is_game=True
                    ))
                    organizer.infos[texture_path] = SimpleNamespace(
                        filePath=str(path.parent / texture_path), archive=path.name, origins=["data"]
                    )
            snapshot = search.ProfileResolver(organizer).snapshot(index)
            found = [path for path in textures if any(p.winning for p in snapshot.providers(path))]
            assert found, "No real archive-backed DDS providers resolved"
            assert snapshot.index.find_nifs_by_texture(found[0])[0][0].is_game
            print(f"Real BSA search passed: {member.virtual_path}; {len(found)}/{len(textures)} DDS references resolved")
    finally:
        mesh_archive.close()
        for archive in texture_archives:
            archive.close()


if __name__ == "__main__":
    main()
