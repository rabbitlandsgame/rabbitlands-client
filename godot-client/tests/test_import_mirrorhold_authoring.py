from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
TOOLKIT = Path(__file__).resolve().parents[2] / \
    "eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0, str(TOOLKIT))
SPEC = importlib.util.spec_from_file_location(
    "import_mirrorhold_authoring", TOOLS / "import_mirrorhold_authoring.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_grouped_final_object_keeps_one_editable_transform_and_relative_roots():
    nodes = [{"name": f"Final_{index}", "mesh": index,
              "translation": [840.0 + index, 10.0, 650.0]}
             for index in range(169)]
    objects = []
    for index in range(168):
        roots = [index, 168] if index == 0 else [index]
        objects.append({
            "region": M.REGION_ID, "libraryRegion": M.REGION_ID,
            "node": f"Final_{index}", "index": index, "indices": roots,
            "shift": [2.0, 3.0, -4.0], "collides": index > 0,
            "walk": False, "source": {"kind": "landmark"},
        })
    content = SimpleNamespace(documents={M.REGION_ID: ({"nodes": nodes}, b"")})

    records, families = M.final_object_records(content, tuple(objects))

    grouped = next(record for record in records if record["id"] == "Final_0")
    assert len(records) == 168
    assert grouped["sourceRoots"] == [0, 168]
    assert np.allclose(grouped["matrix"][:3, 3], [2.0, 13.0, -4.0])
    assert np.allclose(grouped["relativeRootMatrices"][0], np.eye(4))
    assert np.allclose(grouped["relativeRootMatrices"][168][:3, 3], [168.0, 0.0, 0.0])
    assert grouped["metadata"]["groupedRootNames"] == ["Final_0", "Final_168"]
    assert len(families[grouped["family"]]) == 1


def test_paths_claim_exact_routes_and_dense_full_river(tmp_path):
    roads = {"roads": [{
        "id": identity, "width": 4.0 if "--" in identity else 1.65,
        "points": [[840.0, 80.0, 650.0], [842.0, 81.0, 654.0]],
    } for identity in M.OWNED_ROUTE_IDS]}
    controls = [[800.0 + index * 10.0, 600.0 + index * 5.0, 78.0 - index]
                for index in range(4)]
    plan = {"rivers": [{
        "id": M.RIVER_ID, "name": "Mirrorwater", "joins": "western_river",
        "width": 4.0, "valley_width": 65.0, "bank_height": 2.0,
        "depth": 1.2, "bank_shelf_width": 0.0, "cuts_relief": False,
        "points": controls,
    }]}

    paths, river = M.path_records(roads, plan, tmp_path, "res://fixture")

    assert len(paths) == 48
    assert [entry["id"] for entry in paths] == list(M.OWNED_ROUTE_IDS)
    assert {entry["properties"]["terrainConform"] for entry in paths} == {False}
    assert {entry["routingRole"] for entry in paths
            if entry["id"].startswith(("discovery-", "trail-"))} == {"decorative"}
    assert river["sourceControlPointCount"] == 4
    assert len(river["points"]) == 19
    assert river["points"][0] == [-40.0, 78.0, -50.0]
    assert river["width"] == 8.0
    assert river["properties"]["terrainConform"] is False
    assert river["properties"]["joins"] == "western_river"


def test_saved_terrain_material_uses_exact_paint_texture_and_global_uv_offset(tmp_path):
    M.write_terrain_surface(tmp_path / "ground.tres", "res://mirrorhold")
    text = (tmp_path / "ground.tres").read_text(encoding="utf-8")

    assert "continental-ground.png" in text
    assert "vertex_color_use_as_albedo = true" in text
    assert "roughness = 0.95" in text
    assert "uv1_offset = Vector3(0.8, 0.5, 0)" in text
    assert "uv1_triplanar" not in text


def test_published_bridge_pairs_are_grouped_under_stable_river_keys(tmp_path):
    nodes = []
    for _stable, names in sorted(M.PUBLISHED_ASSEMBLIES.items()):
        for name in names:
            child = len(nodes)
            nodes.append({"name": name, "mesh": child})
            nodes.append({
                "name": name + "_WorldPlacement",
                "children": [child], "translation": [0.0, 0.0, 0.0],
            })
    document = {"nodes": nodes}
    roads = {"crossingSites": [{
        "key": "mirror_outlet@16", "deckLevel": 160.45,
        "routeLandings": [[600.0, 300.0], [620.0, 304.0]],
    }]}

    class Exporter:
        def __init__(self, target, shared_images):
            self.target = target

        def add(self, *_args, **_kwargs):
            return None

        def write(self):
            self.target.parent.mkdir(parents=True, exist_ok=True)
            self.target.write_bytes(b"glb")
            return {"externalResources": {}}

    records, prototypes = M.bridge_records(
        document, b"", roads, tmp_path, "res://fixture",
        SimpleNamespace(Exporter=Exporter))

    assert len(records) == 3
    crossings = [entry for entry in records if "authoredCrossing" in entry["metadata"]]
    accesses = [entry for entry in records if "authoredAccessAssembly" in entry["metadata"]]
    assert {entry["metadata"]["authoredCrossing"]["id"] for entry in crossings} == \
        {"mirror_outlet@16"}
    assert len(accesses) == 2
    assert all(entry["collisionRole"] == "walk_surface" for entry in records)
    assert all(record["roots"] == 2 for record in prototypes.values())
    assert all(len(entry["metadata"]["authoredCrossing"]["localEndpoints"]) == 2
               for entry in crossings)


def test_sidecar_contract_is_full_grid_rgba8():
    assert M.GRID_SHAPE == (271, 271)
    assert M.COLOR_BYTES == 271 * 271 * 4
    assert M.PREVIEW_UV_DENSITY == 0.17
    assert np.allclose((M.TRANSLATION[[0, 2]] * M.PREVIEW_UV_DENSITY) % 1.0,
                       [0.8, 0.5])


def test_runtime_seed_count_is_certified_by_seed_not_forced_candidate_total():
    markers = [{
        "container": "Gameplay/NPCs", "kind": "npc_marker", "id": "guide",
        "position": [1.0, 2.0, 3.0], "runtimeBindings": [],
    }]
    seed = {
        "schema": "eloria-runtime-binding-seed-v1", "regionId": M.REGION_ID,
        "provenance": {
            "sourceReportSha256": "a" * 64,
            "profileFiles": [{
                "path": M.IMMUTABLE_PROFILE_PREFIX + "config/eloria/npcs.txt",
                "sha256": "b" * 64,
            }],
        },
        "counts": {"bindings": 1, "runtimePoints": 0},
        "bindings": [{
            "id": "npcs.txt:1:guide@1:2",
            "source": {"path": "config/eloria/npcs.txt", "line": 1,
                       "recordId": "guide", "oldTile": [1, 2]},
            "marker": {"section": "npcMarkers", "id": "guide"},
            "role": "npc", "roads": "marker", "targetOffset": [0, 0, 0],
            "aliases": [],
        }],
    }

    M.apply_runtime_seed(markers, seed)

    assert len(markers[0]["runtimeBindings"]) == 1
    assert markers[0]["runtimeBindings"][0]["id"] == "npcs.txt:1:guide@1:2"


def test_saved_mirrorhold_source_matches_the_certified_capture_contract():
    source = Path(__file__).resolve().parents[1] / \
        "world_authoring/regions/mirrorhold"
    provenance = json.loads((source / "migration-provenance.json").read_text())
    spec = json.loads((source / "region-authoring-spec.json").read_text())
    seed = json.loads((source / "runtime-bindings.seed.json").read_text())
    scene = (source / "mirrorhold.tscn").read_bytes()

    assert hashlib.sha256(scene).hexdigest() == provenance["sceneSha256"]
    assert provenance["counts"] == {
        "objects": 168, "paths": 48, "prototypeFamilies": 171,
        "publishedAssemblies": 3, "retiredSourcePlacements": 333,
        "riverControlPoints": 4, "riverCurvePoints": 19,
        "runtimeBindings": 139, "runtimePoints": 93,
        "savedAssetControls": 171, "visibleGameplay": 129,
    }
    assert seed["counts"] == {
        "bindings": 139, "runtimePoints": 93, "existingMarkerBindings": 46,
    }
    assert [binding["id"] for binding in seed["bindings"]
            if binding["marker"] ==
            {"section": "spawnPoints", "id": "continent-arrival"}] == \
        ["territories.txt:34:2@102:89"]
    assert {record["id"] for record in provenance["objects"]} >= {
        "published-mirror-mirror-outlet-16",
        "published-mirror-mirror-bank-ramp-quay",
        "published-mirror-mirror-bank-ramp-sanctuary",
    }
    assert spec["authority"]["ownedRouteIds"] == list(M.OWNED_ROUTE_IDS)
    assert spec["authority"]["requiredRouteIds"] == list(M.REQUIRED_ROUTE_IDS)
    assert spec["authority"]["ownedPlanFeatureIds"] == ["mirror_lake", M.RIVER_ID]
    assert spec["gameplay"] == {
        "runtimeBindingCount": 139, "runtimePointCount": 93,
        "existingMarkerBindingCount": 46,
    }
    assert (source / "base-heights.f32le").stat().st_size == M.GRID_BYTES
    assert (source / "base-colors.rgba8").stat().st_size == M.COLOR_BYTES
