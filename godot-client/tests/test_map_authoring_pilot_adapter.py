"""The editor's small export is consumable by the real server movement code."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "tools" / "map_authoring_pilot_adapter.py"
EXAMPLE_MANIFEST = (ROOT / "src" / "dev" / "map_authoring_pilot"
                    / "example_export" / "world.json")
SPEC = importlib.util.spec_from_file_location("map_authoring_pilot_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


def _server_root() -> Path:
    configured = os.environ.get("ELORIA_SERVER_ROOT")
    if not configured:
        pytest.skip("set ELORIA_SERVER_ROOT to run the real-server adapter check")
    root = Path(configured)
    if not (root / "eloria" / "world.py").is_file():
        pytest.fail(f"ELORIA_SERVER_ROOT is not a server checkout: {root}")
    return root


def test_actual_godot_export_runs_through_real_server_pathfinding():
    result = ADAPTER.validate_export(EXAMPLE_MANIFEST, _server_root())

    assert result["pathfinder"] == "eloria.world.World.find_path"
    assert result["serverGrid"] == [48, 48]
    assert all(length > 0 for length in result["segmentLengths"])
    assert set(result["blocked"]) == {
        "waterProbe", "solidProbe", "besideBridgeProbe"}


def test_conservative_fold_blocks_a_server_tile_if_one_sample_is_blocked():
    authored = bytes((5, 5, 5, 5,
                      5, 0, 5, 5))
    width, height, folded = ADAPTER.fold_for_server(4, 2, authored, 0.0, 0.2)

    assert (width, height) == (2, 1)
    assert folded == b"\0\1"
