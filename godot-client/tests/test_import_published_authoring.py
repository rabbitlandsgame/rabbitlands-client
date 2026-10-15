from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] /
                       "eloria-assets/maps/nymara-regions/_continent"))
spec = importlib.util.spec_from_file_location(
    "import_published_authoring", TOOLS / "import_published_authoring.py")
assert spec and spec.loader
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def setup_import(tmp_path: Path, monkeypatch, *, water=None):
    repo = TOOLS.parents[1]
    contract = SimpleNamespace(
        adapter="published-generic-v1", id="amberwood", label="Amberwood",
        continent_translation=(100.0, 0.0, 200.0), terrain_origin=(-10.0, -20.0),
        terrain_vertices=(4, 5), terrain_cell_metres=2.0,
        owned_route_ids=("amberwood--grey_moors-amberwood",),
        required_route_ids=("amberwood--grey_moors-amberwood",),
        owned_plan_feature_ids=("amber_lake",),
        server_origin=(10, 20), server_cells=(30, 40),
        collision_origin_metres=(-10.0, 20.0),
        runtime_binding_count=0, runtime_point_count=0,
        existing_marker_binding_count=0,
        snapshot_path=repo / "eloria-assets/maps/nymara-regions/amberwood/authoring/continent-authoring.json",
        scene_path=repo / "godot-client/world_authoring/regions/amberwood/amberwood.tscn",
    )
    import authoring_catalog
    monkeypatch.setattr(authoring_catalog, "load_region_spec", lambda *a, **k: contract)
    entry = {"id": "amber-lake", "kind": "lake", "planFeatureId": "amber_lake",
             "localCenter": [5.0, 7.0, 8.0], "radii": [9.0, 4.0],
             "displayName": "Amber Lake", "baselinePlanDepth": 2.0}
    bootstrap = {"schema": "eloria-published-region-bootstrap-v1",
                 "objectCount": 0,
                 "objectIdsSha256": hashlib.sha256(b"[]").hexdigest(),
                 "baselineProofSha256": "0" * 64,
                 "visibleGameplayCount": 0, "assemblies": [],
                 "water": [entry] if water is None else water,
                 "bakedTerrainFeatures": [],
                 "previewUvMetresInverse": 0.17}
    path = tmp_path / "region-authoring-spec.json"
    path.write_text(json.dumps({"bootstrap": bootstrap}), encoding="utf-8")
    return path


def test_generic_bootstrap_claims_water_and_renders_declared_region(tmp_path, monkeypatch):
    path = setup_import(tmp_path, monkeypatch)
    M.configure(path)
    roads = {"roads": [{"id": M.OWNED_ROUTE_IDS[0], "width": 3.0,
                       "points": [[100.0, 7.0, 200.0], [102.0, 7.0, 200.0]]}]}
    plan = {"lakes": [{"id": "amber_lake", "name": "Amber Lake",
                       "center": [105.0, 208.0], "radii": [9.0, 4.0],
                       "level": 7.0, "depth": 2.0}]}
    paths, waters = M.path_records(roads, plan, tmp_path, "res://amberwood")
    assert len(paths) == len(waters) == 1
    assert paths[0]["routingRole"] == "required"
    assert waters[0]["planFeatureId"] == "amber_lake"
    manifest = {"continentGeography": {"ownershipPolygon": [[0, 0], [1, 0], [0, 1]]},
                "streamingBorders": []}
    M.write_scene(tmp_path, manifest, [], {}, paths, waters, [], "res://amberwood",
                  "res://amberwood/runtime-bindings.seed.json", "0" * 64)
    scene = (tmp_path / "amberwood.tscn").read_text(encoding="utf-8")
    assert 'region_id = "amberwood"' in scene
    assert 'replaces_plan_feature_id = "amber_lake"' in scene
    assert "Vector2i(30, 40)" in scene
    assert "Mirrorhold" not in scene


def test_generic_bootstrap_rejects_unclaimed_water(tmp_path, monkeypatch):
    path = setup_import(tmp_path, monkeypatch, water=[])
    with pytest.raises(ValueError, match="exactly cover owned plan features"):
        M.configure(path)


def test_new_stable_lake_id_binds_exact_unnamed_source_plan_record(tmp_path, monkeypatch):
    entry = {"id": "moor_headwater_tarn", "kind": "lake",
             "planFeatureId": "amber_lake", "sourceName": "Headwater Tarn",
             "localCenter": [5.0, 7.0, 8.0], "radii": [9.0, 4.0],
             "displayName": "Headwater Tarn", "baselinePlanDepth": 2.0}
    M.configure(setup_import(tmp_path, monkeypatch, water=[entry]))
    source = {"name": "Headwater Tarn", "center": [105.0, 208.0],
              "radii": [9.0, 4.0], "level": 7.0, "depth": 2.0}
    _, waters = M.path_records({"roads": [{"id": M.OWNED_ROUTE_IDS[0],
        "width": 3.0, "points": [[100., 7., 200.], [102., 7., 200.]]}]},
        {"lakes": [source]}, tmp_path, "res://amberwood")
    assert waters[0]["id"] == "moor_headwater_tarn"
    with pytest.raises(ValueError, match="differs from published plan"):
        M.path_records({"roads": [{"id": M.OWNED_ROUTE_IDS[0],
            "width": 3.0, "points": [[100., 7., 200.], [102., 7., 200.]]}]},
            {"lakes": [dict(source, depth=3.0)]}, tmp_path, "res://amberwood")


def test_generic_assembly_support_roots_allow_exact_group_and_single_root(tmp_path, monkeypatch):
    path = setup_import(tmp_path, monkeypatch)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["bootstrap"]["assemblies"] = [
        {"id": "amber-ramp", "kind": "access", "walkNode": "Walk_Amber_RootRamp",
         "supportNodes": ["Amber_RootRamp_Skirt", "Amber_RootRamp_Posts",
                          "Amber_RootRamp_Rails"]},
        {"id": "root-hatch", "kind": "access", "walkNode": "Motherroot_RootHatch",
         "supportNodes": []},
    ]
    path.write_text(json.dumps(document), encoding="utf-8")
    M.configure(path)
    assert set(M.PUBLISHED_ASSEMBLIES) == {"amber-ramp", "root-hatch"}
    document["bootstrap"]["assemblies"][0]["supportNodes"].append(
        "Amber_RootRamp_Rails")
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid assembly support roots"):
        M.configure(path)


def test_generic_grid_must_equal_final_composed_height_samples(tmp_path, monkeypatch):
    M.configure(setup_import(tmp_path, monkeypatch))
    x = np.arange(90., 98., 2.)
    z = np.arange(180., 190., 2.)
    heights = np.arange(20, dtype="<f4").reshape(5, 4)
    world = SimpleNamespace(x=x, z=z, height=heights.astype(float))
    grid = tmp_path / "heights.f32le"
    grid.write_bytes(heights.tobytes())
    M.validate_saved_grid(world, grid)
    heights[2, 1] += 1
    grid.write_bytes(heights.tobytes())
    with pytest.raises(ValueError, match="1 saved height vertices differ"):
        M.validate_saved_grid(world, grid)


def test_runtime_report_role_identity_is_checked(tmp_path, monkeypatch):
    M.configure(setup_import(tmp_path, monkeypatch))
    M.CONTRACT.existing_marker_binding_count = 1
    report = {"schema": "eloria-region-runtime-binding-inventory-v1",
              "regionId": "amberwood", "sources": [],
              "counts": {"bindings": 1, "existingMarkerBindings": 1,
                         "runtimePoints": 0},
              "bindings": [{"id": "one", "source": {"path": "config/eloria/maps.txt",
                             "line": 1, "oldTile": [2, 3], "recordId": "door"},
                             "marker": {"section": "portals", "id": "door"},
                             "role": "door", "roads": "entrance",
                             "targetOffset": [0., 0., 0.]}]}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    seed = {"provenance": {"sourceReportSha256": M.sha256(path),
                           "profileFiles": []},
            "bindings": [dict(report["bindings"][0])]}
    M.validate_runtime_report(seed, path)
    seed["bindings"][0]["role"] = "return"
    with pytest.raises(ValueError, match="identities/roles differ"):
        M.validate_runtime_report(seed, path)


def test_reviewed_proof_binds_actual_pickle_bytes(tmp_path, monkeypatch):
    spec_path = setup_import(tmp_path, monkeypatch)
    names = ("composed", "composition", "exportLedger", "publishedMaster",
             "roads", "plan", "crossingReport", "ferryFit",
             "sourceWorld", "sourceManifest",
             "resolvedHeights", "runtimeBindings", "runtimeReport")
    paths = {}
    for name in names:
        path = tmp_path / name
        path.write_bytes(name.encode())
        paths[name] = path
    proof = {"schema": "eloria-published-baseline-proof-v1",
             "publishedClientHead": "f837588815f165bc5d62e40650d56fc90c9cafc3",
             "publishedServerHead": "610af2ff24c67f815a957e868023484f0bb9da40",
             "inputs": {name: M.sha256(paths[name]) for name in names[:8]},
             "regions": {"amberwood": {
                 "inputs": {name: M.sha256(paths[name]) for name in names[8:]},
                 "assemblyIds": [], "assemblyRoots": {},
                 "bakedTerrainFeatureIds": []}}}
    proof_path = tmp_path / "baseline-proof.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    source = json.loads(spec_path.read_text(encoding="utf-8"))
    source["bootstrap"]["baselineProofSha256"] = M.sha256(proof_path)
    spec_path.write_text(json.dumps(source), encoding="utf-8")
    M.configure(spec_path)
    args = SimpleNamespace(
        baseline_proof=proof_path, composed=paths['composed'],
        composition=paths['composition'], export_ledger=paths['exportLedger'],
        published_master=paths['publishedMaster'], roads=paths['roads'],
        plan=paths['plan'], crossing_report=paths['crossingReport'],
        ferry_fit=paths['ferryFit'],
        source_world=paths['sourceWorld'],
        source_manifest=paths['sourceManifest'],
        resolved_heights=paths['resolvedHeights'],
        runtime_bindings=paths['runtimeBindings'],
        runtime_report=paths['runtimeReport'])
    assert M.verify_baseline_proof(args)["assemblyIds"] == []
    paths["composed"].write_bytes(b"altered pickle")
    with pytest.raises(ValueError, match="differs from the reviewed baseline proof"):
        M.verify_baseline_proof(args)
