"""Ground v2 replays byte-exact from v1 and its pinned recipe, and refuses unsafe edits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_continent_v2_ground as B


@pytest.fixture(scope="module")
def built():
    recipe = B.load_recipe()
    return recipe, B.build(recipe)


def test_outputs_replay_byte_exact(built):
    _, expected = built
    for name, blob in expected.items():
        assert (B.OUTPUT / name).read_bytes() == blob, name


def test_v1_vertices_outside_the_changed_mask_are_byte_identical(built):
    recipe, expected = built
    provenance = json.loads(expected["terrain-provenance.json"])
    grid = provenance["grid"]
    w, h = grid["gridSize"]
    heights = np.frombuffer(expected["base-heights.f32le"], "<f4").reshape(h, w)
    colors = np.frombuffer(expected["base-colors.rgba8"], np.uint8).reshape(h, w, 4)
    changed = np.unpackbits(np.frombuffer(expected["changed-mask.bits"], np.uint8), count=w * h).reshape(h, w) > 0
    _, v1h, v1c = B.load_v1(recipe)
    window = provenance["predecessorWindow"]
    rows = slice(window["row0"], window["row0"] + window["rows"])
    cols = slice(window["col0"], window["col0"] + window["cols"])
    keep = ~changed[rows, cols]
    assert np.array_equal(heights[rows, cols].view(np.uint32)[keep], v1h.view(np.uint32)[keep])
    assert np.array_equal(colors[rows, cols][keep], v1c[keep])
    assert not changed[:rows.start].any() and not changed[rows.stop:].any() and not changed[:, cols.stop:].any()
    assert provenance["invariants"]["predecessorVerticesChanged"] == int(changed.sum())


def test_edge_is_sea_and_exclusions_untouched(built):
    recipe, expected = built
    provenance = json.loads(expected["terrain-provenance.json"])
    w, h = provenance["grid"]["gridSize"]
    heights = np.frombuffer(expected["base-heights.f32le"], "<f4").reshape(h, w)
    assert np.isfinite(heights).all()
    assert max(heights[0].max(), heights[-1].max(), heights[:, 0].max(), heights[:, -1].max()) < 0
    grid = B.Grid(recipe["grid"]["continentFirstVertex"], recipe["grid"]["gridSize"])
    excluded = B.load_exclusions(recipe, grid)
    changed = np.unpackbits(np.frombuffer(expected["changed-mask.bits"], np.uint8), count=w * h).reshape(h, w) > 0
    assert not (excluded & changed).any()


def test_seabed_profile_deepens_monotonically():
    profile = np.asarray(B.load_recipe()["seabed"]["profile"], np.float64)
    assert np.all(np.diff(profile[:, 0]) > 0) and np.all(np.diff(profile[:, 1]) <= 0)


def tiny_recipe(tmp_path, weights_at, raster_height=3.0, recipe_edit=None):
    """The real recipe with one extra 3x3 edit whose height weight is set at one (row, col) of the v2 grid."""
    recipe = json.loads(json.dumps(B.load_recipe()))
    grid = B.Grid(recipe["grid"]["continentFirstVertex"], recipe["grid"]["gridSize"])
    r, c = weights_at
    first = [float(grid.first[0] + B.CELL * (c - 1)), float(grid.first[1] + B.CELL * (r - 1))]
    eh = np.full((3, 3), raster_height, "<f4")
    ec = np.full((3, 3, 4), 200, np.uint8)
    wh = np.zeros((3, 3), np.uint8); wh[1, 1] = 255
    wc = np.zeros((3, 3), np.uint8)
    files = {}
    for key, arr, ext in (("heights", eh, "f32le"), ("colors", ec, "rgba8"),
                          ("heightWeights", wh, "hw.u8"), ("colorWeights", wc, "cw.u8")):
        blob = arr.tobytes()
        path = tmp_path / f"probe.{ext}"
        path.write_bytes(blob)
        files[key] = {"path": str(path), "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
    recipe["edits"].append({"id": "probe", "firstVertex": first, "gridSize": [3, 3], "files": files})
    return recipe


def find(mask: np.ndarray) -> tuple[int, int]:
    r, c = np.argwhere(mask)[len(np.argwhere(mask)) // 2]
    return int(r), int(c)


def test_refuses_an_edit_on_an_excluded_vertex(tmp_path):
    recipe = B.load_recipe()
    grid = B.Grid(recipe["grid"]["continentFirstVertex"], recipe["grid"]["gridSize"])
    excluded = B.load_exclusions(recipe, grid)
    with pytest.raises(B.GroundError, match="excluded"):
        B.build(tiny_recipe(tmp_path, find(excluded)))


def test_refuses_raising_kept_land(tmp_path):
    recipe = B.load_recipe()
    grid, window, _, v1h, _, _, _, sunk, _ = B.build_base(recipe)
    excluded = B.load_exclusions(recipe, grid)
    kept = np.zeros(excluded.shape, bool)
    kept[window] = (v1h > 0) & ~sunk
    with pytest.raises(B.GroundError, match="kept land"):
        B.build(tiny_recipe(tmp_path, find(kept & ~ndimage_dilate(excluded))))


def test_refuses_a_changed_pinned_source(tmp_path):
    recipe = tiny_recipe(tmp_path, (5, 5))
    path = Path(recipe["edits"][-1]["files"]["heights"]["path"])
    blob = bytearray(path.read_bytes()); blob[0] ^= 1
    path.write_bytes(bytes(blob))
    with pytest.raises(B.GroundError, match="pinned input changed"):
        B.build(recipe)


def ndimage_dilate(mask):
    from scipy import ndimage
    return ndimage.binary_dilation(mask, iterations=2)
