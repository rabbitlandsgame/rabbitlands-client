"""Selected source binds authoring to exact portable inputs, never publications."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import ownership_contract as O
import authoring_catalog as C
import authoring as A
from test_ownership_contract import fixture_document


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture_checkout(tmp_path, document=None):
    client = tmp_path / "relocated client"
    root = client / "eloria-assets/maps/nymara-regions/_continent"
    marker = client / "godot-client/project.godot"
    marker.parent.mkdir(parents=True)
    marker.write_text("config_version=5\n", encoding="utf-8")
    source = root / "ownership/selected.json"
    document = copy.deepcopy(document or fixture_document())
    write(source, document)
    plan = {"bounds": document["bounds"], "regions": [
        {"id": name, "center": [row["coordinateFrame"]["continentTranslation"][i] for i in (0, 2)]}
        for name, row in document["regions"].items()], "ownership_contract": {
            "path": "ownership/selected.json", "revision": document["revision"],
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
    path = root / "diagonal-plan.json"
    baseline = copy.deepcopy(plan)
    baseline.pop("ownership_contract")
    write(root / "ownership/plan-feature-baseline-v1.json", baseline)
    write(path, plan)
    return client, path, source, plan


def snapshot_document(binding):
    frame, storage = binding["coordinateFrame"], binding["baselineStorage"]
    return {"regionId": binding["binding"]["regionId"],
            "continentTranslation": frame["continentTranslation"],
            "server": {"origin": frame["serverOrigin"], "metresPerTile": 1,
                       "cells": storage["serverCells"], "collisionOriginMetres": storage["collisionOriginMetres"]},
            "ownershipSource": binding["binding"],
            "sources": {"repositoryDependencies": binding["repositoryDependencies"]},
            "seams": {"ownershipPolygonSha256": binding["ownershipPolygonSha256"]}}


def test_relocated_binding_uses_raw_bytes_and_repository_relative_paths(tmp_path):
    client, path, source, plan = fixture_checkout(tmp_path)
    result = O.editor_binding("west", path)
    assert result["binding"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["binding"]["planSha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert all(not Path(row["path"]).is_absolute() and "\\" not in row["path"]
               for row in result["repositoryDependencies"])
    A.validate_snapshot_ownership(snapshot_document(result), path)
    # JSON formatting is authority too: stale selection cannot trust parsed equality.
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(O.OwnershipContractError, match="hash/revision"):
        O.editor_binding("west", path)


@pytest.mark.parametrize("change,message", [
    (lambda p: p.update(ownership_contract=None), "requires exactly"),
    (lambda p: p["ownership_contract"].update(sha256="0" * 64), "hash/revision"),
    (lambda p: p["ownership_contract"].update(revision="wrong"), "hash/revision"),
    (lambda p: p["regions"][0].update(center=[11, 20]), "frozen"),
    (lambda p: p["ownership_contract"].update(path="../selected.json"), "contained"),
    (lambda p: p["ownership_contract"].update(path="ownership/../ownership/selected.json"), "contained"),
    (lambda p: p["ownership_contract"].update(path="C:/selected.json"), "contained"),
    (lambda p: p["ownership_contract"].update(path="\\\\host\\selected.json"), "contained"),
    (lambda p: p["ownership_contract"].update(path="res://selected.json"), "contained"),
    (lambda p: p["ownership_contract"].update(path="missing.json"), "cannot read"),
])
def test_selected_invalid_inputs_fail_closed(tmp_path, change, message):
    _, path, _, plan = fixture_checkout(tmp_path)
    change(plan)
    write(path, plan)
    with pytest.raises(O.OwnershipContractError, match=message):
        O.editor_binding("west", path)


def test_invalid_partition_reaches_strict_validator_even_with_current_hash(tmp_path):
    document = fixture_document()
    document["regions"]["west"]["ownershipPolygon"][1][0] = 19
    _, path, _, _ = fixture_checkout(tmp_path, document)
    with pytest.raises(O.OwnershipContractError, match="partition"):
        O.editor_binding("west", path)


@pytest.mark.parametrize("change", [
    lambda d: d["continentTranslation"].__setitem__(0, 99),
    lambda d: d["server"]["origin"].__setitem__(0, 99),
    lambda d: d["server"]["cells"].__setitem__(0, 99),
    lambda d: d["server"]["collisionOriginMetres"].__setitem__(0, 99),
    lambda d: d["ownershipSource"].update(regionId="east"),
    lambda d: d["sources"]["repositoryDependencies"].pop(),
    lambda d: d["seams"].update(ownershipPolygonSha256="0" * 64),
])
def test_snapshot_binding_rejects_frame_or_dependency_drift(tmp_path, change):
    _, path, _, _ = fixture_checkout(tmp_path)
    document = snapshot_document(O.editor_binding("west", path))
    change(document)
    with pytest.raises(A.AuthoringError):
        A.validate_snapshot_ownership(document, path)


def test_plan_change_and_selection_removal_require_fresh_snapshot(tmp_path):
    _, path, _, plan = fixture_checkout(tmp_path)
    document = snapshot_document(O.editor_binding("west", path))
    plan["reviewNote"] = "metadata change still invalidates bake"
    write(path, plan)
    with pytest.raises(A.AuthoringError, match="baseline"):
        A.validate_snapshot_ownership(document, path)
    plan.pop("ownership_contract")
    write(path, plan)
    assert O.editor_binding("west", path) == {}
    with pytest.raises(A.AuthoringError, match="stale"):
        A.validate_snapshot_ownership(document, path)
    document.pop("ownershipSource")
    document["sources"].pop("repositoryDependencies")
    A.validate_snapshot_ownership(document, path)


def test_selected_region_spec_checks_immutable_frame(tmp_path, monkeypatch):
    client, path, _, _ = fixture_checkout(tmp_path)
    binding = O.editor_binding("west", path)
    spec = json.loads((C.CLIENT / "godot-client/world_authoring/regions/sunmane_steppe/region-authoring-spec.json").read_bytes())
    current = snapshot_document(binding)
    spec.update(regionId="west", continentTranslation=current["continentTranslation"], server=current["server"])
    spec["paths"] = {"scene": "godot-client/world_authoring/regions/west/west.tscn",
                     "manifest": "eloria-assets/maps/nymara-regions/west/world.json",
                     "snapshot": "eloria-assets/maps/nymara-regions/west/authoring/continent-authoring.json"}
    for name in ("scene", "manifest"):
        file = client / spec["paths"][name]
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("{}", encoding="utf-8")
    spec_path = client / "godot-client/world_authoring/regions/west/region-authoring-spec.json"
    write(spec_path, spec)
    monkeypatch.setattr(C, "CLIENT", client)
    assert C.load_region_spec(spec_path, ownership_plan_path=path).ownership_binding == binding["binding"]
    spec["server"]["origin"][0] += 1
    write(spec_path, spec)
    with pytest.raises(C.CatalogError, match="frozen"):
        C.load_region_spec(spec_path, ownership_plan_path=path)


def test_cli_validates_without_working_directory_dependency(tmp_path):
    _, path, _, _ = fixture_checkout(tmp_path)
    result = subprocess.run([sys.executable, str(HERE / "ownership_contract.py"),
                             "--plan", str(path), "--region", "west"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == O.editor_binding("west", path)


def test_input_mutation_during_validation_is_rejected(tmp_path, monkeypatch):
    _, path, source, _ = fixture_checkout(tmp_path)
    original = O.for_plan
    def racing(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_bytes(source.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(O, "for_plan", racing)
    with pytest.raises(O.OwnershipContractError, match="changed during"):
        O.editor_binding("west", path)


def test_missing_repository_marker_is_rejected(tmp_path):
    client, path, _, _ = fixture_checkout(tmp_path)
    (client / "godot-client/project.godot").unlink()
    with pytest.raises(O.OwnershipContractError, match="repository markers"):
        O.editor_binding("west", path)


def test_selected_editor_requires_frozen_feature_baseline(tmp_path):
    _, path, _, _ = fixture_checkout(tmp_path)
    (path.parent / "ownership/plan-feature-baseline-v1.json").unlink()
    with pytest.raises(O.OwnershipContractError, match="requires.*baseline"):
        O.editor_binding("west", path)


def test_frozen_feature_baseline_allows_only_selection_and_binds_exact_bytes(tmp_path):
    _, path, _, plan = fixture_checkout(tmp_path)
    baseline_document = copy.deepcopy(plan)
    baseline_document.pop("ownership_contract")
    baseline = path.parent / "ownership/plan-feature-baseline-v1.json"
    write(baseline, baseline_document)
    result = O.editor_binding("west", path)
    assert len(result["repositoryDependencies"]) == 3
    document = snapshot_document(result)
    A.validate_snapshot_ownership(document, path)
    baseline.write_bytes(baseline.read_bytes() + b"\n")
    with pytest.raises(A.AuthoringError, match="dependencies changed"):
        A.validate_snapshot_ownership(document, path)
    plan["rivers"] = [{"id": "unauthorized-river", "points": [[0, 0], [4, 4]], "width": 2}]
    write(path, plan)
    with pytest.raises(O.OwnershipContractError, match="only ownership_contract"):
        O.editor_binding("west", path)


def test_baseline_byte_mutation_during_validation_is_rejected(tmp_path, monkeypatch):
    _, path, _, _ = fixture_checkout(tmp_path)
    baseline = path.parent / "ownership/plan-feature-baseline-v1.json"
    read = Path.read_bytes
    def racing(file):
        data = read(file)
        if file == baseline:
            file.write_bytes(data + b"\n")
        return data
    monkeypatch.setattr(Path, "read_bytes", racing)
    with pytest.raises(O.OwnershipContractError, match="changed during"):
        O.editor_binding("west", path)


def migration_fixture(client, document):
    field = client / "godot-client/world_authoring/terrain/shared-field-v1"
    field.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "eloria-terrain-shared-field-v1", "lattice": {
        "originMetres": [0, 0], "spacing": 2, "globalVertexMin": [0, 0],
        "vertices": [2, 2], "order": "row-major-x-fast"}}
    for key, encoding in (("heights", "float32-little-endian"), ("colors", "rgba8")):
        path = field / (key + ".bin")
        path.write_bytes(bytes(16))
        manifest[key] = {"path": path.relative_to(client).as_posix(),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "encoding": encoding}
    path = field / "manifest.json"
    write(path, manifest)
    translation = document["continentTranslation"]
    document["terrain"] = {"origin": [0, 0], "migration": {
        "revision": "global-lattice-envelope-v1", "sharedFieldPath": path.relative_to(client).as_posix(),
        "sharedFieldSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "globalVertexMin": [int(translation[0] / 2), int(translation[2] / 2)],
        "previousGridSha256": "1" * 64}}
    return C.migration_sources(document, client=client)


def test_migration_provenance_binds_arrays_under_legacy_and_selected_plans(tmp_path):
    client, path, _, plan = fixture_checkout(tmp_path)
    document = snapshot_document(O.editor_binding("west", path))
    dependencies = migration_fixture(client, document)
    document["sources"]["repositoryDependencies"] = sorted(
        document["sources"]["repositoryDependencies"] + dependencies, key=lambda row: row["path"])
    A.validate_snapshot_ownership(document, path)
    plan.pop("ownership_contract")
    write(path, plan)
    document.pop("ownershipSource")
    document["sources"]["repositoryDependencies"] = dependencies
    A.validate_snapshot_ownership(document, path)
    document["terrain"]["migration"]["globalVertexMin"][0] += 1
    with pytest.raises(A.AuthoringError, match="grid identity"):
        A.validate_snapshot_ownership(document, path)
    document["terrain"]["migration"]["globalVertexMin"][0] -= 1
    arrays = [row for row in dependencies if row["path"].endswith(".bin")]
    (client / arrays[0]["path"]).write_bytes(bytes(15) + b"x")
    with pytest.raises(A.AuthoringError, match="hash changed"):
        A.validate_snapshot_ownership(document, path)


def test_required_terrain_coverage_includes_incident_vertices_and_ring():
    import numpy as np
    owner = np.full((6, 6), -1)
    owner[2, 2] = 0
    required = A.required_terrain_vertices(owner, 0, (7, 7))
    assert required.sum() == 16
    A.validate_required_coverage(required, np.arange(1, 5), np.arange(1, 5), "fixture")
    with pytest.raises(A.AuthoringError, match="omits 4 required"):
        A.validate_required_coverage(required, np.arange(2, 5), np.arange(1, 5), "fixture")


def test_selected_incomplete_terrain_rejects_before_mutation_legacy_still_clips():
    import numpy as np
    from types import SimpleNamespace
    owner = np.full((6, 6), -1)
    owner[2, 2] = 0
    world = SimpleNamespace(owner=owner, ids=["fixture"], x0=0, z0=0,
                            height=np.zeros((7, 7)), ownership_contract=object())
    snapshot = SimpleNamespace(document={"regionId": "fixture", "terrain": {
        "origin": [4, 4], "cellMetres": 2}}, translation=np.zeros(3),
        terrain_width=2, terrain_height=2, effective_heights=lambda: np.ones((2, 2)))
    with pytest.raises(A.AuthoringError, match="omits 12 required"):
        A.apply_terrain(world, snapshot)
    assert np.count_nonzero(world.height) == 0
    assert not hasattr(world, "authored_terrain_authority")
    world.ownership_contract = None
    assert A.apply_terrain(world, snapshot)["appliedVertices"] == 4
