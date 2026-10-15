"""Recorded dynamic section ownership, shared vertices, mirrored patches and external frozen crops.

sw_isle, tollholms and gull_skerries (owner decisions D2a-D2c) share one conditioned base: sw_isle's terrain grid
covers the whole group and the other two are byte crops of it, so the vertices two neighbours share are bit-identical.
These tests run godot-client/tools/continent_v2_territories.py on the committed territories, and show that each
check catches the fault it is there for.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot-client" / "tools"))
import continent_v2_territories as T  # noqa: E402


@pytest.fixture(scope="module")
def territories():
    return T.load_territories()


@pytest.fixture(scope="module")
def lattice(territories):
    return T.Lattice.of(territories)


def by_id(territories, identity):
    return next(t for t in territories if t.id == identity)


def replaced(territories, identity, **changes):
    return [dataclasses.replace(t, **changes) if t.id == identity else t for t in territories]


def vertex_index(territory, x, z):
    column, row = (x - territory.first_vertex[0]) / T.CELL, (z - territory.first_vertex[1]) / T.CELL
    assert column == int(column) and row == int(row)
    return int(row), int(column)


def test_the_catalog_lists_recorded_partition(territories):
    recorded = T._json(ROOT / "eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/sections_spec.json")
    sections = recorded["sections"]
    assert [t.id for t in territories] == [s["mapId"] for s in sorted(sections,key=lambda s:s["label"])]
    assert len(territories) == 15
    assert not set(recorded["retiredMapIds"]) & {t.id for t in territories}
    for t in territories:
        section=next(s for s in sections if s["mapId"]==t.id)
        assert t.polygons == section["ownershipPolygons"]


def test_scene_frames_agree_with_manifests_and_specs(territories):
    problems,report=T.check_frames(territories)
    assert problems == []
    for t in territories:
        assert all(type(v) is int and v%6==0 and v<=2048 for v in t.spec["server"]["cells"])
        assert all(float(v).is_integer() for v in t.translation)
    assert len(by_id(territories,"ravenhead").polygons)==2


def test_all_new_bases_are_byte_crops_of_frozen_external_group(territories):
    problems,report=T.check_crops(territories)
    assert problems==[] and set(report)=={t.id for t in territories}
    assert all(e=={"parent":"isles-group-terrain","heights":True,"colors":True,"frame":True} for e in report.values())


def test_external_crop_hash_grid_and_bounds_faults_are_caught(territories):
    import copy
    t=territories[0]
    for kind in ("hash","grid","bounds"):
        provenance=copy.deepcopy(t.provenance)
        if kind=="hash": provenance["crop"]["parentFiles"]["heights"]["sha256"]="0"*64
        elif kind=="grid": provenance["crop"]["parentGrid"]["cellMetres"]=3
        else: provenance["crop"]["col0"]=-1
        problems,_=T.check_crops([dataclasses.replace(t,provenance=provenance)])
        assert problems,kind
    heights=t.heights.copy(); heights[0,0]+=1
    assert T.check_crops([dataclasses.replace(t,heights=heights)])[0]


def test_ownership_polygons_do_not_overlap_and_own_every_island(territories,lattice):
    problems,report=T.check_ownership(territories,lattice)
    assert problems==[]
    assert not any(report["overlappingCells"].values())
    assert report["unownedIslandLandM2"]==0 and report["islandLandM2"]>2_000_000
    recorded=T._json(ROOT/"eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/check_report.json")
    assert report["mainlandM2"]["owned"]==4*recorded["mainlandVerticesOwned"]


def test_shared_border_vertices_are_byte_equal(territories,lattice):
    problems,report=T.check_seams(territories,lattice)
    assert problems==[]
    for entry in report.values():
        if entry["sharedVertices"]:
            assert entry["baseDifferences"]==0 and entry["waterNearShared"]==[]
            assert all(value==0 for key,value in entry.items() if key.startswith("sculptedShared_"))
    assert report["greenlight|spindle_hill"]["mirroredPatches"]==["seam-mole-knob"]
    assert T.patches(by_id(territories,"ravenhead"))[0]["id"]=="seam-mole-pier"
    assert sum(len(T.patches(t)) for t in territories)==3


def shared_pair(territories,lattice):
    a=by_id(territories,"greenlight"); b=by_id(territories,"spindle_hill")
    mask=T.authority(a,lattice)&T.authority(b,lattice)&T._covered(a,lattice)&T._covered(b,lattice)
    row,col=np.argwhere(mask)[0]; x,z=lattice.xz()
    return a,b,float(x[col]),float(z[row])


def test_a_changed_shared_vertex_is_caught(territories,lattice):
    a,b,x,z=shared_pair(territories,lattice); heights=b.heights.copy(); row,col=vertex_index(b,x,z)
    heights[row,col]=np.nextafter(heights[row,col],np.float32(np.inf))
    problems,_=T.check_seams([a,dataclasses.replace(b,heights=heights)],lattice)
    assert any("shared vertices differ in the base" in p for p in problems)


def test_a_sculpted_shared_vertex_is_caught(territories,lattice,monkeypatch):
    a,b,x,z=shared_pair(territories,lattice); original=T.sculpt_deltas
    def sculpted(t):
        values,problems=original(t)
        if t.id==b.id:
            values=values.copy(); values[vertex_index(t,x,z)]=0.25
        return values,problems
    monkeypatch.setattr(T,"sculpt_deltas",sculpted)
    assert any("sculpts 1 shared vertices" in p for p in T.check_seams([a,b],lattice)[0])


def test_unmirrored_and_moved_knob_are_caught(territories,lattice):
    a,b,_,_=shared_pair(territories,lattice)
    key=next(k for k,v in b.scene.nodes.items() if v.properties.get("patch_id")=='"seam-mole-knob"')
    missing=dataclasses.replace(b.scene,nodes={k:v for k,v in b.scene.nodes.items() if k!=key})
    assert any("only greenlight declares" in p for p in T.check_seams([a,dataclasses.replace(b,scene=missing)],lattice)[0])
    patch=b.scene.nodes[key]; moved=dataclasses.replace(patch,properties=dict(patch.properties,size="Vector2(40, 12)"))
    changed=dataclasses.replace(b.scene,nodes=dict(b.scene.nodes,**{key:moved}))
    assert any("declared differently" in p for p in T.check_seams([a,dataclasses.replace(b,scene=changed)],lattice)[0])


def test_water_near_shared_vertices_is_caught(territories,lattice,monkeypatch):
    a,b,x,z=shared_pair(territories,lattice); original=T.water_features
    monkeypatch.setattr(T,"water_features",lambda t: original(t)+([{"kind":"river","path":"Rivers/test","xz":np.array([[x,z]]),"reach":1}] if t.id==b.id else []))
    assert any("river Rivers/test comes within" in p for p in T.check_seams([a,b],lattice)[0])


def test_missing_multipart_ring_and_overlapping_ownership_are_caught(territories,lattice):
    raven=by_id(territories,"ravenhead")
    problems,report=T.check_ownership(replaced(territories,raven.id,polygons=[raven.polygons[1]]),lattice)
    changed=replaced(territories,raven.id,polygons=[raven.polygons[1]])
    assert any("ownership sha" in p for p in T.check_frames(changed)[0])
    a,b,_,_=shared_pair(territories,lattice)
    changed=dataclasses.replace(b,polygons=a.polygons,polygon=a.polygon)
    assert any("overlap" in p for p in T.check_ownership([a,changed],lattice)[0])


def test_classify_counts_edges_as_owned_and_interiors_strictly():
    square=[[1,1],[5,1],[5,5],[1,5]]
    assert T.classify(np.array([3,1,5,0]),np.array([3,3,5,3]),square).tolist()==[1,2,2,0]
    assert T.polygons_sha([square])==T.polygon_sha(square)
    assert T.polygons_sha([square,square])!=T.polygon_sha(square)


def test_each_catalog_entry_names_its_published_package(territories):
    problems,report=T.check_published(territories)
    assert problems==[]
    for t in territories:
        assert report[t.id]["publishedManifestPath"]==f"res://../eloria-assets/maps/continent-v2/{t.id}/client/world.json"


def served_fixture(root, *, served_grid=True, status="continent-v2-client-preview", origin=(1023, 993),
                   publish=True, row=None):
    """A checkout holding one v2 catalog entry, its registry row and (when `publish`) its client package."""
    resource = "res://../eloria-assets/maps/continent-v2/isle/client/world.json"
    catalog = root / "godot-client" / "world_authoring" / "continent-v2" / "territories.json"
    registry = root / "godot-client" / "data" / "maps" / "registry.json"
    package = root / "eloria-assets" / "maps" / "continent-v2" / "isle" / "client" / "world.json"
    for path in (catalog, registry, package):
        path.parent.mkdir(parents=True, exist_ok=True)
    transform = {"serverOrigin": list(origin), "serverCells": [2046, 2046], "metresPerTile": 1.0,
                 "invertServerY": True}
    catalog.write_text(T.json.dumps({"schema": "eloria-map-authoring-territories-v1", "entries": [
        {"id": "isle", "label": "Isle", "manifestPath": "res://../eloria-assets/maps/continent-v2/isle/world.json",
         "publishedManifestPath": resource}]}), encoding="utf-8")
    registry.write_text(T.json.dumps({"maps": {"isle": {
        "manifest": resource, "status": status, "coordinateTransform": transform,
        "continentGeography": {"translation": [1418.0, 0.0, 7270.0]}, **(row or {})}}}), encoding="utf-8")
    if publish:
        collision = {"cellMetres": 0.5}
        if served_grid:
            collision["servedGrid"] = {"binary": "served-grid.escg.gz", "format": "ESCG-v2"}
        package.write_text(T.json.dumps({"coordinateTransform": transform, "collision": collision,
                                         "continentGeography": {"translation": [1418, 0, 7270]}}), encoding="utf-8")
    return catalog


def test_a_served_territorys_frame_is_frozen(tmp_path):
    same = {"isle": {"origin": [1023, 993], "cells": [2046, 2046], "translation": [1418.0, 0.0, 7270.0]}}
    # a client preview (no served grid, not served in the registry) may still move: D2b moved sw_isle by 30 tiles
    preview = served_fixture(tmp_path / "preview", served_grid=False)
    assert T.served_frames(preview) == {}
    assert T.served_frame_problems({"isle": dict(same["isle"], origin=[1023, 963])}, preview) == []
    # once the package ships a served grid, the frame it was exported in is frozen
    served = served_fixture(tmp_path / "served")
    assert T.served_frames(served)["isle"]["origin"] == [1023, 993]
    assert T.served_frame_problems(same, served) == []
    moved = T.served_frame_problems({"isle": dict(same["isle"], origin=[1023, 963])}, served)
    assert len(moved) == 1 and "server origin would move from [1023, 993] to [1023, 963]" in moved[0]
    assert "position migration" in moved[0]
    resized = T.served_frame_problems({"isle": dict(same["isle"], cells=[2040, 2040])}, served)
    shifted = T.served_frame_problems({"isle": dict(same["isle"], translation=[1418.0, 0.0, 7240.0])}, served)
    assert any("server cells" in p for p in resized) and any("continent translation" in p for p in shifted)
    assert any("has no frame here" in p for p in T.served_frame_problems({}, served))
    # the registry's served status counts too, even before the package is republished
    registered = served_fixture(tmp_path / "registered", served_grid=False, status=T.SERVED_STATUS, publish=False)
    assert "registry row is continent-v2-served" in T.served_frames(registered)["isle"]["why"]
    assert T.served_frame_problems({"isle": dict(same["isle"], origin=[1023, 963])}, registered)


def test_a_served_row_names_the_map_as_the_catalog_does(tmp_path):
    promoted = {"label": "Isle", "landscapeTransitions": True}
    good = served_fixture(tmp_path / "good", status=T.SERVED_STATUS, row=promoted)
    assert T.served_row_problems(good) == []
    # a client preview is not held to it: it may still wait for its server map, unlabelled
    preview = served_fixture(tmp_path / "preview", row={"requiresServerMap": "not published on the server yet"})
    assert T.served_row_problems(preview) == []
    renamed = served_fixture(tmp_path / "renamed", status=T.SERVED_STATUS, row=dict(promoted, label="Sw Isle"))
    assert ["isle: the served registry row's label 'Sw Isle' is not the catalog's 'Isle'"] ==         T.served_row_problems(renamed)
    unlabelled = served_fixture(tmp_path / "unlabelled", status=T.SERVED_STATUS, row={"landscapeTransitions": True})
    assert any("label None" in p for p in T.served_row_problems(unlabelled))
    walled = served_fixture(tmp_path / "walled", status=T.SERVED_STATUS, row=dict(promoted, landscapeTransitions=False))
    assert any("landscapeTransitions is False" in p for p in T.served_row_problems(walled))
    waiting = served_fixture(tmp_path / "waiting", status=T.SERVED_STATUS,
                             row=dict(promoted, requiresServerMap="2046x2046 server tiles"))
    assert any("still says it requires a server map" in p for p in T.served_row_problems(waiting))


def test_served_packages_from_another_export_run_are_caught(tmp_path):
    catalog = served_fixture(tmp_path / "run")
    package = tmp_path / "run" / "eloria-assets" / "maps" / "continent-v2" / "isle" / "client" / "world.json"
    manifest = T.json.loads(package.read_text(encoding="utf-8"))
    own = {"snapshotSha256": "a" * 64, "servedGridSha256": "b" * 64}
    manifest["collision"].update(sourceSnapshotSha256=own["snapshotSha256"], groupExport={"maps": {"isle": own}})
    manifest["collision"]["servedGrid"]["sha256"] = own["servedGridSha256"]
    package.write_text(T.json.dumps(manifest), encoding="utf-8")
    assert T.served_group_problems(catalog) == []
    manifest["collision"]["groupExport"]["maps"]["isle"]["servedGridSha256"] = "c" * 64
    package.write_text(T.json.dumps(manifest), encoding="utf-8")
    assert ["another export run" in p for p in T.served_group_problems(catalog)] == [True]
    # a preview without a served grid is not held to it
    assert T.served_group_problems(served_fixture(tmp_path / "preview", served_grid=False)) == []


def test_the_committed_frames_are_not_moved(territories):
    stubs = {t.id: {"origin": t.manifest["server"]["origin"], "cells": t.manifest["server"]["cells"],
                    "translation": list(t.translation)} for t in territories}
    assert T.served_frame_problems(stubs) == []


def test_prospective_entries_preserve_served_new_ids(tmp_path):
    catalog=served_fixture(tmp_path)
    entries=T._json(catalog)["entries"]
    assert T.served_frame_problems({},catalog,entries)
    assert T.served_frames(catalog,[])=={}


def test_scene_hierarchy_applies_position_rotation_scale_and_column_basis():
    parent=T.Section("node",{}, {"position":"Vector3(10, 2, 20)","rotation_degrees":"Vector3(0, 90, 0)","scale":"Vector3(2, 1, 3)"})
    child=T.Section("node",{}, {"position":"Vector3(1, 0, 0)"})
    scene=T.Scene(Path("fixture.tscn"),{}, {}, {"Wrapper":parent,"Wrapper/Child":child})
    assert np.allclose(scene.world("Wrapper/Child")[:3,3],[10,2,18])
    matrix=T.transform("Transform3D(0, 0, -1, 0, 1, 0, 1, 0, 0, 10, 2, 20)")
    assert np.allclose(matrix @ [1,0,0,1],[10,2,19,1])


def test_bad_frame_cell_and_translation_contracts_are_caught(territories):
    import copy
    t=territories[0]; spec=copy.deepcopy(t.spec); spec["server"]["cells"][0]+=1
    changed=dataclasses.replace(t,spec=spec,translation=t.translation+np.array([0.5,0,0]))
    problems,_=T.check_frames([changed])
    assert any("multiples of six" in p for p in problems)
    assert any("whole continent metres" in p for p in problems)


def test_active_plan_owners_use_positions_and_reject_unknown_schemas():
    import copy
    import bootstrap_continent_v2_territory as B
    from shapely.geometry import Polygon,Point
    from shapely.ops import unary_union
    recorded=T._json(B.INPUT/"sections_spec.json")
    shapes=[(s["mapId"],unary_union([Polygon(r) for r in s["ownershipPolygons"]])) for s in recorded["sections"]]
    retired=set(recorded["retiredMapIds"])
    plan=T._json(B.PLAN); source=T._json(B.INPUT/"source-plan.json")
    for landmark,original in zip(plan["landmarks"],source["landmarks"]):
        expected=next(rid for rid,shape in shapes if shape.covers(Point(original["x"],original["z"])))
        assert landmark["territory"]==expected
        assert dict(landmark,territory=original["territory"])==original
    B.reassign_active_owners(copy.deepcopy(plan),shapes,retired)
    with pytest.raises(ValueError,match="unresolved nonposition"):
        B.reassign_active_owners({"ferry":{"territory":next(iter(retired)),"id":"unknown"}},shapes,retired)
    with pytest.raises(ValueError,match="outside section"):
        B.reassign_active_owners({"landmark":{"territory":next(iter(retired)),"x":0,"z":0}},shapes,retired)
    with pytest.raises(ValueError,match="retired ID"):
        B.reassign_active_owners({"connections":{"maps":[next(iter(retired))]}},shapes,retired)


def test_water_clearance_uses_transformed_ellipse_instead_of_outer_circle():
    angle = np.pi/5
    rotate = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    feature = {"kind": "water region", "path": "WaterRegions/oval", "xz": np.array([[12., 30.]]),
               "ellipse": rotate @ np.diag([20., 3.])}
    local = np.array([[0., 8.], [25., 0.], [0., 2.], [0., 3.5]])
    world = local @ rotate.T + feature["xz"][0]
    np.testing.assert_allclose(T._distance_to_water(feature, world[:, 0], world[:, 1]),
                               [5., 5., 0., .5], atol=1e-10)
    # The enclosing radius-20 circle would wrongly flag the first point, while
    # the last point must still fail the two-metre seam rule.
    assert T._distance_to_water(feature, world[:1,0], world[:1,1])[0] > T.SEAM_WATER_CLEARANCE
    assert T._distance_to_water(feature, world[3:,0], world[3:,1])[0] < T.SEAM_WATER_CLEARANCE
