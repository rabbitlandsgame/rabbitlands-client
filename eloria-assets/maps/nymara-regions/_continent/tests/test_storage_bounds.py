"""Storage expansion preserves logical identity and exact source provenance."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from storage_bounds import StorageBounds as Bounds, authoring_storage
import authoring as A
import authoring_catalog as C
import ownership_contract as O
from test_ownership_authoring import fixture_checkout, snapshot_document, write


@pytest.mark.parametrize("minimum", [(0, 0), (-50, -18), (7, 13)])
def test_indices_are_storage_relative_and_endpoints_are_half_open(minimum):
    bounds = Bounds(6, 12, *minimum)
    assert Bounds.from_metadata([6, 12], bounds.metadata()) == bounds
    for row in range(12):
        for column in range(6):
            tile = bounds.logical_xy(column, row)
            assert tile == (minimum[0] + column, minimum[1] + row)
            assert bounds.index_xy(*tile) == (column, row)
            assert bounds.index(*tile) == row * 6 + column
    for tile in ((bounds.min_x - 1, bounds.min_y), (bounds.min_x, bounds.min_y - 1),
                 (bounds.max_x, bounds.min_y), (bounds.min_x, bounds.max_y)):
        assert not bounds.contains(*tile) and bounds.index(*tile) is None
    with pytest.raises(ValueError):
        bounds.logical_xy(6, 0)


def test_conservative_union_retains_each_old_logical_identity():
    old = Bounds(426, 426)
    needed = Bounds(484, 332, -50, 20)
    union = old.union(needed)
    assert union == Bounds(484, 426, -50, 0)
    assert union.contains_bounds(old) and union.contains_bounds(needed)
    assert union.union(old) == union
    # Origin and world transforms are independent: only array column changes.
    for tile in ((0, 0), (425, 425), (241, 181)):
        assert union.logical_xy(*union.index_xy(*tile)) == tile
        assert union.index_xy(*tile)[0] == old.index_xy(*tile)[0] + 50


def test_wire_capacity_does_not_impose_publisher_shape():
    assert Bounds(2048, 1, -100, 7).max_x == 1948
    for args in ((2049, 1), (0, 1), (1, -1), (1, 1, 2**31, 0), (2, 1, 2**31 - 1, 0)):
        with pytest.raises(ValueError):
            Bounds(*args)


@pytest.mark.parametrize("metadata", [
    {"serverTileMin": [0, 0]}, {"serverStorageVersion": 1},
    {"serverStorageVersion": 0, "serverTileMin": [0, 0]},
    {"serverStorageVersion": True, "serverTileMin": [0, 0]},
    {"serverStorageVersion": 1.0, "serverTileMin": [0, 0]},
    {"serverStorageVersion": 1, "serverTileMin": [False, 0]},
    {"serverStorageVersion": 1, "serverTileMin": [0.5, 0]},
    {"serverStorageVersion": 1, "serverTileMin": [0, 0, 0]},
])
def test_explicit_malformed_storage_never_falls_back(metadata):
    with pytest.raises(ValueError):
        Bounds.from_metadata([6, 6], metadata)


def test_omitted_and_explicit_zero_minimum_are_semantically_equal():
    assert Bounds.from_metadata([6, 12], {}) == Bounds.from_metadata([6, 12], Bounds(6, 12).metadata())
    with pytest.raises(ValueError):
        Bounds.from_metadata([True, 12], {})


@pytest.mark.parametrize("field,value", [
    ("localOrigin", [0, 1, 0]), ("metresPerTile", 2), ("metresPerTile", True),
    ("invertServerY", False), ("invertServerY", 1), ("walkingHeight", float("nan")),
    ("collisionOriginMetres", [-60, 70]),
])
def test_physical_origin_requires_supported_explicit_frame(field, value):
    server = {"origin": [60, 70], "cells": [126, 126],
              "collisionOriginMetres": [-66, 70], **Bounds(126, 126, -6, 0).metadata()}
    server[field] = value
    with pytest.raises(ValueError):
        authoring_storage(server)


def test_selected_storage_can_expand_without_changing_frozen_frame(tmp_path):
    _, plan, _, _ = fixture_checkout(tmp_path)
    binding = O.editor_binding("west", plan)
    document = snapshot_document(binding)
    document["server"].update(cells=[126, 132], collisionOriginMetres=[-66, 82],
                              **Bounds(126, 132, -6, -12).metadata())
    before = copy.deepcopy(binding)
    O.validate_authoring_frame(binding, document)
    assert binding == before
    for change in (
        {"cells": [125, 132]},  # Shrinks the old positive edge by one.
        {"serverTileMin": [1, -12], "collisionOriginMetres": [-59, 82]},
        {"origin": [61, 70], "collisionOriginMetres": [-67, 82]},
        {"collisionOriginMetres": [-60, 70]},
    ):
        bad = copy.deepcopy(document)
        bad["server"].update(change)
        with pytest.raises(O.OwnershipContractError):
            O.validate_authoring_frame(binding, bad)


def bind_spec(client, document):
    relative = f"godot-client/world_authoring/regions/{document['regionId']}/region-authoring-spec.json"
    path = client / relative
    write(path, {"schema": C.SPEC_SCHEMA, "regionId": document["regionId"],
                 "continentTranslation": document["continentTranslation"], "server": document["server"]})
    document.setdefault("sources", {})["authoringSpec"] = {
        "path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return path


def test_snapshot_binds_exact_spec_bytes_and_retains_optional_frame(tmp_path):
    document = {"regionId": "west", "continentTranslation": [10, 0, 20],
        "server": {"origin": [60, 70], "cells": [126, 132], "collisionOriginMetres": [-66, 82],
                   "walkingHeight": 42.25, "localOrigin": [0, 0, 0], "invertServerY": True,
                   **Bounds(126, 132, -6, -12).metadata()}}
    with pytest.raises(A.AuthoringError, match="requires sources.authoringSpec"):
        A.validate_snapshot_storage_source(document, client=tmp_path)
    path = bind_spec(tmp_path, document)
    assert A.validate_snapshot_storage_source(document, client=tmp_path)
    for field, value in (("walkingHeight", 42.5), ("serverTileMin", [-5, -12])):
        bad = copy.deepcopy(document)
        bad["server"][field] = value
        with pytest.raises(A.AuthoringError):
            A.validate_snapshot_storage_source(bad, client=tmp_path)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(A.AuthoringError, match="hash changed"):
        A.validate_snapshot_storage_source(document, client=tmp_path)


def test_new_source_binding_works_through_normal_snapshot_loader(tmp_path, monkeypatch):
    from test_authoring import fixture
    path, document = fixture(tmp_path, monkeypatch)
    document["server"].update(Bounds(792, 792, -6, -12).metadata())
    document["server"]["collisionOriginMetres"] = [-200, 304]
    spec = bind_spec(A.CLIENT, document)
    write(path, document)
    snapshot = A.load_snapshot(path, production=False)
    assert snapshot.document["server"]["origin"] == [194, 292]
    assert document["sources"]["authoringSpec"]["path"] in snapshot.source_sha256
    spec.write_bytes(spec.read_bytes() + b"\n")
    with pytest.raises(A.AuthoringError, match="changed after snapshot load"):
        snapshot.bound_sources()
    with pytest.raises(A.AuthoringError, match="hash changed"):
        A.load_snapshot(path, production=False)


def test_current_legacy_specs_remain_unchanged_and_loadable():
    for contract in C.authored_contracts():
        assert contract.server_tile_min == (0, 0)
        assert contract.server_storage_version is None
        assert contract.spec_sha256 == hashlib.sha256(contract.spec_path.read_bytes()).hexdigest()
