from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import authoring_catalog as C


def test_product_catalog_is_sorted_complete_and_authored_contracts_are_exact():
    entries = C.load_catalog()

    assert [entry.label for entry in entries] == sorted(
        (entry.label for entry in entries), key=str.casefold)
    assert {entry.id for entry in entries} == {
        "amberwood", "amethyst_barrens", "crownwater", "grey_moors",
        "four_gates", "manymouth_delta", "mirrorhold", "ssarathi_ruins", "sunmane_steppe",
        "verdant_stair", "westhaven", "whitehorn_range",
    }
    assert all(entry.authored and entry.scene_path.is_file() and
               entry.authoring_spec_path.is_file() for entry in entries)
    contracts = {value.id: value for value in C.authored_contracts()}
    assert set(contracts) == {entry.id for entry in entries}
    assert sum(value.runtime_binding_count for value in contracts.values()) == 2094
    contract = contracts["sunmane_steppe"]
    assert contract.continent_translation == (1200.0, 0.0, 720.0)
    assert contract.server_origin == (194, 292)
    assert contract.server_cells == (792, 792)
    assert contract.terrain_origin == (-194.0, -500.0)
    assert contract.terrain_vertices == (397, 397)
    assert contract.snapshot_path == (
        C.CLIENT / "eloria-assets/maps/nymara-regions/sunmane_steppe/authoring/continent-authoring.json")
    assert set(contract.required_route_ids) < set(contract.owned_route_ids)
    amethyst = contracts["amethyst_barrens"]
    assert amethyst.continent_translation == (950.0, 0.0, 400.0)
    assert amethyst.server_origin == (182, 166)
    assert amethyst.server_cells == (738, 738)
    assert amethyst.terrain_origin == (-182.0, -572.0)
    assert amethyst.terrain_vertices == (370, 370)
    assert amethyst.runtime_binding_count == 189
    assert amethyst.runtime_point_count == 130
    mirrorhold = contracts["mirrorhold"]
    assert mirrorhold.continent_translation == (840.0, 0.0, 650.0)
    assert mirrorhold.server_origin == (208, 350)
    assert mirrorhold.terrain_vertices == (271, 289)
    assert mirrorhold.runtime_binding_count == 139
    assert mirrorhold.runtime_point_count == 93
    whitehorn = contracts["whitehorn_range"]
    assert whitehorn.continent_translation == (550.0, 0.0, 220.0)
    assert whitehorn.server_origin == (362, 360)
    assert whitehorn.terrain_vertices == (352, 289)
    assert whitehorn.runtime_binding_count == 197
    assert whitehorn.runtime_point_count == 67


def _write_fixture(tmp_path: Path, monkeypatch, catalog: dict, spec: dict | None = None):
    client = tmp_path / "client"
    manifest = client / "eloria-assets/maps/nymara-regions/example/world.json"
    scene = client / "godot-client/world_authoring/regions/example/example.tscn"
    spec_path = scene.with_name("region-authoring-spec.json")
    manifest.parent.mkdir(parents=True)
    scene.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"asset": {"id": "example"}}), encoding="utf-8")
    scene.write_text('[gd_scene format=3]\nregion_id = "example"\n', encoding="utf-8")
    if spec is not None:
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
    catalog_path = client / "godot-client/world_authoring/territories.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(C, "CLIENT", client)
    return catalog_path


def test_catalog_rejects_half_migrated_entry(tmp_path, monkeypatch):
    path = _write_fixture(tmp_path, monkeypatch, {
        "schema": C.CATALOG_SCHEMA,
        "entries": [{"id": "example", "label": "Example",
                          "manifestPath": "eloria-assets/maps/nymara-regions/example/world.json",
                          "scenePath": "godot-client/world_authoring/regions/example/example.tscn",
                          "authoringSpecPath": None}],
    })
    with pytest.raises(C.CatalogError, match="atomically"):
        C.load_catalog(path)


def test_catalog_rejects_spec_scene_disagreement(tmp_path, monkeypatch):
    spec = {
        "schema": C.SPEC_SCHEMA, "regionId": "other", "label": "Example",
        "adapter": "fixture-v1",
        "paths": {"scene": "godot-client/world_authoring/regions/example/example.tscn",
                  "manifest": "eloria-assets/maps/nymara-regions/example/world.json",
                  "snapshot": "eloria-assets/maps/nymara-regions/example/authoring/continent-authoring.json"},
        "continentTranslation": [0, 0, 0],
        "server": {"origin": [0, 0], "cells": [2, 2],
                   "collisionOriginMetres": [0, 0]},
        "terrain": {"origin": [0, 0], "cellMetres": 2, "vertices": [2, 2]},
        "authority": {"ownedRouteIds": [], "requiredRouteIds": [],
                      "ownedPlanFeatureIds": []},
        "gameplay": {"runtimeBindingCount": 0, "runtimePointCount": 0,
                     "existingMarkerBindingCount": 0},
    }
    path = _write_fixture(tmp_path, monkeypatch, {
        "schema": C.CATALOG_SCHEMA,
        "entries": [{"id": "example", "label": "Example",
                          "manifestPath": "eloria-assets/maps/nymara-regions/example/world.json",
                          "scenePath": "godot-client/world_authoring/regions/example/example.tscn",
                          "authoringSpecPath": "godot-client/world_authoring/regions/example/region-authoring-spec.json"}],
    }, spec)
    with pytest.raises(C.CatalogError, match="regionId"):
        C.load_catalog(path)


def test_import_can_validate_a_spec_before_creating_its_scene(tmp_path, monkeypatch):
    client = tmp_path / "client"
    manifest = client / "eloria-assets/maps/nymara-regions/example/world.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"asset": {"id": "example"}}), encoding="utf-8")
    spec_path = client / "godot-client/world_authoring/regions/example/region-authoring-spec.json"
    spec_path.parent.mkdir(parents=True)
    spec = {
        "schema": C.SPEC_SCHEMA, "regionId": "example", "label": "Example",
        "adapter": "fixture-v1",
        "paths": {"scene": "godot-client/world_authoring/regions/example/example.tscn",
                  "manifest": "eloria-assets/maps/nymara-regions/example/world.json",
                  "snapshot": "eloria-assets/maps/nymara-regions/example/authoring/continent-authoring.json"},
        "continentTranslation": [0, 0, 0],
        "server": {"origin": [0, 0], "cells": [2, 2], "collisionOriginMetres": [0, 0]},
        "terrain": {"origin": [0, 0], "cellMetres": 2, "vertices": [2, 2]},
        "authority": {"ownedRouteIds": [], "requiredRouteIds": [],
                      "ownedPlanFeatureIds": []},
        "gameplay": {"runtimeBindingCount": 0, "runtimePointCount": 0,
                     "existingMarkerBindingCount": 0},
    }
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(C, "CLIENT", client)

    contract = C.load_region_spec(spec_path, require_scene=False)
    assert contract.scene_path.name == "example.tscn"
    with pytest.raises(C.CatalogError, match="does not exist"):
        C.load_region_spec(spec_path)


def test_pipeline_bakes_each_authored_catalog_entry_independently(tmp_path, monkeypatch):
    import build_pipeline as P

    project = tmp_path / "client/godot-client"
    scene = project / "world_authoring/regions/example/example.tscn"
    snapshot = tmp_path / "client/eloria-assets/maps/nymara-regions/example/authoring/continent-authoring.json"
    scene.parent.mkdir(parents=True)
    scene.write_text('[gd_scene format=3]\nregion_id = "example"\n', encoding="utf-8")
    executable = tmp_path / "godot.exe"
    executable.write_bytes(b"")
    contract = type("Contract", (), {"id": "example", "scene_path": scene,
                                      "snapshot_path": snapshot})()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if any(str(part).endswith("region_bake_cli.gd") for part in command):
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text("{}", encoding="utf-8")
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(P, "CLIENT", tmp_path / "client")
    monkeypatch.setattr(P, "find_godot", lambda _explicit=None: str(executable))
    monkeypatch.setattr(P.authoring_catalog, "authored_contracts", lambda _path: (contract,))
    monkeypatch.setattr(P.subprocess, "run", run)
    P.bake_authored_regions(catalog_path=tmp_path / "catalog.json")

    assert len(calls) == 2
    assert "--editor" in calls[0]
    assert "res://world_authoring/regions/example/example.tscn" in calls[1]
    assert str(snapshot) in calls[1]
