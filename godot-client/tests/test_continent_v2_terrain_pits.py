"""Inland tears and the Saltsound approach stay repaired in source and packages."""
from pathlib import Path
import json
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot-client/tools"))
import repair_continent_v2_pits as R
import continent_v2_territories as T


def test_sink_audit_distinguishes_a_hole_from_an_open_valley():
    terrain = np.full((9, 9), 100., dtype=np.float32)
    terrain[3:6, 3:6] = 20
    np.testing.assert_array_equal(R.fill_sinks(terrain), 100)
    terrain[4, :5] = 20  # A real valley exits through the map boundary.
    np.testing.assert_array_equal(R.fill_sinks(terrain), terrain)


def test_interpolation_recovers_a_sloping_hillside_and_preserves_its_surroundings():
    rows, cols = np.indices((15, 15))
    plane = (100 + .3 * cols + .2 * rows).astype(np.float32)
    mask = np.zeros(plane.shape, bool)
    mask[4:11, 4:11] = True
    torn = plane.copy()
    torn[mask] -= 70
    fixed = R.interpolate(torn, mask)
    np.testing.assert_allclose(fixed, plane, atol=2e-5)
    assert fixed[~mask].tobytes() == torn[~mask].tobytes()


@pytest.fixture(scope="module")
def repaired():
    base, fixed, mask, sites = R.repair_field()
    territories = T.load_territories()
    return base, fixed, mask, sites, territories, T.Lattice.of(territories)


def test_saved_sculpts_repair_all_nine_sites_without_changing_frozen_bases(repaired):
    base, fixed, mask, sites, territories, lattice = repaired
    assert len(sites) == 9
    assert base[~mask].tobytes() == fixed[~mask].tobytes()
    current = R.lattice_base(territories, lattice)
    delta = R.to_lattice(fixed - base, lattice, np.float32(0))
    for t in territories:
        window = lattice.window(t)
        np.testing.assert_array_equal(t.heights, current[window])
        sculpt, errors = T.sculpt_deltas(t)
        assert not errors
        expected = delta[window]
        own = T.authority(t, lattice)[window]
        expected = np.where(own, expected, 0)
        touched = expected != 0
        np.testing.assert_array_equal(sculpt[touched], expected[touched], err_msg=t.id)


def test_reported_warrenmead_hole_is_a_walkable_hillside(repaired):
    base, fixed, *_ = repaired
    # The screenshot's [433,301] sits at continent [758,7264], beside the tear.
    r, c = (7264 - 6163) // 2, (758 - 299) // 2
    before, after = base[r-7:r+8, c-9:c+9], fixed[r-7:r+8, c-9:c+9]
    assert max(np.abs(np.diff(before, axis=0)).max(), np.abs(np.diff(before, axis=1)).max()) > 70
    assert max(np.abs(np.diff(after, axis=0)).max(), np.abs(np.diff(after, axis=1)).max()) < 1.3
    assert R.sample(fixed, 747, 7261) > 138


def test_scenery_follows_repaired_ground_without_changing_its_embedding(repaired):
    base, fixed, _, _, territories, _ = repaired
    report = json.loads((ROOT / "eloria-assets/maps/continent-v2/_continent_v2/terrain-pit-repair.json").read_text())
    assert sum(len(v["groundedAssets"]) for v in report["maps"].values()) > 100
    for t in territories:
        for asset in report["maps"].get(t.id, {}).get("groundedAssets", []):
            matrix = t.scene.world(asset["node"])
            x, y, z = matrix[:3, 3] + t.translation
            expected_delta = R.sample(fixed - base, x, z)
            assert y == pytest.approx(asset["afterY"], abs=1e-6)
            assert y - asset["beforeY"] == pytest.approx(expected_delta, abs=1e-6)


def test_replaying_the_repair_does_not_move_scenery_twice(repaired):
    base, fixed, _, _, territories, lattice = repaired
    for t in territories:
        if t.id not in R.REPAIRED_REGIONS:
            continue
        window = lattice.window(t)
        delta = R.to_lattice(fixed - base, lattice, np.float32(0))
        expected = np.where(T.authority(t, lattice)[window], delta[window], 0)
        path, content, installed, moved = R.prepare_scene(t, expected, base, fixed)
        assert installed and not moved
        assert content == path.read_text(encoding="utf-8")


def test_saltsound_hillside_approach_stays_within_the_normal_walking_grade(repaired):
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "eloria-assets/maps/nymara-regions/_continent"))
    import collision_export as CE
    base, fixed, *_ = repaired
    x, z = np.meshgrid(np.arange(2002.25, 2021.76, .5),
                       np.arange(6465.25, 6486.76, .5))
    world = SimpleNamespace(height=base, x0=R.FIRST[0], z0=R.FIRST[1], cell=2.)
    assert CE.terrain_grade(world, x, z).max() > 1.5
    world.height = fixed
    assert CE.terrain_grade(world, x, z).max() < CE.MAX_GRADE
    # Smoothing never moves the shore or makes cliffs globally climbable.
    np.testing.assert_array_equal(fixed[base <= 2], base[base <= 2])
    assert CE.MAX_GRADE == .65


def test_published_terrain_triangles_match_the_repaired_editor_ground(repaired):
    sys.path.insert(0, str(ROOT / "eloria-assets/maps/nymara-regions/_toolkit"))
    import glb_reader as GR
    _, fixed, _, sites, territories, _ = repaired
    samples = sites + [{"region": "saltsound", "continent": [2018.5, 6482.5]},
                       {"region": "saltsound", "continent": [2006.5, 6470.5]}]
    for site in samples:
        t = next(t for t in territories if t.id == site["region"])
        x, z = np.asarray(site["continent"]) - t.translation[[0, 2]]
        package = ROOT / "eloria-assets/maps/continent-v2" / t.id / "client"
        manifest = json.loads((package / "world.json").read_text())
        heights = []
        for chunk in manifest["streamingChunks"]["chunks"]:
            low, high = chunk["bounds"]["min"], chunk["bounds"]["max"]
            if not (low[0] <= x <= high[0] and low[2] <= z <= high[2]):
                continue
            path = package / chunk["manifest"]
            doc, body = GR.load(path.parent / "world.glb")
            tri = GR.triangles(doc, body, GR.named(doc, "Terrain_"))
            if not len(tri):
                continue
            a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
            denominator = (b[:, 2]-c[:, 2])*(a[:, 0]-c[:, 0]) + (c[:, 0]-b[:, 0])*(a[:, 2]-c[:, 2])
            valid = np.abs(denominator) > 1e-10
            a, b, c, denominator = a[valid], b[valid], c[valid], denominator[valid]
            u = ((b[:, 2]-c[:, 2])*(x-c[:, 0]) + (c[:, 0]-b[:, 0])*(z-c[:, 2])) / denominator
            v = ((c[:, 2]-a[:, 2])*(x-c[:, 0]) + (a[:, 0]-c[:, 0])*(z-c[:, 2])) / denominator
            hit = (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1+1e-6)
            heights.extend((u*a[:, 1]+v*b[:, 1]+(1-u-v)*c[:, 1])[hit])
        assert heights, site
        assert max(heights) == pytest.approx(R.sample(fixed, *site["continent"]), abs=.001), site
