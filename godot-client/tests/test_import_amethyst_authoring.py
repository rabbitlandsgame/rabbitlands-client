from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "import_amethyst_authoring", TOOLS / "import_amethyst_authoring.py")
assert SPEC and SPEC.loader
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


def test_final_composed_objects_keep_walk_subtree_and_local_endpoints():
    nodes = []
    final_objects = []
    crossings = []
    crossing_nodes = {asset: (identity, walk) for identity, (asset, walk)
                      in A.CROSSING_ASSETS.items()}
    for index in range(124):
        name = (list(crossing_nodes)[index] if index < len(crossing_nodes)
                else f"FinalPlacement_{index:03d}")
        root = len(nodes)
        translation = [950.0 + index, 2.0, 400.0]
        node = {"name": name, "mesh": index, "translation": translation}
        if name in crossing_nodes:
            identity, walk = crossing_nodes[name]
            child = root + 1
            node["children"] = [child]
            nodes.append(node)
            nodes.append({"name": walk, "mesh": 1000 + index})
            crossings.append({"id": identity, "endpoints": [
                [950.0 + index, 4.0, 400.0],
                [954.0 + index, 5.0, 400.0]]})
        else:
            nodes.append(node)
        final_objects.append({
            "region": A.REGION_ID, "libraryRegion": A.REGION_ID,
            "node": name, "index": root, "indices": [root],
            "shift": [1.0, 0.5, -2.0], "collides": index >= 8,
            "walk": False, "source": {"kind": "landmark"},
        })
    content = SimpleNamespace(documents={A.REGION_ID: ({"nodes": nodes}, b"")})
    objects, _families = A.final_object_records(
        content, tuple(final_objects), {"crossings": crossings})

    assert len(objects) == 124
    first = next(entry for entry in objects if entry["id"] == "Landmark_SurveyedBridge_0")
    assert first["collisionRole"] == "none"
    assert np.allclose(first["matrix"][:3, 3], [1.0, 2.5, -2.0])
    assert first["metadata"]["authoredCrossing"] == {
        "id": "bridge_massif",
        "walkNode": "Walk_Landmark_SurveyedBridge_0__alpine_gravel",
        "localEndpoints": [[0.0, 2.0, 0.0], [4.0, 3.0, 0.0]],
    }


def test_amethyst_paths_preserve_all_owned_ids_and_convert_full_widths(tmp_path):
    roads = {"roads": []}
    for index, identity in enumerate(A.OWNED_ROUTE_IDS):
        roads["roads"].append({
            "id": identity, "width": 4.0 if index < 3 else 1.65,
            "points": [[950.0, 10.0, 400.0], [952.0, 11.0, 404.0]],
        })
    records = A.path_records(roads, tmp_path, "res://fixture")

    assert [entry["id"] for entry in records] == list(A.OWNED_ROUTE_IDS)
    assert records[0]["points"] == [[0.0, 10.0, 0.0], [2.0, 11.0, 4.0]]
    assert records[0]["width"] == 8.0
    assert {entry["routingRole"] for entry in records
            if entry["id"].startswith("discovery-")} == {"decorative"}
    assert {entry["routingRole"] for entry in records
            if entry["id"] in A.REQUIRED_ROUTE_IDS} == {"required"}
    assert {entry["properties"]["terrainConform"] for entry in records} == {False}


def test_runtime_seed_coordinates_match_godot_text_precision():
    source = {"bindings": [{
        "targetOffset": [1.9547052910647835, 0.0, 1.2864350136806024],
        "initialPosition": [42.12345678901234, 7.0, -8.76543210987654],
    }]}

    result = A.canonical_runtime_seed(source)

    assert result["bindings"][0]["targetOffset"] == [
        1.95470529106, 0.0, 1.28643501368]
    assert result["bindings"][0]["initialPosition"] == [
        42.123456789, 7.0, -8.76543210988]
    assert source["bindings"][0]["targetOffset"][0] == 1.9547052910647835


def test_runtime_seed_identity_uses_hash_bound_immutable_profile(tmp_path):
    profile = tmp_path / A.IMMUTABLE_PROFILE_PREFIX / "config/eloria"
    profile.mkdir(parents=True)
    interactive = profile / "interactives.txt"
    interactive.write_text(
        "amethyst_barrens | 505 | 99 | 291 | secret | maps.txt | Vault\n",
        encoding="utf-8")
    seed = {
        "provenance": {"profileFiles": [{
            "path": A.IMMUTABLE_PROFILE_PREFIX + "config/eloria/interactives.txt",
            "sha256": A.sha256(interactive)}]},
        "bindings": [{
            "id": "interactives.txt:1:505@99:291", "role": "interactive",
            "source": {"path": "config/eloria/interactives.txt", "line": 1,
                       "oldTile": [99, 291], "recordId": "505"},
        }],
    }

    A.validate_runtime_seed_profiles(seed, tmp_path)
    seed["bindings"][0]["source"]["oldTile"] = [142, 319]
    with pytest.raises(ValueError, match="immutable content row"):
        A.validate_runtime_seed_profiles(seed, tmp_path)
    seed["bindings"][0]["source"]["oldTile"] = [99, 291]
    interactive.write_text(
        "amethyst_barrens | 505 | 100 | 291 | secret | maps.txt | Vault\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="profile hash mismatch"):
        A.validate_runtime_seed_profiles(seed, tmp_path)


def test_runtime_seed_rejects_logical_profile_path_without_repo_prefix(tmp_path):
    seed = {
        "provenance": {"profileFiles": [{
            "path": "config/eloria/interactives.txt", "sha256": "0" * 64}]},
        "bindings": [{"source": {"path": "config/eloria/interactives.txt"}}],
    }

    with pytest.raises(ValueError, match="immutable repo-relative prefix"):
        A.validate_runtime_seed_profiles(seed, tmp_path)


def test_generated_asset_cleanup_removes_only_obsolete_sources_and_sidecars(tmp_path):
    prototypes = tmp_path / "assets/prototypes"
    textures = tmp_path / "assets/textures"
    prototypes.mkdir(parents=True)
    textures.mkdir(parents=True)
    for path in (prototypes / "keep.glb", prototypes / "keep.glb.import",
                 prototypes / "old.glb", prototypes / "old.glb.import",
                 prototypes / "already-gone.glb.import",
                 textures / "keep.png", textures / "keep.png.import",
                 textures / "old.png", textures / "old.png.import",
                 textures / "already-gone.png.import"):
        path.write_bytes(b"fixture")
    records = {"keep": {
        "path": "res://region/assets/prototypes/keep.glb",
        "stats": {"externalResources": {
            "res://region/assets/textures/keep.png": "digest",
        }},
    }}

    A.prune_generated_assets(tmp_path, records)

    assert sorted(path.name for path in prototypes.iterdir()) == [
        "keep.glb", "keep.glb.import"]
    assert sorted(path.name for path in textures.iterdir()) == [
        "keep.png", "keep.png.import"]
