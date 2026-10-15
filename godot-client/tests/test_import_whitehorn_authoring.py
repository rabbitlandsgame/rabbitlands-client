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
    "import_whitehorn_authoring", TOOLS / "import_whitehorn_authoring.py")
assert SPEC and SPEC.loader
W = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(W)


def test_grouped_final_object_keeps_one_editable_transform_and_relative_roots():
    nodes = [{"name": f"Final_{index}", "mesh": index,
              "translation": [550.0 + index, 10.0, 220.0]}
             for index in range(381)]
    objects = []
    for index in range(380):
        roots = [index, 380] if index == 0 else [index]
        objects.append({
            "region": W.REGION_ID, "libraryRegion": W.REGION_ID,
            "node": f"Final_{index}", "index": index, "indices": roots,
            "shift": [2.0, 3.0, -4.0], "collides": index > 0,
            "walk": False, "source": {"kind": "landmark"},
        })
    content = SimpleNamespace(documents={W.REGION_ID: ({"nodes": nodes}, b"")})

    records, families = W.final_object_records(content, tuple(objects))

    grouped = next(record for record in records if record["id"] == "Final_0")
    assert len(records) == 380
    assert grouped["sourceRoots"] == [0, 380]
    assert np.allclose(grouped["matrix"][:3, 3], [2.0, 13.0, -4.0])
    assert np.allclose(grouped["relativeRootMatrices"][0], np.eye(4))
    assert np.allclose(grouped["relativeRootMatrices"][380][:3, 3], [380.0, 0.0, 0.0])
    assert grouped["metadata"]["groupedRootNames"] == ["Final_0", "Final_380"]
    assert len(families[grouped["family"]]) == 1


def test_paths_claim_exact_routes_and_dense_full_river(tmp_path):
    roads = {"roads": [{
        "id": identity, "width": 4.0 if "--" in identity else 1.65,
        "points": [[550.0, 160.0, 220.0], [552.0, 161.0, 224.0]],
    } for identity in W.OWNED_ROUTE_IDS]}
    controls = [[484.0 + index, 173.0 + index, 191.8 - index]
                for index in range(45)]
    plan = {"rivers": [{
        "id": W.RIVER_ID, "name": "Hornwater", "joins": "amber_tributary",
        "width": 5.0, "valley_width": 30.0, "bank_height": 2.5,
        "depth": 1.5, "bank_shelf_width": 5.0, "cuts_relief": True,
        "points": controls,
    }]}

    paths, river = W.path_records(roads, plan, tmp_path, "res://fixture")

    assert len(paths) == 23
    assert [entry["id"] for entry in paths] == list(W.OWNED_ROUTE_IDS)
    assert {entry["properties"]["terrainConform"] for entry in paths} == {False}
    assert {entry["routingRole"] for entry in paths
            if entry["id"].startswith(("discovery-", "trail-"))} == {"decorative"}
    assert river["sourceControlPointCount"] == 45
    assert len(river["points"]) == 45 * 6 - 5
    assert river["points"][0] == [-66.0, 191.8, -47.0]
    assert river["width"] == 10.0
    assert river["properties"]["terrainConform"] is False
    assert river["properties"]["joins"] == "amber_tributary"


def test_saved_terrain_material_uses_exact_paint_texture_and_global_uv_offset(tmp_path):
    W.write_terrain_surface(tmp_path / "ground.tres", "res://whitehorn")
    text = (tmp_path / "ground.tres").read_text(encoding="utf-8")

    assert "continental-ground.png" in text
    assert "vertex_color_use_as_albedo = true" in text
    assert "roughness = 0.95" in text
    assert "uv1_offset = Vector3(0.5, 0.4, 0)" in text
    assert "uv1_triplanar" not in text


def test_published_bridge_pairs_are_grouped_under_stable_river_keys(tmp_path):
    nodes = []
    for stable, suffix in sorted(W.BRIDGE_UNIONS.items()):
        for prefix in ("Walk_ContinentalBridgeUnion_", "BridgeUnionTimberEdge_"):
            child = len(nodes)
            nodes.append({"name": f"{prefix}{suffix}_whitehorn_range", "mesh": child})
            nodes.append({
                "name": f"{prefix}{suffix}_whitehorn_range_WorldPlacement",
                "children": [child], "translation": [0.0, 0.0, 0.0],
            })
    document = {"nodes": nodes}
    roads = {"crossingSites": [{
        "key": stable, "deckLevel": 160.45,
        "routeLandings": [[600.0, 300.0], [620.0, 304.0]],
    } for stable in W.BRIDGE_UNIONS]}

    class Exporter:
        def __init__(self, target, shared_images):
            self.target = target

        def add(self, *_args, **_kwargs):
            return None

        def write(self):
            self.target.parent.mkdir(parents=True, exist_ok=True)
            self.target.write_bytes(b"glb")
            return {"externalResources": {}}

    records, prototypes = W.bridge_records(
        document, b"", roads, tmp_path, "res://fixture",
        SimpleNamespace(Exporter=Exporter))

    assert len(records) == 3
    assert {entry["metadata"]["authoredCrossing"]["id"] for entry in records} == \
        set(W.BRIDGE_UNIONS)
    assert all(entry["collisionRole"] == "walk_surface" for entry in records)
    assert all(record["roots"] == 2 for record in prototypes.values())
    assert all(len(entry["metadata"]["authoredCrossing"]["localEndpoints"]) == 2
               for entry in records)


def test_sidecar_contract_is_full_grid_rgba8():
    assert W.GRID_SHAPE == (350, 289)
    assert W.COLOR_BYTES == 350 * 289 * 4
    assert W.PREVIEW_UV_DENSITY == 0.17
    assert np.allclose((W.TRANSLATION[[0, 2]] * W.PREVIEW_UV_DENSITY) % 1.0,
                       [0.5, 0.4])


def test_runtime_seed_count_is_certified_by_seed_not_forced_candidate_total():
    markers = [{
        "container": "Gameplay/NPCs", "kind": "npc_marker", "id": "guide",
        "position": [1.0, 2.0, 3.0], "runtimeBindings": [],
    }]
    seed = {
        "schema": "eloria-runtime-binding-seed-v1", "regionId": W.REGION_ID,
        "provenance": {
            "sourceReportSha256": "a" * 64,
            "profileFiles": [{
                "path": W.IMMUTABLE_PROFILE_PREFIX + "config/eloria/npcs.txt",
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

    W.apply_runtime_seed(markers, seed)

    assert len(markers[0]["runtimeBindings"]) == 1
    assert markers[0]["runtimeBindings"][0]["id"] == "npcs.txt:1:guide@1:2"


def test_saved_whitehorn_source_matches_the_certified_capture_contract():
    source = Path(__file__).resolve().parents[1] / \
        "world_authoring/regions/whitehorn_range"
    provenance = json.loads((source / "migration-provenance.json").read_text())
    spec = json.loads((source / "region-authoring-spec.json").read_text())
    seed = json.loads((source / "runtime-bindings.seed.json").read_text())
    scene = (source / "whitehorn_range.tscn").read_bytes()

    assert hashlib.sha256(scene).hexdigest() == provenance["sceneSha256"]
    assert provenance["counts"] == {
        "objects": 380, "paths": 23, "prototypeFamilies": 383,
        "publishedBridgeAssemblies": 3, "retiredSourcePlacements": 517,
        "riverControlPoints": 45, "riverCurvePoints": 265,
        "runtimeBindings": 197, "runtimePoints": 67,
        "savedAssetControls": 383, "visibleGameplay": 125,
    }
    assert seed["counts"] == {
        "bindings": 197, "runtimePoints": 67, "existingMarkerBindings": 125,
    }
    assert all(binding["marker"] !=
               {"section": "spawnPoints", "id": "continent-arrival"}
               for binding in seed["bindings"])
    assert {record["id"] for record in provenance["objects"]} >= {
        "Landmark_ice_cave",
        "published-bridge-horn-tributary-24",
        "published-bridge-horn-tributary-124",
        "published-bridge-horn-tributary-292",
    }
    assert all("MC009" not in record["id"] for record in provenance["objects"])
    assert spec["authority"]["ownedRouteIds"] == list(W.OWNED_ROUTE_IDS)
    assert spec["authority"]["ownedPlanFeatureIds"] == [W.RIVER_ID]
    assert spec["gameplay"] == {
        "runtimeBindingCount": 197, "runtimePointCount": 67,
        "existingMarkerBindingCount": 125,
    }
    assert (source / "base-heights.f32le").stat().st_size == W.GRID_BYTES
    assert (source / "base-colors.rgba8").stat().st_size == W.COLOR_BYTES
