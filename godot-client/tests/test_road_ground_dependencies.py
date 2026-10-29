import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from road_ground_dependencies import dependencies, RoadGroundDependencyError, SCHEMA


def fixture(tmp_path, resources=None):
    chunk = tmp_path / "eloria-assets/maps/region/client/chunks/00_00"
    chunk.mkdir(parents=True)
    payload = chunk / "ids.zst"
    payload.write_bytes(b"verified runtime bytes")
    metadata = chunk / "roads.json"
    document = {"schema": SCHEMA, "resources": resources if resources is not None else {
        "ids.zst": hashlib.sha256(payload.read_bytes()).hexdigest()}}
    metadata.write_text(json.dumps(document))
    config = {"metadata": "roads.json", "sha256": hashlib.sha256(metadata.read_bytes()).hexdigest()}
    return chunk / "world.json", config, payload, metadata


def test_absent_maps_keep_empty_closure(tmp_path):
    assert dependencies(tmp_path, tmp_path / "world.json", None) == {}


def test_metadata_and_binary_are_both_dependencies(tmp_path):
    world, config, payload, metadata = fixture(tmp_path)
    result = dependencies(tmp_path, world, config)
    assert set(result) == {payload, metadata}
    assert result[payload] == hashlib.sha256(payload.read_bytes()).hexdigest()


@pytest.mark.parametrize("target", ["payload", "metadata"])
def test_mutated_runtime_input_is_rejected(tmp_path, target):
    world, config, payload, metadata = fixture(tmp_path)
    (payload if target == "payload" else metadata).write_bytes(b"changed after publication")
    with pytest.raises(RoadGroundDependencyError):
        dependencies(tmp_path, world, config)


@pytest.mark.parametrize("uri", ["C:/private/file", "/private/file", "../../../../../../../private", "%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/private", "wrong\\file"])
def test_resource_cannot_escape_asset_tree(tmp_path, uri):
    world, config, _, _ = fixture(tmp_path, {uri: "0" * 64})
    with pytest.raises(RoadGroundDependencyError):
        dependencies(tmp_path, world, config)


def test_config_cannot_select_parent_metadata(tmp_path):
    world, config, _, _ = fixture(tmp_path)
    config["metadata"] = "../roads.json"
    with pytest.raises(RoadGroundDependencyError):
        dependencies(tmp_path, world, config)


def test_undeclared_resource_set_is_rejected(tmp_path):
    world, config, _, _ = fixture(tmp_path, {})
    with pytest.raises(RoadGroundDependencyError):
        dependencies(tmp_path, world, config)
