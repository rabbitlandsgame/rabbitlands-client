"""The Godot snapshot is a complete, hash-bound shared-world input."""
from __future__ import annotations

import hashlib
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import authoring as A
import authoring_catalog as C


def test_published_manymouth_stelae_pair_keeps_both_ids_when_one_moves():
    contract = C.load_region_spec(
        C.CLIENT / "godot-client/world_authoring/regions/manymouth_delta/region-authoring-spec.json")
    baked = A.load_snapshot(contract.snapshot_path, contract=contract)
    original = copy.deepcopy(baked.document)
    records = [entry for entry in original["gameplay"]["landmarks"]
               if entry["id"] == "stelae-court"]
    assert len(records) == 2
    assert {entry["node"] for entry in records} == {
        "Landmark_StelaeCourt", "Lore_stelae_court"}
    original_positions = {entry["node"]: entry["position"][:] for entry in records}
    moved = next(entry for entry in records if entry["node"] == "Lore_stelae_court")
    moved["position"][0] += 1.25
    A._validate_gameplay(original, True, contract)
    snapshot = replace(baked, document=original)
    manifest = A.authored_gameplay(snapshot)
    emitted = [entry for entry in manifest["landmarks"] if entry["id"] == "stelae-court"]
    assert len(emitted) == 2
    by_node = {entry["node"]: entry for entry in emitted}
    assert set(by_node) == set(original_positions)
    assert by_node["Landmark_StelaeCourt"]["position"] == original_positions["Landmark_StelaeCourt"]
    assert by_node["Lore_stelae_court"]["position"][0] == pytest.approx(
        original_positions["Lore_stelae_court"][0] + 1.25)
    moved["node"] = "Landmark_StelaeCourt"
    with pytest.raises(A.AuthoringError, match="distinct source nodes"):
        A._validate_gameplay(original, True, contract)
    original["gameplay"]["landmarks"] = [entry for entry in original["gameplay"]["landmarks"]
                                            if entry is not moved]
    next(entry for entry in original["gameplay"]["landmarks"]
         if entry["id"] == "stelae-court")["node"] = "Foreign_StelaeCourt"
    with pytest.raises(A.AuthoringError, match="distinct source nodes"):
        A._validate_gameplay(original, True, contract)


def test_sunmane_deleted_ramp_routes_remain_claimed_and_do_not_resurrect():
    contract = C.load_region_spec(
        C.CLIENT / "godot-client/world_authoring/regions/sunmane_steppe/region-authoring-spec.json")
    baked = A.load_snapshot(contract.snapshot_path, contract=contract)
    ramp_ids = {"east-gate-main-ramp", "east-gate-town-ramp"}
    assert ramp_ids <= set(baked.document["replacements"]["routeIds"])
    def world_with_native_ramps():
        return SimpleNamespace(
            roads=[{"id": identity, "points": []} for identity in sorted(ramp_ids)],
            height=np.zeros((2, 2)), x=np.arange(2), z=np.arange(2),
            gx=np.zeros((2, 2)), gz=np.zeros((2, 2)), x0=0.0, z0=0.0,
            crossing_sites=[])

    present = world_with_native_ramps()
    A.replace_routes(present, baked)
    for identity in ramp_ids:
        path = next(path for path in baked.document["paths"] if path["id"] == identity)
        output = [road for road in present.roads if road["id"] == identity]
        assert len(output) == 1
        assert len(output[0]["points"]) == len(path["points"])
        assert output[0]["widths"] == pytest.approx(
            [point["width"] * 0.5 for point in path["points"]])
    deleted = copy.deepcopy(baked.document)
    deleted["paths"] = [path for path in deleted["paths"] if path["id"] not in ramp_ids]
    A._validate_replacements(deleted, True, contract)
    snapshot = replace(baked, document=deleted)
    world = world_with_native_ramps()
    A.replace_routes(world, snapshot)
    assert not ramp_ids & {road["id"] for road in world.roads}


def test_idless_published_moor_lake_claims_survive_control_deletion():
    contract = C.load_region_spec(
        C.CLIENT / "godot-client/world_authoring/regions/grey_moors/region-authoring-spec.json")
    baked = A.load_snapshot(contract.snapshot_path, contract=contract)
    assert {"moor_headwater_tarn", "moorwater_pool"} <= set(
        baked.document["replacements"]["planFeatureIds"])
    plan = json.loads((A.HERE / "diagonal-plan.json").read_text(encoding="utf-8"))
    assert all("id" not in lake for lake in plan["lakes"])
    deleted = copy.deepcopy(baked.document)
    deleted["waterRegions"] = []
    A._validate_replacements(deleted, True, contract)
    after = A.apply_plan(plan, replace(baked, document=deleted))
    assert {lake["name"] for lake in after["lakes"]} == {"Mirror Lake"}
    altered = copy.deepcopy(plan)
    altered["lakes"][0]["radii"][0] += 1
    with pytest.raises(A.AuthoringError, match="source record changed"):
        A.apply_plan(altered, replace(baked, document=deleted))


def test_ferry_replacement_registry_persists_without_a_quay_control():
    contract = SimpleNamespace(
        id="crownwater", owned_route_ids=(), required_route_ids=(),
        owned_plan_feature_ids=(),
        owned_ferry_connection_ids=("crownwater--westhaven",))
    document = {"paths": [], "waterRegions": [], "replacements": {
        "routeIds": [], "planFeatureIds": [],
        "ferryConnectionIds": ["crownwater--westhaven"]}}
    A._validate_replacements(document, True, contract)
    document["replacements"]["ferryConnectionIds"] = []
    with pytest.raises(A.AuthoringError, match="ferry connection registry"):
        A._validate_replacements(document, True, contract)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    client = tmp_path / "client"
    authoring = client / "eloria-assets/maps/nymara-regions/sunmane_steppe/authoring"
    scene = client / "godot-client/world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn"
    dependency = scene.with_name("base-heights.f32le")
    asset = client / "godot-client/assets/asset.glb"
    scene.parent.mkdir(parents=True)
    asset.parent.mkdir(parents=True)
    scene.write_text("[gd_scene format=3]\n", encoding="utf-8")
    dependency.write_bytes(b"source heights")
    asset.write_bytes(b"glTF source fixture")
    authoring.mkdir(parents=True)
    heights = np.arange(397 * 397, dtype="<f4").reshape(397, 397)
    sidecar = authoring / "base-heights.f32le"
    sidecar.write_bytes(heights.tobytes())
    resolved = authoring / "resolved-heights.f32le"
    resolved.write_bytes(heights.tobytes())
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    document = {
        "schema": A.SCHEMA,
        "regionId": "sunmane_steppe",
        "coordinateSpace": "territory-local",
        "axes": {"x": "east", "y": "up", "z": "south"},
        "continentTranslation": [1200.0, 0.0, 720.0],
        "server": {"metresPerTile": 1.0, "origin": [194, 292], "cells": [792, 792],
                   "collisionOriginMetres": [-194.0, 292.0]},
        "sources": {
            "scene": {"path": scene.relative_to(client).as_posix(), "sha256": digest(scene)},
            "dependencies": [
                {"path": asset.relative_to(client).as_posix(), "sha256": digest(asset)},
                {"path": dependency.relative_to(client).as_posix(), "sha256": digest(dependency)},
            ],
        },
        "authority": {"terrain": True, "water": True, "paths": True,
                      "objects": True, "gameplay": True},
        "replacements": {"routeIds": ["road-a"], "planFeatureIds": []},
        "terrain": {"origin": [-194.0, -500.0], "cellMetres": 2.0,
                    "previewUvMetresInverse": 0.24, "width": 397, "height": 397,
                    "baseHeights": {"path": sidecar.name, "sha256": digest(sidecar),
                                    "encoding": "float32-le"},
                    "resolvedHeights": {"path": resolved.name, "sha256": digest(resolved),
                                        "encoding": "float32-le",
                                        "includes": ["patches", "road-earthworks", "river-cuts"]},
                    "baseSurface": {"preset": "Grass", "rotationDegrees": 0.0,
                                    "materialMode": "surface"},
                    "patches": []},
        "groundRegions": [],
        "waterRegions": [],
        "paths": [{"id": "road-a", "kind": "road", "routingRole": "required",
                   "replacesRouteId": "road-a", "replacesPlanFeatureId": None,
                   "closed": False, "surface": {"preset": "Worn earth", "rotationDegrees": 0.0,
                                                "materialMode": "road"},
                   "points": [{"position": [-2, 3, -2], "width": 4},
                              {"position": [2, 3, 2], "width": 4}], "properties": {}}],
        "bridges": [],
        "objects": [{"id": "object-a", "nodeName": "ObjectA", "assetId": "asset:a",
                    "scenePath": "res://assets/asset.glb", "sourceNode": "ObjectA", "matrix": identity,
                    "bakedSource": {"path": asset.relative_to(client).as_posix(),
                                    "sha256": digest(asset), "sourceNode": "ObjectA"},
                    "collisionRole": "solid", "metadata": {}}],
        "gameplay": {
            "spawnPoints": [{"id": "spawn", "position": [0, 3, 0], "extras": {"default": True}}],
            "portals": [{"id": "portal", "position": [1, 3, 1],
                         "extras": {"destinationMap": "sunmane_wind_caves"}}],
            "interactives": [], "landmarks": [], "harvestables": [],
            "npcMarkers": [], "ambientPopulation": [],
        },
        "seams": {"ownershipPolygonSha256": "1" * 64, "anchors": []},
    }
    path = authoring / "continent-authoring.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(A, "CLIENT", client)
    return path, document


def test_valid_snapshot_loads_hash_bound_heights_and_translates_points(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    snapshot = A.load_snapshot(path, production=False)

    assert snapshot.base_heights().shape == (397, 397)
    assert snapshot.base_heights()[0, :4].tolist() == [0, 1, 2, 3]
    assert snapshot.continent_point([-2, 3, -2]).tolist() == [1198, 3, 718]
    assert set(snapshot.source_sha256) == {
        "godot-client/world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn",
        "godot-client/world_authoring/regions/sunmane_steppe/base-heights.f32le",
        "godot-client/assets/asset.glb",
    }


def test_authored_crossing_endpoints_follow_saved_asset_transform_and_restore():
    crossing = {"authoredCrossing": {
        "id": "bridge-massif",
        "walkNode": "Walk_Landmark_SurveyedBridge_0__alpine_gravel",
        "localEndpoints": [[-2.0, 1.0, 0.0], [2.0, 3.0, 0.0]],
    }}
    original = {
        "id": "asset-bridge", "nodeName": "Landmark_SurveyedBridge_0",
        "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 20, 30, 1],
        "metadata": crossing,
    }
    # 90 degrees around +Y, uniform scale two, then translation.  The same
    # column-major matrix is handed to scene_io for the complete visual/walk
    # subtree, so this verifies the endpoint half of that shared authority.
    moved = dict(original, matrix=[
        0, 0, -2, 0,
        0, 2, 0, 0,
        2, 0, 0, 0,
        15, 25, 35, 1,
    ])

    before = A.transformed_authored_crossings([original])
    after = A.transformed_authored_crossings([moved])
    restored = A.transformed_authored_crossings([original])

    assert before[0]["endpoints"] == [[8.0, 21.0, 30.0], [12.0, 23.0, 30.0]]
    assert after[0]["endpoints"] == [[15.0, 27.0, 39.0], [15.0, 31.0, 31.0]]
    assert after[0]["walkNode"] == \
        "Walk_Landmark_SurveyedBridge_0__alpine_gravel"
    assert restored == before


def test_authored_crossing_ids_are_unique():
    entry = {
        "id": "asset-bridge", "nodeName": "Landmark_SurveyedBridge_0",
        "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        "metadata": {"authoredCrossing": {
            "id": "bridge-massif", "walkNode": "Walk_Bridge",
            "localEndpoints": [[-1, 0, 0], [1, 0, 0]],
        }},
    }
    with pytest.raises(A.AuthoringError, match="duplicate authored crossing"):
        A.transformed_authored_crossings([entry, dict(entry, id="asset-bridge-copy")])


def test_production_runtime_bindings_resolve_qualified_markers_and_saved_moves():
    from types import SimpleNamespace

    artifacts = A.CLIENT / "godot-client/test-artifacts/sunmane-edit-regression"
    before = A.load_snapshot(artifacts / "before/continent-authoring.json")
    after = A.load_snapshot(artifacts / "after/continent-authoring.json")
    before_content, after_content = SimpleNamespace(), SimpleNamespace()
    assert A.apply_runtime_bindings(before_content, before) == {
        "bindings": 191, "runtimePoints": 110}
    A.apply_runtime_bindings(after_content, after)

    moved_runtime = "maps.txt:1255:return:sunmane_gauntlet_2->sunmane_steppe@183:142"
    moved_aliases = [identity for identity, binding in before_content.runtime_bindings.items()
                     if binding["marker"] == {"section": "portals", "id": "cave-crystal_hollow"}]
    assert len(moved_aliases) == 2
    before_alias_points = [before_content.authored_runtime_points[(A.SUNMANE, identity)]
                           for identity in moved_aliases]
    assert not np.allclose(before_alias_points[0], before_alias_points[1])
    assert np.allclose(
        after_content.authored_runtime_points[(A.SUNMANE, moved_runtime)] -
        before_content.authored_runtime_points[(A.SUNMANE, moved_runtime)],
        [ -5.0, .75, 4.0])
    for identity in moved_aliases:
        assert np.allclose(
            after_content.authored_runtime_points[(A.SUNMANE, identity)] -
            before_content.authored_runtime_points[(A.SUNMANE, identity)],
            [4.0, .5, -3.0])
    runtime_binding = before_content.runtime_bindings[moved_runtime]
    assert runtime_binding["targetOffset"] == [0.0, 0.0, 0.0]
    assert all(before_content.runtime_bindings[identity]["targetOffset"][1] == 0.0
               for identity in moved_aliases)
    assert not hasattr(before_content, "authored_server_points")


def test_saved_seam_anchors_must_match_shared_connection_frame(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path, document = fixture(tmp_path, monkeypatch)
    document["seams"]["anchors"] = [
        {"id": "sunmane--verdant", "anchor": [-10.0, 2.0, 15.0]},
    ]
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)
    world = SimpleNamespace(connections=[{
        "id": "sunmane--verdant",
        "regions": ["sunmane_steppe", "verdant_stair"],
        "anchor": [1190.0, 99.0, 735.0],
    }])

    A.verify_seam_anchors(world, snapshot)
    world.connections[0]["anchor"] = [1190.0, 735.0]
    A.verify_seam_anchors(world, snapshot)
    world.connections.append({
        "id": "sunmane--ferry-neighbour", "type": "ferry",
        "regions": ["sunmane_steppe", "ferry_neighbour"],
    })
    A.verify_seam_anchors(world, snapshot)
    world.connections[0]["anchor"][0] += 0.01
    with pytest.raises(A.AuthoringError, match="seam anchor moved"):
        A.verify_seam_anchors(world, snapshot)
    world.connections.clear()
    with pytest.raises(A.AuthoringError, match="seam links differ"):
        A.verify_seam_anchors(world, snapshot)


def test_saved_region_with_ferry_only_neighbours_needs_no_road_seam_anchors(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path, document = fixture(tmp_path, monkeypatch)
    document["seams"]["anchors"] = []
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)
    world = SimpleNamespace(connections=[{
        "id": "sunmane--ferry-neighbour", "type": "ferry",
        "regions": ["sunmane_steppe", "ferry_neighbour"],
    }])
    A.verify_seam_anchors(world, snapshot)
    world.connections.append({
        "id": "sunmane--walk-neighbour", "type": "walk",
        "regions": ["sunmane_steppe", "walk_neighbour"],
        "anchor": [1190.0, 735.0],
    })
    with pytest.raises(A.AuthoringError, match="seam links differ"):
        A.verify_seam_anchors(world, snapshot)
    world.connections[-1]["type"] = "unknown"
    with pytest.raises(A.AuthoringError, match="unknown seam connection types"):
        A.verify_seam_anchors(world, snapshot)


def test_ownership_and_seam_validation_use_the_snapshot_region(tmp_path, monkeypatch):
    from types import SimpleNamespace

    path, document = fixture(tmp_path, monkeypatch)
    document["regionId"] = "amethyst_barrens"
    document["continentTranslation"] = [950.0, 0.0, 400.0]
    document["seams"] = {
        "ownershipPolygonSha256": "placeholder",
        "anchors": [{"id": "amethyst--sunmane", "anchor": [3.0, 7.0, -4.0]}],
    }
    world = SimpleNamespace(
        polygons={"sunmane_steppe": [[0, 0]], "amethyst_barrens": [[1, 2], [3, 4]]},
        connections=[{
            "id": "amethyst--sunmane",
            "regions": ["amethyst_barrens", "sunmane_steppe"],
            "anchor": [953.0, 396.0],
        }],
    )
    document["seams"]["ownershipPolygonSha256"] = A.ownership_polygon_sha256(
        world, "amethyst_barrens")
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)

    A.verify_ownership(world, snapshot)
    A.verify_seam_anchors(world, snapshot)
    world.polygons["amethyst_barrens"].append([5, 6])
    with pytest.raises(A.AuthoringError, match="amethyst_barrens: ownership polygon changed"):
        A.verify_ownership(world, snapshot)


def test_production_plan_pins_every_authored_sunmane_seam():
    import landscape as L
    snapshot=A.load_snapshot()
    sites=A.apply_plan(L.load_plan(),snapshot)["connection_sites"]

    expected={entry["id"]:snapshot.continent_point(entry["anchor"])[[0,2]].tolist()
              for entry in snapshot.document["seams"]["anchors"]}
    assert {identity:sites[identity] for identity in expected}==expected


def test_apply_plan_injects_saved_seam_sites_and_rejects_conflicts(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["seams"]["anchors"] = [
        {"id": "sunmane--verdant", "anchor": [-10.0, 2.0, 15.0]},
    ]
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)

    plan = {"connection_sites": {"unrelated--link": [7, 8]}, "rivers": []}
    applied = A.apply_plan(plan, snapshot)
    assert applied["connection_sites"] == {
        "unrelated--link": [7, 8],
        "sunmane--verdant": [1190.0, 735.0],
    }
    assert plan["connection_sites"] == {"unrelated--link": [7, 8]}

    plan["connection_sites"]["sunmane--verdant"] = [1191.0, 735.0]
    with pytest.raises(A.AuthoringError, match="conflicts with registered connection site"):
        A.apply_plan(plan, snapshot)


def test_all_production_seam_sites_are_safe_boundary_stations_with_dry_terminals():
    """Bounded preflight of every scene-owned station before the full composition."""
    from types import SimpleNamespace
    import landscape as L
    from river_crossings import setback_metres
    from world_layout import CELL, SEAM_ROAD_WIDTH_METRES, World, ownership_map

    snapshot = A.load_snapshot()
    plan = A.apply_plan(L.load_plan(), snapshot)
    ids, owner, x0, z0 = ownership_map(plan, CELL)
    x1, z1 = plan["bounds"][2:]
    regions = {entry["id"]: entry for entry in plan["regions"]}
    world = SimpleNamespace(
        plan=plan,
        ids=ids,
        centers=np.asarray([regions[identity]["center"] for identity in ids], float),
        owner=owner,
        x0=x0,
        z0=z0,
        x1=x1,
        z1=z1,
        connections=[],
        height_at=lambda x, z: np.zeros(np.broadcast_arrays(x, z)[0].shape),
        owner_at=lambda x, z: World.owner_at(world, x, z),
        adjacent_edges=lambda: World.adjacent_edges(world),
        seam_terminal_penalty=lambda point, normal: 0.0,
        seam_river_penalty=lambda regions, point, normal: 0.0,
    )
    World.plan_connections(world)
    connections = {entry["id"]: entry for entry in world.connections}
    expected = {
        entry["id"]: snapshot.continent_point(entry["anchor"])[[0, 2]]
        for entry in snapshot.document["seams"]["anchors"]
    }
    for identity, point in expected.items():
        np.testing.assert_allclose(connections[identity]["anchor"], point)

    # Production dry-terminal lookup snaps to the two-metre world grid.  Test
    # the full geometric channel/lake domain in a bounded window around each
    # snapped terminal.  Supplying very low ground is conservative: every
    # possible channel cell is wet regardless of the final terrain height.
    setback = setback_metres(L.crossing_policy(plan), SEAM_ROAD_WIDTH_METRES)
    radius = int(np.ceil(setback / CELL)) + 2
    for identity in expected:
        connection = connections[identity]
        anchor = np.asarray(connection["anchor"], float)
        normal = np.asarray(connection["normal"], float)
        for offset in (-9.0, -4.0, 0.0, 4.0, 9.0):
            terminal = anchor + normal * offset
            ix = int(np.rint((terminal[0] - x0) / CELL))
            iz = int(np.rint((terminal[1] - z0) / CELL))
            xs = x0 + np.arange(ix - radius, ix + radius + 1) * CELL
            zs = z0 + np.arange(iz - radius, iz + radius + 1) * CELL
            gx, gz = np.meshgrid(xs, zs)
            water = L.water_fields(gx, gz, height=np.full(gx.shape, -1e9), plan=plan)["river_mask"]
            wz, wx = np.nonzero(water)
            distance = np.inf if not len(wx) else float(np.min(np.hypot(
                xs[wx] - (x0 + ix * CELL), zs[wz] - (z0 + iz * CELL))))
            assert distance > setback, f"{identity} terminal {terminal.tolist()} is only {distance}m from water"


@pytest.mark.parametrize(("mutate", "message"), [
    (lambda document: document["authority"].update(objects=False), "authority"),
    (lambda document: document["paths"].append(dict(document["paths"][0])), "duplicate stable ids"),
    (lambda document: document["gameplay"].update(spawnPoints=[]), "retain an authored spawn"),
    (lambda document: document["gameplay"].update(portals=[]), "retain authored links"),
])
def test_incomplete_authority_never_falls_back(tmp_path, monkeypatch, mutate, message):
    path, document = fixture(tmp_path, monkeypatch)
    mutate(document)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(A.AuthoringError, match=message):
        A.load_snapshot(path, production=False)


def test_uv_scale_is_explicit_and_triplanar_never_silently_changes_mapping(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["terrain"]["previewUvMetresInverse"] = 0.0
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="previewUvMetresInverse must be positive"):
        A.load_snapshot(path, production=False)

    path, document = fixture(tmp_path / "triplanar", monkeypatch)
    document["terrain"]["baseSurface"]["pbrOverrides"] = {
        "albedoColor": [1, 1, 1, 1], "albedoTexture": None,
        "normalTexture": None, "ormTexture": None, "normalScale": 1,
        "roughness": 1, "metallic": 0, "uvScale": [0.2, 0.2, 0.2],
        "uvOffset": [0, 0, 0], "triplanar": True, "worldTriplanar": True,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="use an explicit UV-based source material"):
        A.load_snapshot(path, production=False)


def test_scene_and_height_changes_require_a_new_export(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    A.load_snapshot(path, production=False)
    scene = A.CLIENT / "godot-client/world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn"
    scene.write_text("[gd_scene format=3]\n[node name=\"changed\"]\n", encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="changed after snapshot export"):
        A.load_snapshot(path, production=False)

    path, _ = fixture(tmp_path / "second", monkeypatch)
    sidecar = path.with_name("base-heights.f32le")
    sidecar.write_bytes(sidecar.read_bytes()[:-4])
    with pytest.raises(A.AuthoringError, match="changed after snapshot export"):
        A.load_snapshot(path, production=False)


def test_sidecars_cannot_escape_the_authoring_directory(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["terrain"]["baseHeights"]["path"] = "../base-heights.f32le"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(A.AuthoringError, match="escapes"):
        A.load_snapshot(path, production=False)


def test_gameplay_is_a_complete_replacement_and_derives_server_tiles(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    snapshot = A.load_snapshot(path, production=False)
    template = {"spawnPoints": [{"id": "retired"}], "spawns": [{"id": "retired"}],
                "portals": [{"id": "retired"}],
                "ambientPopulation": {"note": "runtime scenery", "groups": [{"id": "retired"}]}}

    result = A.apply_gameplay(template, snapshot)

    assert result["spawnPoints"] == result["spawns"] == [
        {"default": True, "id": "spawn", "position": [0.0, 3.0, 0.0], "serverTile": [194, 292]}]
    assert result["portals"] == [{"destinationMap": "sunmane_wind_caves", "id": "portal",
                                  "position": [1.0, 3.0, 1.0], "serverTile": [195, 291]}]
    assert result["ambientPopulation"] == {"note": "runtime scenery", "groups": []}


def test_gameplay_empty_key_and_false_default_are_semantic_normalization(tmp_path, monkeypatch):
    path,document=fixture(tmp_path,monkeypatch)
    document["gameplay"]["interactives"]=[
        {"id":"normalized-omitted","position":[1,0,0]},
        {"id":"old-empty","position":[0,0,0],"key":""}]
    document["gameplay"]["spawnPoints"].append(
        {"id":"arrival-datum","position":[2,0,2],"default":False})
    document["gameplay"]["spawnPoints"].sort(key=lambda value:value["id"])
    path.write_text(json.dumps(document),encoding="utf-8")

    gameplay=A.authored_gameplay(A.load_snapshot(path,production=False))

    assert gameplay["interactives"][0].get("key","")==gameplay["interactives"][1].get("key","")==""
    arrival=next(value for value in gameplay["spawnPoints"] if value["id"]=="arrival-datum")
    assert not arrival.get("default",False)


def test_authored_terrain_replaces_the_shared_overlap_without_resampling(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path, _ = fixture(tmp_path, monkeypatch)
    snapshot = A.load_snapshot(path, production=False)
    world = SimpleNamespace(x0=0.0, z0=0.0, height=np.full((601, 751), -1.0))

    report = A.apply_terrain(world, snapshot)

    # Local [-194,-500] + [1200,720] starts at global [1006,220].
    assert world.height[110, 503] == 0.0
    assert world.height[111, 504] == snapshot.base_heights()[1, 1]
    assert world.height[109, 503] == -1.0
    # The authoring envelope extends past the east continent edge and is clipped there.
    assert report == {"sourceVertices": 157609, "appliedVertices": 98456,
                      "globalBounds": [[1006.0, 220.0], [1798.0, 1012.0]]}


def test_production_cell_ownership_expands_to_shared_vertices_before_ring(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path, _ = fixture(tmp_path, monkeypatch)
    snapshot = A.load_snapshot(path, production=False)
    height = np.full((401, 751), -1.0)
    owner = np.ones((400, 750), dtype=np.int16)
    owner[110, 503:505] = 0
    world = SimpleNamespace(x0=0.0, z0=0.0, height=height, owner=owner,
                            ids=[A.SUNMANE, "neighbour"])

    A.apply_terrain(world, snapshot)

    # Adjacent owned cells contribute shared vertices once; the one-vertex seam
    # ring expands that exact 2x3 block by one in every direction.
    changed = world.height != -1.0
    rows, columns = np.nonzero(changed)
    # Row 109 and column 502 are outside the authored envelope and remain
    # untouched even though they are inside the ownership dilation.
    assert (rows.min(), rows.max(), columns.min(), columns.max()) == (110, 112, 503, 506)
    assert changed.sum() == 12
    np.testing.assert_array_equal(world.authored_terrain_authority,changed)
    np.testing.assert_array_equal(
        world.authored_terrain_height[changed],world.height[changed])

    # The same construction clips cleanly at the continent's bottom/right
    # boundary and never attempts an owner cell beyond the grid.
    owner[:] = 1;owner[-1, -1] = 0;height[:] = -1.0
    A.apply_terrain(world, snapshot)
    changed = world.height != -1.0
    rows, columns = np.nonzero(changed)
    assert (rows.min(), rows.max(), columns.min(), columns.max()) == (398, 400, 748, 750)
    assert changed.sum() == 9


def _terrain_snapshot(tmp_path, region, values):
    values = np.asarray(values, dtype="<f4")
    folder = tmp_path / region
    folder.mkdir()
    base = folder / "base.f32le"
    resolved = folder / "resolved.f32le"
    base.write_bytes(values.tobytes())
    resolved.write_bytes(values.tobytes())
    document = {
        "regionId": region,
        "continentTranslation": [0.0, 0.0, 0.0],
        "terrain": {"origin": [0.0, 0.0], "cellMetres": 2.0},
    }
    return A.Snapshot(folder / "snapshot.json", document, {}, base, resolved,
                      values.shape[1], values.shape[0])


def test_multiple_authored_terrain_regions_merge_masks_without_overwriting_neighbours(tmp_path):
    from types import SimpleNamespace

    owner = np.zeros((4, 6), dtype=np.int16)
    owner[:, 3:] = 1
    world = SimpleNamespace(x0=0.0, z0=0.0, height=np.zeros((5, 7), float),
                            owner=owner, ids=["west", "east"])
    west = _terrain_snapshot(tmp_path, "west", np.full((5, 7), 10.0))
    east_values = np.full((5, 7), 10.0)
    # These samples are inside the east snapshot rectangle but outside its
    # owned-vertex plus one-ring mask. They must not replace west authority.
    east_values[:, :2] = 99.0
    east = _terrain_snapshot(tmp_path, "east", east_values)

    A.apply_terrain(world, west)
    west_mask = world.authored_terrain_region_masks["west"].copy()
    A.apply_terrain(world, east)

    assert set(world.authored_terrain_region_masks) == {"east", "west"}
    assert np.all(world.authored_terrain_height[west_mask] == 10.0)
    np.testing.assert_array_equal(
        world.authored_terrain_authority,
        world.authored_terrain_region_masks["west"] |
        world.authored_terrain_region_masks["east"],
    )


def test_multiple_authored_terrain_regions_reject_conflicting_shared_ring(tmp_path):
    from types import SimpleNamespace

    owner = np.zeros((4, 6), dtype=np.int16)
    owner[:, 3:] = 1
    world = SimpleNamespace(x0=0.0, z0=0.0, height=np.zeros((5, 7), float),
                            owner=owner, ids=["west", "east"])
    west = _terrain_snapshot(tmp_path, "west", np.full((5, 7), 10.0))
    east_values = np.full((5, 7), 10.0)
    east_values[2, 3] = 10.01
    east = _terrain_snapshot(tmp_path, "east", east_values)

    A.apply_terrain(world, west)
    with pytest.raises(A.AuthoringError, match=r"east: authored terrain conflicts with \['west'\]"):
        A.apply_terrain(world, east)


def test_road_settlement_preserves_authored_overlap_without_mutating_it():
    import landscape as L
    from world_layout import World
    world=World.__new__(World)
    world.x=np.arange(-20.,22.,2.);world.z=np.arange(-20.,22.,2.)
    world.x0=world.x[0];world.z0=world.z[0]
    world.gx,world.gz=np.meshgrid(world.x,world.z)
    world.height=np.zeros_like(world.gx);world.height[:,world.x>=0]=8.
    world.plan={'sea_level':-100.,'rivers':[],'lakes':[]}
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    world.assembly_target=world.height.copy();world.assembly_weight=np.zeros_like(world.height)
    world.road_target=np.zeros_like(world.height);world.road_distance=np.abs(world.gz)
    world.roads=[{'points':[[-18.,0.,0.],[18.,8.,0.]]}];world.quay_contacts=[]
    world.restore_drainage_corridor=lambda stage:None
    world.authored_terrain_authority=(world.gx>=0)
    world.authored_terrain_height=world.height.copy()
    before=world.height.copy()

    world.settle_roads()

    np.testing.assert_array_equal(
        world.height[world.authored_terrain_authority],before[world.authored_terrain_authority])
    assert np.any(world.height[~world.authored_terrain_authority]!=before[~world.authored_terrain_authority])


def test_authored_preview_does_not_become_a_distant_procedural_footing():
    import landscape as L
    from world_layout import World

    def road_world(saved_height):
        world=World.__new__(World)
        world.x=np.arange(-80.,82.,2.);world.z=np.arange(-20.,22.,2.)
        world.x0=world.x[0];world.z0=world.z[0]
        world.gx,world.gz=np.meshgrid(world.x,world.z)
        world.height=np.where(world.gx>=0.,saved_height,0.)
        structure=(world.gx>=-62.)&(world.gx<=-58.)
        world.height[structure]=4.
        world.plan={'sea_level':-100.,'rivers':[],'lakes':[]}
        world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
        world.assembly_target=world.height.copy()
        world.assembly_weight=structure.astype(float)
        world.road_target=np.zeros_like(world.height)
        world.road_distance=np.abs(world.gz)
        world.roads=[{'points':[[-78.,0.,0.],[78.,saved_height,0.]]}]
        world.quay_contacts=[]
        world.restore_drainage_corridor=lambda stage:None
        world.authored_terrain_authority=world.gx>=0.
        world.authored_terrain_height=world.height.copy()
        return world

    low,high=road_world(40.),road_world(80.)
    low.settle_roads();high.settle_roads()

    # Both editor previews remain exact, while their different elevations do
    # not pull the unrelated procedural road forty metres away. The genuine
    # built footing at x=-60 remains fixed in both solves.
    for world,saved_height in ((low,40.),(high,80.)):
        np.testing.assert_array_equal(world.height[world.gx>=0.],saved_height)
        assert world.height[world.z==0.,world.x==-60.][0]==4.
    # The bounded exterior shoulder interpolation may carry centimetres of
    # visual blend; the road core cannot inherit tens of metres from the saved
    # hillside through the global footing envelope.
    assert np.max(abs(low.height[:,low.x==-40.]-high.height[:,high.x==-40.]))<.05
    np.testing.assert_allclose(low.height[low.z==0.,low.x==-40.],
                               high.height[high.z==0.,high.x==-40.],atol=1e-9)


def test_effective_heights_are_the_hash_bound_editor_preview(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    resolved = path.with_name("resolved-heights.f32le")
    values = np.fromfile(resolved, dtype="<f4").reshape(397, 397)
    values[1, 1] = 30.0
    values[2, 2] = 30.0
    resolved.write_bytes(values.astype("<f4").tobytes())
    document["terrain"]["resolvedHeights"]["sha256"] = digest(resolved)
    path.write_text(json.dumps(document), encoding="utf-8")

    heights = A.load_snapshot(path, production=False).effective_heights()

    # Python consumes the exact preview result rather than trying to duplicate
    # Godot's effect evaluation and drifting from what the artist saw.
    assert heights[1, 1] == 30.0
    assert heights[2, 2] == 30.0
    assert heights[3, 0] == 3 * 397


def test_route_registry_survives_deletion_and_required_absence_is_explicit(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["paths"] = []
    path.write_text(json.dumps(document), encoding="utf-8")

    # The owned identity is independent of surviving nodes, so deletion never
    # authorizes a procedural fallback. A production migration then rejects
    # the missing required route explicitly.
    snapshot = A.load_snapshot(path, production=False)
    assert snapshot.document["replacements"]["routeIds"] == ["road-a"]

    document["replacements"]["routeIds"] = list(A.SUNMANE_REQUIRED_ROUTE_IDS)
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="required authored Sunmane routes are absent"):
        A.load_snapshot(path)


def test_owned_plan_water_is_suppressed_before_authored_river_is_added(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["replacements"]["planFeatureIds"] = ["southern_river"]
    document["paths"].append({
        "id": "river", "kind": "river", "routingRole": "decorative",
        "replacesRouteId": None, "replacesPlanFeatureId": "southern_river",
        "closed": False, "surface": {"preset": "Water", "rotationDegrees": 0,
                                      "materialMode": "water"},
        "points": [{"position": [0, 9, 0], "width": 13},
                   {"position": [10, 8, 10], "width": 17}],
        "properties": {"channelDepth": 1.8, "valleyWidth": 73,
                       "bankHeight": 3.1, "mouth": "sea"}})
    document["paths"] = sorted(document["paths"], key=lambda value: value["id"])
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)
    plan = {"rivers": [{"id": "southern_river", "depth": 999, "points": []},
                       {"id": "neighbour", "width": 2, "points": []}]}

    result = A.apply_plan(plan, snapshot)

    assert [river["id"] for river in result["rivers"]] == ["neighbour", "southern_river"]
    authored = result["rivers"][1]
    assert authored["width"] == 8.5
    assert authored["widths"] == [6.5, 8.5]
    assert authored["depth"] == 1.8
    assert authored["authoredSampled"] is True
    assert authored["points"] == [[1200.0, 720.0, 9.0, 6.5], [1210.0, 730.0, 8.0, 8.5]]


def test_saved_ellipse_replaces_lake_and_deleted_control_does_not_restore_it(
        tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["replacements"]["planFeatureIds"] = ["mirror_lake"]
    document["waterRegions"] = [{
        "id": "mirror-lake", "shape": "ellipse",
        "replacesPlanFeatureId": "mirror_lake", "name": "Mirror Lake",
        "center": [3.0, 5.0], "radii": [7.0, 4.0],
        "level": 11.0, "depth": 2.5,
    }]
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)
    plan = {"sea_level": -10.0, "rivers": [], "lakes": [{
        "id": "mirror_lake", "name": "retired", "center": [0, 0],
        "radii": [1, 1], "level": 0, "depth": 99,
    }]}
    applied = A.apply_plan(plan, snapshot)
    assert applied["lakes"] == [{
        "id": "mirror_lake", "name": "Mirror Lake",
        "center": [1203.0, 725.0], "radii": [7.0, 4.0],
        "level": 11.0, "depth": 2.5, "authored": True,
        "resolvedBedAuthority": "saved-terrain",
    }]

    from landscape import water_fields
    x = np.asarray([[1203.0, 1211.0]])
    z = np.asarray([[725.0, 725.0]])
    water = water_fields(x, z, height=np.asarray([[9.0, 9.0]]), plan=applied)
    assert water["mask"].tolist() == [[True, False]]
    assert water["surface"].tolist() == [[11.0, -10.0]]
    # The imported legacy bed-depth is reference metadata. Actual water depth
    # and collision follow water level minus the unchanged saved ground.
    assert water["depth"].tolist() == [[2.0, 0.0]]

    document["waterRegions"] = []
    path.write_text(json.dumps(document), encoding="utf-8")
    deleted = A.apply_plan(plan, A.load_snapshot(path, production=False))
    assert deleted["lakes"] == []


def test_plan_feature_claims_are_unique_across_controls_and_snapshots(
        tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    document["replacements"]["planFeatureIds"] = ["shared_water"]
    document["waterRegions"] = [{
        "id": "lake", "shape": "ellipse",
        "replacesPlanFeatureId": "shared_water", "name": "Lake",
        "center": [0, 0], "radii": [3, 2], "level": 4, "depth": 1,
    }]
    document["paths"].append({
        "id": "river", "kind": "river", "routingRole": "decorative",
        "replacesRouteId": None, "replacesPlanFeatureId": "shared_water",
        "closed": False, "surface": {"preset": "Water", "rotationDegrees": 0.0,
                                         "materialMode": "water"},
        "points": [{"position": [0, 4, 0], "width": 2},
                   {"position": [2, 4, 0], "width": 2}],
        "properties": {"channelDepth": 1, "valleyWidth": 3, "bankHeight": 1},
    })
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="only one saved control"):
        A.load_snapshot(path, production=False)

    document["paths"].pop()
    path.write_text(json.dumps(document), encoding="utf-8")
    first = A.load_snapshot(path, production=False)
    second_document = json.loads(json.dumps(first.document))
    second_document["regionId"] = "other"
    second = A.Snapshot(first.path, second_document, first.source_sha256,
                        first.base_heights_path, first.resolved_heights_path,
                        first.terrain_width, first.terrain_height)
    with pytest.raises(A.AuthoringError, match="claimed by both sunmane_steppe and other"):
        A.apply_plans({"rivers": [], "lakes": []}, [first, second])


def test_optional_rgba8_base_colors_are_hash_bound_and_exact(tmp_path, monkeypatch):
    path, document = fixture(tmp_path, monkeypatch)
    colors = np.arange(397 * 397 * 4, dtype=np.uint8).reshape(397, 397, 4)
    color_path = path.with_name("base-colors.rgba8")
    color_path.write_bytes(colors.tobytes())
    document["terrain"]["baseColors"] = {
        "path": color_path.name, "sha256": digest(color_path),
        "encoding": "rgba8-srgb",
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)
    np.testing.assert_array_equal(snapshot.base_colors(), colors)
    monkeypatch.setattr(A, "AUTHORING_FRAMEWORK_GLOBS", ())
    assert color_path.relative_to(A.CLIENT).as_posix() in snapshot.bound_sources()

    color_path.write_bytes(color_path.read_bytes()[:-1])
    document["terrain"]["baseColors"]["sha256"] = digest(color_path)
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="expected"):
        A.load_snapshot(path, production=False)


def test_authored_river_samples_are_exact_linear_spans_without_legacy_resmoothing():
    import landscape as L
    river={"id":"authored","authoredSampled":True,"width":4.,
           "points":[[0.,0.,0.,1.],[1.,0.,10.,2.],[1.,1.,20.,4.]]}

    np.testing.assert_array_equal(L.river_points(river),river["points"])
    assert len(L.river_points({"points":river["points"]})) == 13
    distance,level,width=L.river_field(
        np.asarray([.5,1.,.5]),np.asarray([0.,.5,.25]),river)

    assert distance.tolist()==pytest.approx([0.,0.,.25])
    assert level.tolist()==pytest.approx([5.,15.,5.])
    assert width.tolist()==pytest.approx([1.5,3.,1.5])


def test_route_replacement_preserves_neighbour_order_and_rebuilds_fields(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path, document = fixture(tmp_path, monkeypatch)
    document["paths"][0]["points"] = [
        {"position": [-2, 3, -2], "width": 8},
        {"position": [2, 3, 2], "width": 12}]
    added = dict(document["paths"][0]);added.update(
        id="road-new", routingRole="decorative", replacesRouteId=None,
        points=[{"position": [5, 3, 5], "width": 4}, {"position": [9, 3, 9], "width": 6}])
    document["paths"].append(added)
    # Deleting every saved bridge control must not return an obsolete
    # region-owned procedural crossing or loose bridge component.
    document["objects"] = []
    path.write_text(json.dumps(document), encoding="utf-8")
    snapshot = A.load_snapshot(path, production=False)
    world = SimpleNamespace(
        roads=[{"id": "before", "width": 2, "points": [[1180, 1, 700], [1190, 1, 710]]},
               {"id": "road-a", "width": 99, "points": [[0, 0, 0], [1, 0, 1]]},
               {"id": "after", "width": 2, "points": [[1220, 1, 740], [1230, 1, 750]]}],
        x0=1000.0, z0=200.0, x=np.arange(1000, 1302, 2), z=np.arange(200, 802, 2))
    world.gx, world.gz = np.meshgrid(world.x, world.z)
    world.height = np.zeros_like(world.gx, dtype=float)
    world.ids = ["neighbour", "sunmane_steppe"]
    world.crossing_sites = [
        {"id": 6, "region": "neighbour"}, {"id": 7, "region": "sunmane_steppe"}]
    world.crossing_site_use = {6: 1, 7: 1}
    world.crossing_site_roads = {6: {"before"}, 7: {"road-a"}}

    report = A.replace_routes(world, snapshot)

    assert [road["id"] for road in world.roads] == ["before", "road-a", "after", "road-new"]
    assert world.roads[1]["width"] == 6.0
    assert world.roads[1]["widths"] == [4.0, 6.0]
    assert world.roads[1]["points"] == [[1198.0, 3.0, 718.0], [1202.0, 3.0, 722.0]]
    assert world.roads[-1]["points"] == [[1205.0, 3.0, 725.0], [1209.0, 3.0, 729.0]]
    assert report["removedProceduralRoutes"] == 1
    assert report["suppressedProceduralBridgeSiteIds"] == [7]
    assert [site["id"] for site in world.crossing_sites] == [6]
    assert world.crossing_site_use == {6: 1}
    assert np.isfinite(world.road_distance).any()
    import bridge_export as B
    world.authoring_snapshots = {"sunmane_steppe": snapshot}
    assert B._authored_crossing_claims(world) == {}
    assert B._suppresses_generated_authored_component(
        {"id": 501, "sites": []}, np.array([1, 1]), {1})


def test_visual_overlays_preserve_variable_widths_and_godot_uv_order():
    from types import SimpleNamespace
    import terrain_export as T
    from amberwood import gltf as G
    class Snapshot:
        translation = np.array([1.3,0.,2.7])
        terrain_width = terrain_height = 4
        @staticmethod
        def base_colors():
            return np.arange(4 * 4 * 4, dtype=np.uint8).reshape(4, 4, 4)
        document = {
            "terrain": {"origin":[-1.3,-2.7],"cellMetres":2.,
                        "previewUvMetresInverse":.24,
                        "baseSurface": {"preset": "Desert", "rotationDegrees": 0}},
            "groundRegions": [
                {"id":"low","enabled":True,"shape":"rectangle","matrix":[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
                 "size":[100,100],"blendWidth":0,"opacity":1,"priority":1,
                 "surface":{"preset":"Sand","rotationDegrees":0}},
                {"id":"high","enabled":True,"shape":"rectangle","matrix":[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
                 "size":[100,100],"blendWidth":0,"opacity":1,"priority":2,
                 "surface":{"preset":"Grass","rotationDegrees":0}}],
            "paths": [{"id": "variable-road", "kind": "road",
                       "surface": {"preset": "Worn earth", "rotationDegrees": 90,
                                   "materialMode":"road","roadOverrides":{
                                       "wornTint":[.9,.78,.59,1.],"roughnessMultiplier":1.,
                                       "normalStrength":.72,"edgeFeather":.16,"textureScale":1.}},
                       "points": [{"position": [0, 2, 0], "width": 4},
                                  {"position": [10, 3, 0], "width": 8}]}]}
        @staticmethod
        def continent_point(point):return np.asarray(point,float)+Snapshot.translation
    x=np.arange(0.,8.,2.);gx,gz=np.meshgrid(x,x)
    world=SimpleNamespace(authoring_snapshot=Snapshot(),ids=[A.SUNMANE],owner=np.zeros(gx.shape,int),
                          gx=gx,gz=gz,height=gx*.1,x=x,z=x,x0=0.,z0=0.)
    world.owner_at=lambda x,z:np.zeros(np.broadcast_arrays(x,z)[0].shape,dtype=int)
    world.height_at=lambda x,z:5.+.1*np.asarray(x)

    builder=G.GltfBuilder("test");overlays=T.authored_overlays(world,builder)
    base=next(item["mesh"] for item in overlays if item["name"]=="AuthoredGround_SunmaneBase")
    road=next(item["mesh"] for item in overlays if item["name"].startswith("Walk_variable-road"))

    assert base.colors is not None
    assert np.all((base.colors >= 0.) & (base.colors <= 1.))
    assert np.unique(np.rint(base.colors * 255).astype(np.uint8),axis=0).shape[0] > 1

    # Full authored widths become the exact endpoint edge lengths. The visible
    # ribbon samples the resolved terrain authority instead of intersecting it.
    first=np.unique(road.positions[np.isclose(road.positions[:,0],1.3)],axis=0)
    last=np.unique(road.positions[np.isclose(road.positions[:,0],11.3)],axis=0)
    assert np.ptp(first[:,2]) == pytest.approx(4.)
    assert np.ptp(last[:,2]) == pytest.approx(8.)
    assert len(first)==len(last)==7
    assert first[:,1].tolist() == pytest.approx([5.185]*7)
    assert last[:,1].tolist() == pytest.approx([6.185]*7)
    first_uv=np.unique(road.uvs[np.isclose(road.positions[:,0],1.3)],axis=0)
    assert max(np.linalg.norm(a-b) for a in first_uv for b in first_uv)==pytest.approx(4.)
    first_alpha=road.colors[np.isclose(road.positions[:,0],1.3),3]
    assert np.unique(first_alpha).tolist()==pytest.approx([0.,1.])
    road_material=next(value for value in builder._materials if value["name"]=="authored_variable-road")
    assert road_material["pbrMetallicRoughness"]["baseColorFactor"]==pytest.approx(
        A.gltf_base_color([.9,.78,.59,1.]))
    assert road_material["pbrMetallicRoughness"]["roughnessFactor"]==1.
    assert road_material["normalTexture"]["scale"]==.72
    assert road_material["alphaMode"]=="BLEND"
    # At 90 degrees, Godot's R*(UV*density+offset) maps +U to +V.
    np.testing.assert_allclose(T._rotated_uv([[1.,0.]],{"rotationDegrees":90},1.),[[0.,1.]],atol=1e-8)
    np.testing.assert_allclose(T._rotated_uv([[1.,1.]],
        {"rotationDegrees":0,"pbr":{"uvOffset":[.2,.4,0]}},[2.,3.]),[[2.2,3.4]])
    base=next(item["mesh"] for item in overlays if item["name"].startswith("AuthoredGround_SunmaneBase"))
    np.testing.assert_allclose(base.uvs[0],
        (base.positions[0,[0,2]]-Snapshot.translation[[0,2]])*.24*.2)
    assert abs(base.normals[:,0]).max()>0.05
    low=next(item["mesh"] for item in overlays if item["name"].startswith("AuthoredGround_low"))
    high=next(item["mesh"] for item in overlays if item["name"].startswith("AuthoredGround_high"))
    assert high.positions[:,1].min()-low.positions[:,1].min()==pytest.approx(.0005)
    np.testing.assert_allclose(low.uvs[0],
        (low.positions[0,[0,2]]-Snapshot.translation[[0,2]])*.24*.2)
    assert np.isfinite(base.tangents()).all()
    assert np.isfinite(low.tangents()).all()
    image=next(entry for entry in builder._images if entry["name"]=="SunmaneBase_albedoTexture")
    view=builder._buffer_views[image["bufferView"]]
    embedded=bytes(builder._buffer[view["byteOffset"]:view["byteOffset"]+view["byteLength"]])
    assert hashlib.sha256(embedded).hexdigest()=="5d3d975e645bf4fd460f1022d0522c29b3dbc7b4e281bf0deb9559062fc9570a"
    assert A._PRESET_MATERIALS["Desert"]==(
        "desert",(0.90,0.82,0.68,1.0),1.0,0.0,0.50,0.20)

    river_surface={"preset":"Custom","rotationDegrees":0,"materialMode":"water","pbr":{
        "albedoColor":[.24,.54,.62,.9],"albedoTexture":None,"normalTexture":None,"ormTexture":None,
        "normalScale":1.,"roughness":.45,"metallic":0.,"uvScale":[1.,1.,1.],
        "uvOffset":[0.,0.,0.],"triplanar":False,"worldTriplanar":False}}
    material,_=T.authored_surface_material(builder,river_surface,"southern_river_water")
    river_material=next(value for value in builder._materials if value["name"]==material)
    river_pbr=river_material["pbrMetallicRoughness"]
    assert river_pbr["baseColorFactor"]==pytest.approx(A.gltf_base_color([.24,.54,.62,.9]))
    assert river_pbr["metallicFactor"]==0.
    assert river_pbr["roughnessFactor"]==.45
    assert river_material["alphaMode"]=="BLEND"


def test_godot_srgb_colours_become_linear_gltf_factors():
    assert A.gltf_base_color([.5,.5,.5,.25])==pytest.approx(
        [.21404114048223255,.21404114048223255,.21404114048223255,.25])


def test_authored_bridge_geometry_matches_preview_equation_and_clearance():
    import tempfile
    from types import SimpleNamespace
    import bridge_export as B
    import collision_export as C
    import scene_io as S
    from amberwood import gltf as G
    class Snapshot:
        document={"bridges":[{
            "id":"bridge-a","start":[-5,1,0],"end":[5,1,0],"width":4.,"arch":.35,
            "waterClearance":1.1,"collisionRole":"walk_surface","deckTextureRotationDegrees":0.,
            "deckSurface":{"preset":"Timber","rotationDegrees":0.},
            "supportSurface":{"preset":"Stone","rotationDegrees":0.}}]}
        @staticmethod
        def continent_point(point):return np.asarray(point,float)
    world=SimpleNamespace(authoring_snapshot=Snapshot(),ids=[A.SUNMANE],
        plan={"rivers":[{"id":"river","width":2.,"points":[[0,-10,1.5,2.],[0,10,1.5,2.]]}]})
    world.owner_at=lambda x,z:0
    world.height_at=lambda x,z:np.asarray(x)*0

    builder=G.GltfBuilder("test")
    parts,triangles,records=B._authored_bridge_geometry(world,builder)

    deck=parts[0][2];record=records[0]
    assert record["segments"] == 10
    assert record["uniformClearanceLift"] == pytest.approx(1.306)
    assert np.linalg.norm(deck.positions[0]-deck.positions[1]) == pytest.approx(4.)
    assert deck.positions[0,1] == pytest.approx(2.306)
    assert deck.positions[10,1] == pytest.approx(2.656)
    assert len(triangles[0]) == 20
    assert len(record["supports"]) == 1
    assert parts[0][0:2] == (A.SUNMANE,"Walk_AuthoredBridge_bridge-a_sunmane_steppe")
    assert parts[0][3] is True

    # The same named top strip consumed by the render export is classified as
    # walk geometry by collision export. Fascia and piers remain visual only.
    node=parts[0][1]
    builder.add_mesh(node,deck,with_tangents=False)
    builder.add_node(G.Node(node,mesh=node))
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/"authored-bridge.glb";builder.write_glb(str(path))
        document,body=S.GR.load(path)
    walk,structures,statistics=C._mesh_groups(document,body,{
        "navigation":{"surfaceNodePrefixes":["Terrain_","Walk_"]},
        "collision":{"nodeNames":[node]}})
    assert len(walk)==20
    assert structures==[]
    assert statistics["walkMeshes"]==1


def test_bridge_controls_cannot_disable_their_walk_collision(tmp_path,monkeypatch):
    path,document=fixture(tmp_path,monkeypatch)
    document["bridges"]=[{
        "id":"bridge-a","start":[-5,1,0],"end":[5,1,0],"width":4.,"arch":.35,
        "waterClearance":1.1,"collisionRole":"none","deckTextureRotationDegrees":0.,
        "deckSurface":{"preset":"Timber","rotationDegrees":0.},
        "supportSurface":{"preset":"Stone","rotationDegrees":0.}}]
    path.write_text(json.dumps(document),encoding="utf-8")

    with pytest.raises(A.AuthoringError,match="collisionRole must be walk_surface"):
        A.load_snapshot(path,production=False)


def test_normal_bake_performs_bounded_cold_import_before_snapshot(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import build_pipeline as P
    client=tmp_path/"client";project=client/"godot-client";project.mkdir(parents=True)
    snapshot=client/"eloria-assets/maps/nymara-regions/sunmane_steppe/authoring/continent-authoring.json"
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        if "--script" in command:
            snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_text("{}")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(P,"CLIENT",client);monkeypatch.setattr(P,"SUNMANE_SNAPSHOT",snapshot)
    monkeypatch.setattr(P,"find_godot",lambda explicit=None:"godot-test")
    monkeypatch.setattr(P.subprocess,"run",run)

    P.bake_sunmane()

    assert calls[0][0]==["godot-test","--headless","--editor","--path",str(project),"--quit"]
    assert calls[1][0][1:3]==["--headless","--path"]
    assert calls[0][1]["timeout"]==calls[1][1]["timeout"]==180


def test_normal_bake_fails_instead_of_using_stale_snapshot(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import build_pipeline as P
    client=tmp_path/"client";(client/"godot-client").mkdir(parents=True)
    stale=client/"continent-authoring.json";stale.write_text("stale")
    monkeypatch.setattr(P,"CLIENT",client);monkeypatch.setattr(P,"SUNMANE_SNAPSHOT",stale)
    monkeypatch.setattr(P,"find_godot",lambda explicit=None:"godot-test")
    monkeypatch.setattr(P.subprocess,"run",lambda command,**kwargs:SimpleNamespace(
        returncode=1 if "--script" in command else 0))

    with pytest.raises(RuntimeError,match="bake failed with exit code 1"):
        P.bake_sunmane()
    assert stale.read_text()=="stale"


def test_production_geometry_import_does_not_require_optional_preview_raster(tmp_path,monkeypatch):
    toolkit=HERE.parent/"_toolkit"
    if str(toolkit) not in sys.path:sys.path.insert(0,str(toolkit))
    from amberwood import render
    monkeypatch.setattr(render,"_lib",None)
    monkeypatch.setattr(render,"_LIB_PATH",str(tmp_path/"missing-libraster.so"))

    assert render.look_at([0,1,2],[0,0,0]).shape==(4,4)
    with pytest.raises(RuntimeError,match="offline preview rasterizer is unavailable"):
        render._library()


def test_legacy_object_authority_filters_destination_not_source():
    import object_edits as OE
    edits = OE.ObjectEdits({"version": 1, "vegetationAreas": [], "objects": [
        {"id": "from-sunmane", "action": "add",
         "source": "sunmane_steppe_Tree_WorldPlacement", "pivot": [0, 0, 0], "translate": [0, 0, 0]},
        {"id": "into-sunmane", "action": "add",
         "source": "amberwood_Tree_WorldPlacement", "pivot": [0, 0, 0], "translate": [0, 0, 0]},
        {"id": "old-move", "action": "transform",
         "root": "sunmane_steppe_Old_WorldPlacement", "translate": [1, 0, 0]},
    ]}, ["sunmane_steppe", "amberwood"])

    edits.exclude_authored_region("sunmane_steppe")

    # Source libraries remain available to neighbouring territories. Target
    # ownership is resolved later by add_copies and suppresses only additions
    # that would land inside the fully authored region.
    assert [entry[2]["id"] for entry in edits.copies] == ["from-sunmane", "into-sunmane"]
    assert edits.transforms == {}


def test_saved_object_y_is_never_runtime_regrounded():
    from types import SimpleNamespace
    import content as C
    value=object.__new__(C.Content)
    value.authored_regions={A.SUNMANE};value.attachment_order=();value.assembly_records={}
    value.bounds_by_name={}
    value.objects=[
        {"region":A.SUNMANE,"node":"saved","low":np.array([0.,1.,0.]),
         "high":np.array([1.,2.,1.]),"shift":np.zeros(3),"targetGround":0.},
        {"region":"neighbour","node":"legacy","low":np.array([2.,1.,2.]),
         "high":np.array([3.,2.,3.]),"shift":np.zeros(3),"targetGround":0.}]
    value.world=SimpleNamespace(height_at=lambda x,z:5.)

    value.reground()

    assert value.objects[0]["shift"].tolist()==[0.,0.,0.]
    assert value.objects[0]["low"].tolist()==[0.,1.,0.]
    assert value.objects[1]["shift"].tolist()==[0.,5.,0.]


def test_publication_keeps_authored_sunmane_spawns():
    from types import SimpleNamespace
    import export_contracts as E
    placement=SimpleNamespace(region=A.SUNMANE,content=SimpleNamespace(templates={A.SUNMANE:{}}),
        spec={"previousServerOrigin":[194,292],"tilePositions":{},"arrival":[1,1]},
        report={"regions":{A.SUNMANE:{}}},local_position=lambda tile:[0.,9.,0.])
    manifest={"spawnPoints":[
        {"id":"arrival-datum","default":False,"position":[0.,22.,0.]},
        {"id":"steppe-arrival","default":True,"position":[4.,23.,5.]}],
        "coordinateTransform":{},"navigation":{}}

    E.update_markers(placement,manifest)

    assert [value["id"] for value in manifest["spawnPoints"]]==["arrival-datum","steppe-arrival"]
    assert manifest["navigation"]["defaultSpawn"]=="steppe-arrival"
    assert manifest["coordinateTransform"]["walkingHeight"]==23.


def test_material_override_clones_shared_mesh_and_matches_godot_uv_order(tmp_path, monkeypatch):
    from PIL import Image
    client = tmp_path / "client";texture = client / "godot-client/material.png"
    texture.parent.mkdir(parents=True)
    Image.new("RGBA", (1, 1), (255, 255, 255, 255)).save(texture)
    monkeypatch.setattr(A, "CLIENT", client)
    document = {"nodes": [{"name": "Root", "mesh": 0}, {"name": "Other", "mesh": 0}],
                "meshes": [{"primitives": [{"attributes": {}}]}], "materials": [],
                "bufferViews": [], "images": [], "textures": [], "samplers": [],
                "buffers": [{"byteLength": 0}]}
    surface = {"preset": "Custom", "rotationDegrees": 90, "materialMode": "surface",
               "pbr": {"albedoColor": [1, 1, 1, 1],
                       "albedoTexture": "godot-client/material.png", "normalTexture": None,
                       "ormTexture": None, "normalScale": 1, "roughness": 1, "metallic": 0,
                       "uvScale": [3, 4, 1], "uvOffset": [1, 2, 0],
                       "triplanar": False, "worldTriplanar": False}}

    result, _ = A._apply_material_overrides(
        document, b"", 0, [{"meshNodePath": ".", "surfaceIndex": 0, "surface": surface}])

    assert document["nodes"][0]["mesh"] == document["nodes"][1]["mesh"] == 0
    assert result["nodes"][1]["mesh"] == 0
    assert result["nodes"][0]["mesh"] == 1
    material = result["materials"][0]
    transform = material["pbrMetallicRoughness"]["baseColorTexture"]["extensions"]["KHR_texture_transform"]
    assert transform["rotation"] == pytest.approx(np.pi / 2)
    assert transform["scale"] == [3.0, 4.0]
    assert transform["offset"] == pytest.approx([-2.0, 1.0])

    preset_override={"preset":"Grass","rotationDegrees":0,"materialMode":"surface",
                     "pbrOverrides":dict(surface["pbr"],albedoColor=[.24,.54,.62,.9],
                                         roughness=.45,metallic=0)}
    A._validate_surface(preset_override,{"godot-client/material.png":digest(texture)},"surface")
    overridden,_=A._apply_material_overrides(
        document,b"",0,[{"meshNodePath":".","surfaceIndex":0,"surface":preset_override}])
    material=overridden["materials"][0]
    assert material["pbrMetallicRoughness"]["baseColorFactor"]==pytest.approx(
        A.gltf_base_color([.24,.54,.62,.9]))
    assert material["pbrMetallicRoughness"]["roughnessFactor"]==.45
    assert material["alphaMode"]=="BLEND"


@pytest.mark.parametrize("child_name", ["Landmark_BridgeWatch", "OrdinaryChild"])
def test_material_override_resolves_relative_nested_mesh_without_changing_geometry(child_name):
    document = {
        "nodes": [
            {"name": child_name, "children": [1], "translation": [1, 2, 3]},
            {"name": "Landmark_BridgeWatch__pale_ashlar", "mesh": 0, "scale": [2, 3, 4]},
            {"name": "OtherInstance", "mesh": 0, "translation": [5, 6, 7]},
            {"name": "Unrelated", "children": [2]},
            {"name": "Landmark_BridgeWatch", "children": [0, 3], "translation": [8, 9, 10]},
        ],
        "scenes": [{"nodes": [4]}], "scene": 0,
        "meshes": [{"primitives": [
            {"attributes": {"POSITION": 0}, "material": 0},
            {"attributes": {"POSITION": 0}, "material": 1},
        ]}],
        "materials": [{"name": "OriginalStone"}, {"name": "OriginalRoof"}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 1, "type": "VEC3"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 12}],
        "buffers": [{"byteLength": 12}],
    }
    original = copy.deepcopy(document)
    binary = bytes(range(12))
    surface = {"preset": "Custom", "pbr": {
        "albedoColor": [.4, .5, .6, 1], "roughness": .8, "metallic": 0,
        "normalScale": 1, "uvScale": [1, 1, 1], "uvOffset": [0, 0, 0],
    }}
    result, body = A._apply_material_overrides(document, binary, 4, [{
        "meshNodePath": f"{child_name}/Landmark_BridgeWatch__pale_ashlar",
        "surfaceIndex": 1, "surface": surface,
    }])

    assert document == original
    assert body == binary
    target_mesh = result["nodes"][1]["mesh"]
    assert target_mesh != 0
    assert result["nodes"][2]["mesh"] == 0
    assert result["meshes"][0] == original["meshes"][0]
    assert result["materials"][:2] == original["materials"]
    assert result["meshes"][target_mesh]["primitives"][0] == original["meshes"][0]["primitives"][0]
    assert result["meshes"][target_mesh]["primitives"][1] == {
        "attributes": {"POSITION": 0}, "material": 2}
    assert result["materials"][2]["pbrMetallicRoughness"]["roughnessFactor"] == .8
    expected_nodes = copy.deepcopy(original["nodes"])
    expected_nodes[1]["mesh"] = target_mesh
    assert result["nodes"] == expected_nodes
    for field in ("scenes", "scene", "accessors", "bufferViews", "buffers"):
        assert result[field] == original[field]


@pytest.mark.parametrize("case", ["missing", "ambiguous", "surface_bounds"])
def test_material_override_rejects_invalid_relative_target(case):
    document = {"nodes": [
        {"name": "Root", "children": [1]},
        {"name": "Child", "mesh": 0},
        {"name": "Child", "mesh": 0},
    ], "meshes": [{"primitives": [{"attributes": {}}]}]}
    if case == "ambiguous":
        document["nodes"][0]["children"].append(2)
    path = "Missing" if case == "missing" else "Child"
    index = 1 if case == "surface_bounds" else 0
    original = copy.deepcopy(document)
    with pytest.raises(A.AuthoringError, match="does not identify one mesh node|has no surface"):
        A._apply_material_overrides(document, b"", 0, [{
            "meshNodePath": path, "surfaceIndex": index, "surface": {},
        }])
    assert document == original


def test_material_override_indexed_multiroot_preserves_source_graph_and_shared_mesh():
    document = {"nodes": [
        {"name": "Root", "children": [1], "translation": [1, 2, 3]},
        {"name": "Target", "mesh": 0, "scale": [2, 3, 4]},
        {"name": "OtherRoot", "mesh": 0, "translation": [4, 5, 6]},
    ], "scenes": [{"nodes": [0, 2]}], "scene": 0,
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
        "materials": [{"name": "Original"}],
        "accessors": [{"bufferView": 0}], "bufferViews": [{"buffer": 0, "byteLength": 4}],
        "buffers": [{"byteLength": 4}]}
    original = copy.deepcopy(document)
    surface = {"preset": "Custom", "pbr": {
        "albedoColor": [.4, .5, .6, 1], "roughness": .8, "metallic": 0,
        "normalScale": 1, "uvScale": [1, 1, 1], "uvOffset": [0, 0, 0]}}
    result, body = A._apply_material_overrides(document, b"abcd", [0, 2], [{
        "meshNodePath": "GodotRenamedRoot/Target", "bakedMeshNodeIndex": 1,
        "surfaceIndex": 0, "surface": surface}])
    assert document == original and body == b"abcd"
    expected = copy.deepcopy(original)
    expected["nodes"][1]["mesh"] = 1
    expected["meshes"].append({"primitives": [{"attributes": {"POSITION": 0}, "material": 1}]})
    expected["materials"].append(result["materials"][1])
    assert result == expected
    assert result["materials"][1]["pbrMetallicRoughness"]["roughnessFactor"] == .8


@pytest.mark.parametrize("binding", [{}, {"bakedMeshNodeIndex": True},
    {"bakedMeshNodeIndex": -1}, {"bakedMeshNodeIndex": 1.0},
    {"bakedMeshNodeIndex": 3}, {"bakedMeshNodeIndex": 99}])
def test_material_override_multiroot_rejects_missing_invalid_or_unreachable_binding(binding):
    document = {"nodes": [{"children": [1]}, {"mesh": 0}, {}, {"mesh": 0}],
                "meshes": [{"primitives": [{"attributes": {}}]}]}
    override = {"meshNodePath": "irrelevant", "surfaceIndex": 0, "surface": {}, **binding}
    with pytest.raises(A.AuthoringError, match="bakedMeshNodeIndex"):
        A._apply_material_overrides(document, b"", [0, 2], [override])


@pytest.mark.parametrize("index", [True, -1, 1.0, "1"])
def test_material_override_snapshot_rejects_noninteger_binding(tmp_path, monkeypatch, index):
    path, document = fixture(tmp_path, monkeypatch)
    document["objects"][0]["materialOverrides"] = [{
        "meshNodePath": ".", "surfaceIndex": 0, "bakedMeshNodeIndex": index, "surface": {}}]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(A.AuthoringError, match="bakedMeshNodeIndex must be a non-negative integer"):
        A.load_snapshot(path, production=False)


def test_real_godot_saved_edit_reaches_terrain_collision_routes_objects_and_gameplay(tmp_path):
    from types import SimpleNamespace
    import collision_export as collision
    artifacts = A.CLIENT / "godot-client/test-artifacts/sunmane-edit-regression"
    recorded = json.loads((artifacts / "before/continent-authoring.json").read_text(encoding="utf-8"))
    scene = A.CLIENT / recorded["sources"]["scene"]["path"]
    if A.sha256(scene) != recorded["sources"]["scene"]["sha256"]:
        pytest.skip("saved-edit artifacts await regeneration from the finalized production scene")
    before = A.load_snapshot(artifacts / "before/continent-authoring.json")
    after = A.load_snapshot(artifacts / "after/continent-authoring.json")

    owner = np.ones((397, 397), dtype=np.int16);owner[5:-5, 5:-5] = 0
    def world(snapshot):
        value = SimpleNamespace(x0=1006.0, z0=220.0,
                                x=np.arange(1006, 1800, 2), z=np.arange(220, 1014, 2),
                                height=np.zeros((397, 397), float), owner=owner.copy(),
                                ids=["sunmane_steppe", "neighbour"], cell=2.0)
        A.apply_terrain(value, snapshot)
        return value
    first, second = world(before), world(after)
    changed = first.height != second.height
    from scipy.ndimage import binary_dilation
    authority = binary_dilation(owner == 0, structure=np.ones((3, 3), bool))
    assert changed.any() and not changed[~authority].any()
    rows, columns = np.nonzero(changed & ~np.eye(397, dtype=bool))
    sample = np.arange(min(len(rows), 2000))
    x = first.x[columns[sample]] + .5;z = first.z[rows[sample]] + .5
    assert np.any(np.abs(collision.terrain_grade(first, x, z) -
                         collision.terrain_grade(second, x, z)) > 1e-6)

    roads = {entry["id"]: entry for entry in after.document["paths"]}
    assert roads["mirrorhold--sunmane_steppe-sunmane_steppe"]["points"][0]["width"] == 9.75
    assert roads["mirrorhold--sunmane_steppe-sunmane_steppe"]["surface"]["rotationDegrees"] == 23.0
    assert roads["southern_river"]["points"][0]["width"] == 12.0
    ground_surface=after.document["groundRegions"][0]["surface"]
    assert {key:ground_surface[key] for key in ("materialMode","preset","rotationDegrees")} == {
        "materialMode": "surface", "preset": "Sand", "rotationDegrees": 37.0}
    assert ground_surface["pbrOverrides"]["triplanar"] is False
    assert ground_surface["pbrOverrides"]["worldTriplanar"] is False
    assert after.document["bridges"][0]["width"] == 5.25

    products = A.build_retained_library(after, tmp_path / "library")
    metadata = json.loads((tmp_path / "library/library.json").read_text(encoding="utf-8"))
    placements = {entry["authoringId"]: entry for entry in metadata["placements"]}
    assert "Camp00_Cart" not in placements
    assert "Landmark_sunmane_cave_crystal_hollow-copy" in placements
    before_object=next(entry for entry in before.document["objects"]
                       if entry["id"]=="Landmark_sunmane_cave_crystal_hollow")
    before_position=np.asarray(before_object["matrix"],float).reshape(4,4,order="F")[:3,3]
    assert np.asarray(placements["Landmark_sunmane_cave_crystal_hollow"]["position"])-before_position == pytest.approx(
        [4.,.5,-3.])
    assert products["library.glb"] == A.sha256(tmp_path / "library/library.glb")

    gameplay = A.authored_gameplay(after)
    before_gameplay=A.authored_gameplay(before)
    portal = next(entry for entry in gameplay["portals"] if entry["id"] == "cave-crystal_hollow")
    before_portal=next(entry for entry in before_gameplay["portals"]
                       if entry["id"]=="cave-crystal_hollow")
    assert portal["destinationMap"] == "sunmane_wind_caves"
    assert portal["assetId"] == "Landmark_sunmane_cave_crystal_hollow"
    assert np.asarray(portal["position"])-before_portal["position"] == pytest.approx([4.,.5,-3.])
    assert portal["serverTile"] == A.server_tile(portal["position"])


@pytest.mark.parametrize("with_material_override", [False, True])
def test_retained_library_moves_every_root_in_a_grouped_scene(tmp_path, monkeypatch, with_material_override):
    from types import SimpleNamespace
    sys.path.insert(0, str(HERE.parent / "_toolkit"))
    from amberwood import gltf as G, mesh as M
    from content import Content
    import scene_io as S

    path, document = fixture(tmp_path, monkeypatch)
    asset = A.CLIENT / document["objects"][0]["bakedSource"]["path"]
    builder = G.GltfBuilder("grouped retained fixture")
    builder.add_material(G.Material("plain"))
    mesh = M.Mesh(
        positions=np.asarray([[0., 0., 0.], [1., 0., 0.], [0., 0., 1.]]),
        normals=np.tile([0., 1., 0.], (3, 1)),
        uvs=np.asarray([[0., 0.], [1., 0.], [0., 1.]]),
        indices=np.asarray([0, 1, 2]), material="plain")
    builder.add_mesh("triangle", mesh, with_tangents=False)
    builder.add_node(G.Node("visual-root", mesh="triangle", translation=(1., 0., 0.)))
    builder.add_node(G.Node("walk-root", mesh="triangle", translation=(0., 0., 2.)))
    builder.write_glb(str(asset))

    digest = A.sha256(asset)
    dependency = next(entry for entry in document["sources"]["dependencies"]
                      if entry["path"] == document["objects"][0]["bakedSource"]["path"])
    dependency["sha256"] = digest
    entry = document["objects"][0]
    entry["bakedSource"]["sha256"] = digest
    entry["sourceNode"] = entry["bakedSource"]["sourceNode"] = "."
    entry["nodeName"] = "GroupedObject"
    entry["matrix"][12:15] = [10., 1., 20.]
    if with_material_override:
        entry["materialOverrides"] = [{"meshNodePath": "visual-root", "bakedMeshNodeIndex": 0,
            "surfaceIndex": 0, "surface": {"preset": "Custom", "materialMode": "surface",
            "rotationDegrees": 0, "pbr": {"albedoColor": [.4, .5, .6, 1], "roughness": .8,
            "metallic": 0, "normalScale": 1, "uvScale": [1, 1, 1], "uvOffset": [0, 0, 0],
            "triplanar": False, "worldTriplanar": False}}}]
    path.write_text(json.dumps(document), encoding="utf-8")

    snapshot = A.load_snapshot(path, production=False)
    A.build_retained_library(snapshot, tmp_path / "library")
    output, body = S.GR.load(tmp_path / "library/library.glb")
    metadata = json.loads((tmp_path / "library/library.json").read_text(encoding="utf-8"))
    roots = output["scenes"][output.get("scene", 0)]["nodes"]
    assert len(roots) == 2
    mesh_nodes = [index for index, node in enumerate(output["nodes"])
                  if node.get("mesh") is not None]
    values = S.GR.triangles(output, body, mesh_nodes)
    centres = sorted(np.mean(triangle, axis=0).tolist() for triangle in values)
    assert np.asarray(centres) == pytest.approx(np.asarray(sorted([
        [11. + 1. / 3., 1., 20. + 1. / 3.],
        [10. + 1. / 3., 1., 22. + 1. / 3.],
    ])))
    assert output["nodes"][roots[0]]["name"] == "GroupedObject"
    assert output["nodes"][roots[1]]["name"].startswith("GroupedObject__companion_1_")
    assert metadata["placements"][0]["groupedNodes"] == [
        output["nodes"][roots[0]]["name"], output["nodes"][roots[1]]["name"]]

    content = Content.__new__(Content)
    content.authoring_snapshots = {"sunmane_steppe": snapshot}
    content.documents = {}; content.metadata = {}; content.transforms = {}
    content.source_centers = {}; content.scales = {}; content.objects = []
    content.mapping = {}; content.placement_by_name = {}; content.bounds_by_name = {}
    content.prototypes = {}; content.world = SimpleNamespace(height_at=lambda x, z: 2.)
    content.load_authored_region("sunmane_steppe", output, body, metadata)
    placed = content.objects[0]
    assert placed["indices"] == roots
    np.testing.assert_allclose(placed["low"], [1210., 1., 740.])
    np.testing.assert_allclose(placed["high"], [1212., 1., 743.])

    downstream = tmp_path / "downstream.glb"
    exporter = S.Exporter(downstream)
    exporter.add(output, body, placed["indices"],
                 transforms={index: placed["shift"] for index in placed["indices"]})
    exporter.write()
    final, final_body = S.GR.load(downstream)
    final_meshes = [index for index, node in enumerate(final["nodes"])
                    if node.get("mesh") is not None]
    final_triangles = S.GR.triangles(final, final_body, final_meshes)
    assert len(final_triangles) == 2
    final_centres = sorted(np.mean(triangle, axis=0).tolist() for triangle in final_triangles)
    np.testing.assert_allclose(final_centres, np.asarray(centres) + snapshot.translation)
