"""Catalog-driven isle frame agreement, tile conversions and fail-closed source loading.

Production loads require all four copies. Bootstrap source loads accept absent
unserved copies but validate every present copy and never bypass served history.
Set ELORIA_V2_BAKES to all current bakes for full marker tile verification.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import sys

import pytest

V2 = Path(__file__).resolve().parents[2]
CHECKOUT = V2.parents[2]
sys.path.insert(0, str(V2 / "_continent_v2"))
sys.path.insert(0, str(CHECKOUT / "godot-client" / "tools"))
import frames as F
import continent_v2_territories as T

MAPS = tuple(F.regions())


@pytest.fixture(scope="module")
def all_frames():
    return F.load_all()


def test_catalog_maps_have_one_valid_frozen_frame(all_frames):
    assert set(all_frames) == set(MAPS)
    plan = json.loads((V2 / "_continent_v2/continent-v2-plan.json").read_text())
    assert set(all_frames) == {r["id"] for r in plan["territories"]}
    for frame in all_frames.values():
        assert frame.cells[0] == frame.cells[1]
        assert frame.cells[0] % 6 == 0 and 0 < frame.cells[0] <= 2048
        assert frame.collision_origin == (-float(frame.origin[0]), float(frame.origin[1]))
        assert all(v == int(v) for v in frame.lattice)
        stub = json.loads((V2 / frame.region / "world.json").read_text())
        geography = stub["continentGeography"]
        rings = geography.get("ownershipPolygons", [geography["ownershipPolygon"]])
        for ring in rings:
            for x, z in ring:
                tx, ty = frame.tile_of_continent(x, z)
                assert 4 <= tx <= frame.cells[0] - 4
                assert 4 <= ty <= frame.cells[1] - 4


def test_tile_edges_and_outside_rule():
    frame = F.Frame("fixture", "Fixture", (3, 7), (12, 12), (100., 0., 200.))
    assert frame.tile(-3., 7.) == (0, 0)
    assert frame.tile(-2.0001, 6.0001) == (0, 0)
    assert frame.tile(-2., 6.) == (1, 1)
    assert frame.tile_of_continent(98.5, 205.5) == (1, 1)
    for point in [(-3.0001, 0.), (9., 0.), (0., 7.0001), (0., -5.)]:
        with pytest.raises(F.FrameError, match="outside"):
            frame.tile(*point)


def test_conversions_round_trip(all_frames):
    rng = random.Random(7)
    for frame in all_frames.values():
        for _ in range(500):
            tx, ty = rng.randrange(frame.cells[0]), rng.randrange(frame.cells[1])
            assert frame.tile(*frame.local(tx, ty)) == (tx, ty)
            assert frame.tile_of_continent(*frame.continent(tx, ty)) == (tx, ty)
            x, z = rng.uniform(-500, 500), rng.uniform(-500, 500)
            assert frame.to_local(*frame.to_continent(x, z)) == pytest.approx((x, z))


def _records_with_tiles(doc):
    for section in ("spawnPoints", "landmarks", "interactives", "npcMarkers", "harvestables", "portals"):
        for record in doc.get(section, []):
            if "serverTile" in record:
                yield section, record


def test_package_markers_and_generated_defaults_use_the_frame(all_frames):
    checked = 0
    for region in MAPS:
        manifest = json.loads((V2 / region / "client/world.json").read_text())
        assert len([s for s in manifest["spawnPoints"] if s.get("default")]) == 1
        for section, record in _records_with_tiles(manifest):
            x, _, z = record["position"]
            assert list(all_frames[region].tile(x, z)) == record["serverTile"], (region, section, record["id"])
            checked += 1
    assert checked >= len(MAPS) + 15


def _bakes():
    out = []
    for item in filter(None, os.environ.get("ELORIA_V2_BAKES", "").split(os.pathsep)):
        path = Path(item)
        out.append(path / "continent-authoring.json" if path.is_dir() else path)
    return out


@pytest.mark.skipif(not _bakes(), reason="ELORIA_V2_BAKES names no bake of a v2 territory")
def test_equals_bake_server_tile_for_every_marker(all_frames):
    seen = set()
    for path in _bakes():
        doc = json.loads(path.read_text())
        frame = all_frames[doc["regionId"]]
        seen.add(frame.region)
        server = doc["server"]
        assert (tuple(server["origin"]), tuple(server["cells"])) == (frame.origin, frame.cells), path
        assert tuple(server["collisionOriginMetres"]) == frame.collision_origin, path
        assert tuple(doc["continentTranslation"]) == frame.translation, path
        records = [record for values in doc["gameplay"].values() for record in values]
        if doc.get("generatedArrival"):
            records.append(doc["generatedArrival"])
        for record in records:
            if "serverTile" in record:
                x, _, z = record["position"]
                assert list(frame.tile(x, z)) == record["serverTile"], (path, record["id"])
    assert seen == set(MAPS), "supply every current catalog bake"


def test_every_scene_marker_lies_in_its_window(all_frames):
    total = 0
    for region in MAPS:
        scene = T.load_scene(CHECKOUT / "godot-client/world_authoring/regions" / region / f"{region}.tscn")
        for path, section in scene.nodes.items():
            if path.startswith(("Gameplay/", "RuntimePoints/")) and scene.script_of(section).endswith("gameplay_marker.gd"):
                matrix = scene.world(path)
                all_frames[region].tile(float(matrix[0, 3]), float(matrix[2, 3]))
                total += 1
    assert total == 259  # 254 conserved source markers plus five public storage chests.


def test_every_spawn_row_lies_in_its_window_one_row_a_tile(all_frames):
    total = 0
    for region in MAPS:
        table = json.loads((V2 / region / "content/spawns.json").read_text())
        tiles = {}
        for row in table["spawns"]:
            tile = all_frames[region].tile(*row["local"])
            assert tile not in tiles, (region, row["id"], tiles.get(tile))
            tiles[tile] = row["id"]
            total += 1
    assert total == 1027


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture()
def source_fixture(tmp_path):
    region = "fixture"
    base = tmp_path / "eloria-assets/maps/continent-v2" / region
    geography = {"translation": [100., 0., 200.], "ownershipPolygon": [[98, 202], [103, 202], [103, 199], [98, 199]]}
    server = {"origin": [3, 7], "cells": [12, 12], "collisionOriginMetres": [-3., 7.]}
    coordinate = {"serverOrigin": [3, 7], "serverCells": [12, 12], "metresPerTile": 1., "invertServerY": True}
    resource = f"res://../eloria-assets/maps/continent-v2/{region}/client/world.json"
    write_json(tmp_path / F.CATALOG, {"entries": [{"id": region, "label": "Fixture",
        "manifestPath": f"res://../eloria-assets/maps/continent-v2/{region}/world.json",
        "authoringSpecPath": f"res://world_authoring/regions/{region}/region-authoring-spec.json",
        "publishedManifestPath": resource}]})
    write_json(base / "world.json", {"server": server, "continentGeography": geography})
    write_json(tmp_path / f"godot-client/world_authoring/regions/{region}/region-authoring-spec.json",
        {"server": server, "continentTranslation": geography["translation"]})
    return tmp_path, {"manifest": resource, "coordinateTransform": coordinate,
        "continentGeography": geography, "status": "continent-v2-client-preview"}


def edit(path, change):
    doc = json.loads(path.read_text()); change(doc); write_json(path, doc)


def test_prepublication_source_needs_no_registry_or_package(source_fixture):
    root, row = source_fixture
    assert F.load_source("fixture", root).origin == (3, 7)
    with pytest.raises(F.FrameError, match="missing"):
        F.load("fixture", root)
    write_json(root / F.REGISTRY, {"maps": {"fixture": row}})
    assert F.load_source("fixture", root).cells == (12, 12)
    with pytest.raises(F.FrameError, match="missing"):
        F.load("fixture", root)


def test_prepublication_source_validates_every_present_copy(source_fixture):
    root, row = source_fixture
    write_json(root / F.REGISTRY, {"maps": {"fixture": row}})
    edit(root / F.REGISTRY, lambda d: d["maps"]["fixture"]["coordinateTransform"].update(serverOrigin=[4, 7]))
    with pytest.raises(F.FrameError, match="registry row: origin"):
        F.load_source("fixture", root)


@pytest.mark.parametrize("served_by", ["registry", "package"])
def test_prepublication_source_cannot_bypass_served_history(source_fixture, served_by):
    root, row = source_fixture
    if served_by == "registry":
        row["status"] = "continent-v2-served"
        write_json(root / F.REGISTRY, {"maps": {"fixture": row}})
    else:
        write_json(root / "eloria-assets/maps/continent-v2/fixture/client/world.json",
            {**row, "collision": {"servedGrid": {"binary": "served-grid.escg.gz"}}})
    with pytest.raises(F.FrameError, match="served frame needs"):
        F.load_source("fixture", root)


def test_strict_four_copy_agreement_and_refusals(source_fixture):
    root, row = source_fixture
    write_json(root / F.REGISTRY, {"maps": {"fixture": row}})
    package = root / "eloria-assets/maps/continent-v2/fixture/client/world.json"
    write_json(package, row)
    assert F.load("fixture", root).origin == (3, 7)
    edit(package, lambda d: d["coordinateTransform"].update(serverCells=[18, 18]))
    with pytest.raises(F.FrameError, match="published manifest: cells"):
        F.load("fixture", root)
    write_json(package, row)
    spec = root / "godot-client/world_authoring/regions/fixture/region-authoring-spec.json"
    edit(spec, lambda d: d["server"].update(collisionOriginMetres=[-3, 8]))
    with pytest.raises(F.FrameError, match="region-authoring-spec: collisionOriginMetres"):
        F.load("fixture", root)


def test_source_refuses_fractional_continent_tile_edges(source_fixture):
    root, _ = source_fixture
    edit(root / "eloria-assets/maps/continent-v2/fixture/world.json",
        lambda d: d["continentGeography"].update(translation=[100.5, 0, 200]))
    edit(root / "godot-client/world_authoring/regions/fixture/region-authoring-spec.json",
        lambda d: d.update(continentTranslation=[100.5, 0, 200]))
    with pytest.raises(F.FrameError, match="whole continent metres"):
        F.load_source("fixture", root)
