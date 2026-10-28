"""_continent_v2/publish_client.py: stamping export_collision.py's sidecar as the package's collision block.

The territory manifest carries the sidecar's block (collision.bin, gridAlignment tile-centres-v1, the height encoding
and servedGrid), and a sidecar is refused when it is stale (another snapshot), partial, another map's, or its
binaries are not the ones in the package. Chunk manifests keep the block's frame without its binaries, so
package_client.py finds no file a chunk names that the commit lacks.

The refusals run on a synthetic sidecar. The fixture publish exports test_export_collision's two-territory fixture
with the server's codec (ELORIA_SERVER_ROOT, as there) and builds the territory and chunk manifests with the
publisher's own functions; the server's package reader must accept the territory manifest it writes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
CHECKOUT = V2.parents[3]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CHECKOUT / "godot-client" / "tools"))
import publish_client as PC  # noqa: E402
import package_client  # noqa: E402

SERVER = os.environ.get("ELORIA_SERVER_ROOT")
SNAPSHOT = "a" * 64
SERVER_BLOCK = {"cells": [72, 72], "collisionOriginMetres": [-34.0, 34.0], "metresPerTile": 1.0, "origin": [34, 34]}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_identical_library_texture_alias_keeps_the_certified_hash(tmp_path):
    canonical = tmp_path / "library-a" / "leaf.png"
    alias = tmp_path / "library-b" / "leaf.png"
    canonical.parent.mkdir(); alias.parent.mkdir()
    canonical.write_bytes(b"certified image bytes")
    alias.write_bytes(canonical.read_bytes())
    snapshot = SimpleNamespace(source_sha256={"library-a/leaf.png": sha(canonical.read_bytes())})
    aliases = PC.bind_certified_texture_aliases(snapshot, tmp_path, [alias])
    assert snapshot.source_sha256["library-b/leaf.png"] == sha(alias.read_bytes())
    assert aliases == [{"path": "library-b/leaf.png", "certifiedPath": "library-a/leaf.png",
                        "sha256": sha(alias.read_bytes())}]
    assert PC.bind_certified_texture_aliases(snapshot, tmp_path, [alias]) == []


def test_an_alias_with_different_pixels_is_not_certified(tmp_path):
    canonical = tmp_path / "leaf.png"
    alias = tmp_path / "other-leaf.png"
    canonical.write_bytes(b"certified image")
    alias.write_bytes(b"uncertified image")
    snapshot = SimpleNamespace(source_sha256={"leaf.png": sha(canonical.read_bytes())})
    assert PC.bind_certified_texture_aliases(snapshot, tmp_path, [alias]) == []
    assert "other-leaf.png" not in snapshot.source_sha256


def test_a_changed_canonical_texture_cannot_certify_an_alias(tmp_path):
    canonical = tmp_path / "leaf.png"
    alias = tmp_path / "other-leaf.png"
    alias.write_bytes(b"certified image")
    canonical.write_bytes(b"changed after bake")
    snapshot = SimpleNamespace(source_sha256={"leaf.png": sha(alias.read_bytes())})
    with pytest.raises(ValueError, match="changed after the bake"):
        PC.bind_certified_texture_aliases(snapshot, tmp_path, [alias])


def addressed_model(tmp_path):
    image = tmp_path / (sha(b"model-pinned image") + ".jpg")
    image.write_bytes(b"model-pinned image")
    model = tmp_path / "source.gltf"
    model.write_text(json.dumps({"images": [{"uri": image.name}]}))
    binding = {"path": "source.gltf", "sha256": sha(model.read_bytes())}
    snapshot = SimpleNamespace(source_sha256={}, document={"objects": [{"bakedSource": binding}]})
    authoring = SimpleNamespace(baked_asset_path=lambda entry, snapshot: model)
    reader = SimpleNamespace(load=lambda path: (json.loads(path.read_text()), b""))
    return image, model, snapshot, authoring, reader


def test_texture_content_address_is_bound_by_the_original_model_hash(tmp_path):
    image, model, snapshot, authoring, reader = addressed_model(tmp_path)
    images, addresses = PC.source_texture_paths(snapshot, authoring, reader)
    record = PC.bind_certified_texture_aliases(snapshot, tmp_path, images, addresses)
    assert snapshot.source_sha256[image.name] == sha(image.read_bytes())
    assert record[0]["sourceModelSha256"] == sha(model.read_bytes())


def test_changed_image_cannot_pass_its_model_pinned_content_address(tmp_path):
    image, _, snapshot, authoring, reader = addressed_model(tmp_path)
    images, addresses = PC.source_texture_paths(snapshot, authoring, reader)
    image.write_bytes(b"changed pixels")
    with pytest.raises(ValueError, match="content address"):
        PC.bind_certified_texture_aliases(snapshot, tmp_path, images, addresses)


def test_a_changed_model_cannot_certify_a_new_texture_dependency(tmp_path):
    _, model, snapshot, authoring, reader = addressed_model(tmp_path)
    model.write_text('{"images": []}')
    with pytest.raises(ValueError, match="model changed after the bake"):
        PC.source_texture_paths(snapshot, authoring, reader)


def synthetic(tmp_path, **changes):
    """A package folder holding two binaries and a sidecar that records them."""
    package = tmp_path / "client"
    package.mkdir(parents=True, exist_ok=True)
    (package / PC.COLLISION_BIN).write_bytes(b"EWCG collision")
    (package / PC.SERVED_GRID).write_bytes(b"ESCG served")
    block = {"binary": PC.COLLISION_BIN, "format": "EWCG-v2", "width": 144, "height": 144, "cellMetres": 0.5,
             "serverStorageVersion": 1, "serverTileMin": [0, 0], "serverCells": [72, 72],
             "originMetres": [-34.0, 34.0], "heightEncoding": {"origin": 1.0, "step": .2, "range": [1, 255]},
             "gridAlignment": "tile-centres-v1", "walkableCells": 10, "sha256": sha(b"EWCG collision"),
             "sourceSnapshotSha256": SNAPSHOT,
             "exportStatistics": {"ownCells": 100}, "seamCollar": {"east": {"cells": 4}},
             "groupExport": {"maps": {"east": {"snapshotSha256": "e" * 64, "servedGridSha256": "f" * 64},
                                      "west": {"snapshotSha256": SNAPSHOT, "servedGridSha256": sha(b"ESCG served")}}},
             "servedGrid": {"binary": PC.SERVED_GRID, "format": "ESCG-v2", "unitMetres": .05, "climbMetres": 1.0,
                            "originMetres": -100.0, "openTiles": 2, "sha256": sha(b"ESCG served")}}
    sidecar = {"schema": PC.SIDECAR_SCHEMA, "region": "west", "partial": False, "collision": block}
    for key, value in changes.items():
        if key in block:
            block[key] = value
        else:
            sidecar[key] = value
    path = tmp_path / "west.collision.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    return path, package


def test_the_sidecar_schema_and_file_names_are_the_exporters():
    pytest.importorskip("scipy")
    import export_collision as X
    ours = (PC.COLLISION_BIN, PC.SERVED_GRID, PC.SIDECAR_SCHEMA)
    assert ours == (X.COLLISION_BIN, X.SERVED_GRID, X.SIDECAR_SCHEMA)


def test_a_sidecar_is_stamped_with_its_served_grid(tmp_path):
    path, package = synthetic(tmp_path)
    block, record = PC.collision_block(path, SNAPSHOT, "west", SERVER_BLOCK, package)
    assert block["gridAlignment"] == "tile-centres-v1" and block["binary"] == PC.COLLISION_BIN
    assert block["servedGrid"]["binary"] == PC.SERVED_GRID and block["servedGrid"]["format"] == "ESCG-v2"
    assert block["nodeNames"] == [] and block["note"] == PC.SERVED_COLLISION_NOTE
    assert record["collisionSha256"] == sha(b"EWCG collision") and record["servedGridSha256"] == sha(b"ESCG served")
    assert record["sourceSnapshotSha256"] == SNAPSHOT


@pytest.mark.parametrize("changes, words", [
    ({"sourceSnapshotSha256": "b" * 64}, "stale"),
    ({"region": "east"}, "not west"),
    ({"partial": True}, "partial"),
    ({"schema": "something-else"}, "schema"),
    ({"serverCells": [78, 78]}, "frame"),
    ({"gridAlignment": "half-cells"}, "tile-centres-v1"),
    ({"sha256": "c" * 64}, "another run"),
    ({"groupExport": {"maps": {"west": {"snapshotSha256": SNAPSHOT, "servedGridSha256": "d" * 64}}}},
     "groupExport"),
    ({"groupExport": None}, "groupExport"),
])
def test_a_sidecar_is_refused(tmp_path, changes, words):
    path, package = synthetic(tmp_path, **changes)
    with pytest.raises(PC.CollisionRefused, match=words):
        PC.collision_block(path, SNAPSHOT, "west", SERVER_BLOCK, package)


def test_missing_binaries_are_refused(tmp_path):
    path, package = synthetic(tmp_path)
    (package / PC.SERVED_GRID).unlink()
    with pytest.raises(PC.CollisionRefused, match="missing"):
        PC.collision_block(path, SNAPSHOT, "west", SERVER_BLOCK, package)


def test_without_a_sidecar_a_package_stays_a_preview_unless_it_holds_exported_binaries(tmp_path):
    block, record = PC.collision_block(None, SNAPSHOT, "west", SERVER_BLOCK, tmp_path / "empty")
    assert record is None and block == PC.PREVIEW_COLLISION and "servedGrid" not in block
    _path, package = synthetic(tmp_path)
    with pytest.raises(PC.CollisionRefused, match="--collision"):
        PC.collision_block(None, SNAPSHOT, "west", SERVER_BLOCK, package)
    assert PC.known_limitations("west", None)[0].startswith("no server map")
    assert not any("no server map" in line for line in PC.known_limitations("west", {"sidecarSha256": "x"}))


def chunk_file_references(manifest, base):
    """The files package_client.py follows from a world.json: every file-like string (MANIFEST_SKIPPED_KEYS
    skipped), resolved against the manifest's folder."""
    out = []
    for key, value in package_client.json_strings(manifest, package_client.MANIFEST_SKIPPED_KEYS):
        if package_client.FILE_LIKE.match(value) and not value.startswith(("res://", "user://", "/")):
            out.append((key, str(PurePosixPath(base) / value)))
    return out


def test_chunk_manifests_keep_the_frame_but_name_no_binary(tmp_path):
    path, package = synthetic(tmp_path)
    block, _record = PC.collision_block(path, SNAPSHOT, "west", SERVER_BLOCK, package)
    manifest = {"asset": {"id": "west", "glb": "world.glb"}, "collision": block, "externalResources": {},
                "streamingChunks": {"chunks": []}, "landmarks": [], "lighting": {"markers": []}}
    stats = {"externalResources": {}, "glbBytes": 1}
    chunk = PC.chunk_manifest(manifest, "west", "03_04", stats, {"min": [0, 0, 0], "max": [1, 1, 1]})
    assert "binary" not in chunk["collision"] and "servedGrid" not in chunk["collision"]
    assert "sha256" not in chunk["collision"]
    assert chunk["collision"]["gridAlignment"] == "tile-centres-v1"
    assert chunk["collision"]["originMetres"] == block["originMetres"]
    # an allow-list: what a neighbour-only re-export changes (statistics, collar, provenance, the group record and
    # the own-ground height scale) stays in the territory manifest
    assert set(chunk["collision"]) <= set(PC.CHUNK_COLLISION_KEYS)
    for key in ("exportStatistics", "seamCollar", "groupExport", "sourceSnapshotSha256", "walkableCells",
                "heightEncoding"):
        assert key in block and key not in chunk["collision"], key
    names = [target for _key, target in chunk_file_references(chunk, "chunks/03_04")]
    assert names == ["chunks/03_04/world.glb"]
    # the territory manifest names both binaries, which package_client follows and the commit must hold
    territory = [target for _key, target in chunk_file_references(manifest, ".")]
    assert {"collision.bin", "served-grid.escg.gz"} <= set(territory)
    # a preview's placeholder block passes through a chunk unchanged
    preview = PC.chunk_manifest(dict(manifest, collision=copy.deepcopy(PC.PREVIEW_COLLISION)), "west", "03_04",
                                stats, {"min": [0, 0, 0], "max": [1, 1, 1]})
    assert preview["collision"] == PC.PREVIEW_COLLISION


@pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout with eloria/served_grid.py")
def test_a_fixture_publish_carries_the_served_grid_and_the_server_accepts_it(tmp_path):
    import export_collision as X
    import test_export_collision as fixture
    codec = X.server_codec(SERVER)
    packages = tmp_path / "packages"
    _report, sidecars = X.run(fixture.fixture_territories(), [("east", "west")], codec, tmp_path / "work",
                              packages, log=lambda *_: None)
    for region, sidecar in sidecars.items():
        package = packages / region / "client"
        snapshot = sidecar["collision"]["sourceSnapshotSha256"]
        frame = sidecar["frame"]
        server_block = {"cells": frame["cells"], "origin": frame["origin"],
                        "collisionOriginMetres": [-float(frame["origin"][0]), float(frame["origin"][1])]}
        block, record = PC.collision_block(tmp_path / "work" / f"{region}.collision.json", snapshot, region,
                                           server_block, package)
        manifest = {"asset": {"id": region, "glb": "world.glb"}, "collision": block,
                    "knownLimitations": PC.known_limitations(region, record), "externalResources": {},
                    "streamingChunks": {"chunks": []}}
        (package / "world.json").write_text(json.dumps(manifest), encoding="utf-8")
        blob, grid, spec = codec.sources.read_served_package(package / X.COLLISION_BIN, fixture.CELLS)
        assert spec == block["servedGrid"] and sha(blob) == record["servedGridSha256"]
        chunk = PC.chunk_manifest(manifest, region, "00_00", {"externalResources": {}, "glbBytes": 1},
                                  {"min": [0, 0, 0], "max": [1, 1, 1]})
        assert all(not target.endswith((".bin", ".gz")) for _k, target in chunk_file_references(chunk, "chunks/00_00"))
        # a stale stamp: the same sidecar against another snapshot
        with pytest.raises(PC.CollisionRefused, match="stale"):
            PC.collision_block(tmp_path / "work" / f"{region}.collision.json", "0" * 64, region, server_block,
                               package)


def picture_package(tmp_path):
    """A package with two chunks and a map picture drawn from them (render_minimap.py's block)."""
    out = tmp_path / "client"
    chunks = []
    for name in ("00_00", "00_01"):
        (out / "chunks" / name).mkdir(parents=True)
        (out / "chunks" / name / "world.glb").write_bytes(b"glTF " + name.encode())
        (out / "chunks" / name / "world.json").write_text(json.dumps({"asset": {"glb": "world.glb"}}),
                                                         encoding="utf-8")
        chunks.append({"id": name, "manifest": f"chunks/{name}/world.json"})
    (out / PC.MINIMAP).write_bytes(b"RIFF picture")
    block = {"image": PC.MINIMAP, "imageSha256": sha(b"RIFF picture"),
             "cartographyRender": {"chunksSha256": PC.chunks_digest(out, chunks)}}
    (out / "world.json").write_text(json.dumps({"minimap": block, "streamingChunks": {"chunks": chunks}}),
                                    encoding="utf-8")
    return out, chunks, block


def test_a_republish_keeps_the_map_picture_only_while_it_shows_the_same_chunks(tmp_path):
    out, chunks, block = picture_package(tmp_path)
    assert PC.kept_minimap(out, chunks) == block
    # the digest is over every chunk, in the manifest's order, by id and GLB content
    assert PC.chunks_digest(out, chunks) != PC.chunks_digest(out, chunks[::-1])
    (out / "chunks" / "00_01" / "world.glb").write_bytes(b"glTF regraded")
    assert PC.kept_minimap(out, chunks) is None
    out, chunks, block = picture_package(tmp_path / "again")
    assert PC.kept_minimap(out, chunks[:1]) is None
    (out / PC.MINIMAP).write_bytes(b"RIFF another picture")
    assert PC.kept_minimap(out, chunks) is None
    # a first publish has no picture to keep
    assert PC.kept_minimap(tmp_path / "nowhere", chunks) is None


def test_every_npc_marker_with_a_map_category_keeps_its_shop_dot_and_an_unknown_one_is_refused():
    """The package's serviceMarkers (map_categories.service_markers): every category the client draws, in marker order;
    an unknown category stops the publish rather than dropping the shop's dot."""
    import map_categories as MC
    def marker(ident, category=None, **extra):
        row = {"id": ident, "name": ident.title(), "position": [1.0, 2.0, 3.0], "serverTile": [4, 5], **extra}
        if category is not None:
            row["mapCategory"] = category
        return row
    markers = [marker("bettany", "tavern", mapLabel="Bettany Orl's Tavern"), marker("hemmen"),
               marker("lio", "flower_shop"), marker("ysolde", "magic_shop"), marker("garrow", "blacksmith"),
               marker("rowan", "general_store"), marker("ilyon", "")]
    rows = MC.service_markers(markers)
    assert [(row["id"], row["category"]) for row in rows] == [
        ("bettany", "tavern"), ("lio", "flower_shop"), ("ysolde", "magic_shop"), ("garrow", "blacksmith"),
        ("rowan", "general_store")]
    assert rows[0] == {"id": "bettany", "name": "Bettany", "label": "Bettany Orl's Tavern", "category": "tavern",
                       "position": [1.0, 2.0, 3.0], "serverTile": [4, 5]}
    assert rows[1]["label"] == "Lio"
    with pytest.raises(MC.CategoryError, match="tessa: map category 'books'"):
        MC.service_markers([*markers, marker("tessa", "books")])
    # The publisher builds its rows through the table, and keeps no list of its own.
    source = (V2 / "publish_client.py").read_text(encoding="utf-8")
    assert "MC.service_markers(" in source and '("general_store", "tavern")' not in source
